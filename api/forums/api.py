"""Discussion forums (items 4.08 to 4.10).

Forums belong to a site, optionally to one of its modules, and may be limited to some of the site's groups.
Teaching staff make them; everyone who sees a forum may start threads and reply, except that only teaching
staff start threads in a question-and-answer forum, where a student sees others' replies only after
replying. Every post is cleaned with courses.richtext. An author may change or remove their own post for
FORUM_EDIT_MINUTES (30) after posting; moderators (the site's teaching staff and course administrators)
remove posts with a reason, pin and lock threads, and review reports. Nobody posts before accepting the
conduct statement in force. Every change is written to the audit log.
"""

import re

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from assessments.models import GradeCategory
from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from courses import richtext
from courses.access import TaughtRecord, can_teach, person_of, site_role, visible_sites
from courses.api import TeachingViewSet
from courses.models import ContentItem, CourseSite, Membership, Module, SiteGroup
from forums import services
from forums.models import (
    ConductAcceptance,
    ConductStatement,
    Forum,
    ParticipationMark,
    Post,
    PostReport,
    Subscription,
    Thread,
)
from iam.permissions import RolePermission
from iam.services import SITE_ADMIN_ROLES, has_role
from people.models import PersonRef
from rubrics.models import Rubric


class Refused(APIException):
    status_code = 409
    default_code = "refused"


class ConductNotAccepted(APIException):
    status_code = 403
    default_code = "conduct_not_accepted"
    default_detail = "Read and accept the conduct statement before you post."


def require_conduct(user) -> None:
    if not services.conduct_accepted(user):
        raise ConductNotAccepted()


def rich_body(body: str, body_format: str, site: CourseSite) -> str:
    """A post or description cleaned against the allow-list; refused when empty or with an image problem."""
    cleaned = richtext.text_to_html(body) if body_format == "text" else richtext.clean(body)
    if not re.sub(r"<[^>]*>", "", cleaned).strip() and "<img" not in cleaned:
        raise serializers.ValidationError({"body": ["Write something first."]})
    problems = richtext.errors(richtext.check(cleaned))
    if problems:
        raise serializers.ValidationError({"body": [issue.detail for issue in problems]})
    images = richtext.image_item_ids(cleaned)
    if images and ContentItem.objects.filter(id__in=images, module__site=site).count() != len(images):
        raise serializers.ValidationError({"body": ["A picture in the post is not a file on this course."]})
    return cleaned


def author_name(user) -> str | None:
    if user is None:
        return None
    person = getattr(user, "person", None)
    return person.full_name if person is not None else (user.get_full_name() or user.get_username())


BODY_FORMAT = serializers.ChoiceField(
    choices=["html", "text"],
    default="html",
    write_only=True,
    help_text="'text' turns plain text into paragraphs",
)


# ---------------------------------------------------------------------------------------------------------
# Forums


class ForumSerializer(serializers.ModelSerializer):
    site = TaughtRecord(CourseSite)
    module = TaughtRecord(
        Module, "site", required=False, allow_null=True, help_text="Empty for the whole site"
    )
    groups = TaughtRecord(
        SiteGroup, "site", many=True, required=False, help_text="Shown only to these groups"
    )
    description = serializers.CharField(required=False, allow_blank=True, help_text="Cleaned on the server")
    body_format = serializers.ChoiceField(choices=["html", "text"], default="html", write_only=True)
    subscribed = serializers.SerializerMethodField()
    threads = serializers.SerializerMethodField(help_text="How many threads it has")
    rubric_id = serializers.PrimaryKeyRelatedField(
        source="rubric",
        queryset=Rubric.objects.filter(site__isnull=False),
        required=False,
        allow_null=True,
        help_text="One of the course's rubrics (rubrics.Rubric); copy a library rubric to the course first",
    )
    grade_category = serializers.PrimaryKeyRelatedField(
        queryset=GradeCategory.objects.all(), required=False, allow_null=True, help_text="Gradebook category"
    )

    class Meta:
        model = Forum
        fields = (
            "id",
            "site",
            "module",
            "title",
            "description",
            "body_format",
            "forum_type",
            "is_published",
            "groups",
            "weight",
            "max_mark",
            "rubric_id",
            "grade_category",
            "subscribed",
            "threads",
            "created_at",
        )
        read_only_fields = ("created_at",)

    def validate(self, attrs):
        site = attrs.get("site") or self.instance.site
        if self.instance is not None and "site" in attrs and attrs["site"].pk != self.instance.site_id:
            raise serializers.ValidationError({"site": ["A forum stays on its course."]})
        module = attrs.get("module")
        if module is not None and module.site_id != site.id:
            raise serializers.ValidationError({"module": ["Choose a module of the same course."]})
        if any(g.site_id != site.id for g in attrs.get("groups", [])):
            raise serializers.ValidationError({"groups": ["Choose groups of the same course."]})
        if attrs.get("rubric") is not None and attrs["rubric"].site_id != site.id:
            raise serializers.ValidationError({"rubric_id": ["Choose a rubric of the same course."]})
        if attrs.get("grade_category") is not None and attrs["grade_category"].site_id != site.id:
            raise serializers.ValidationError({"grade_category": ["Choose a category of the same course."]})
        kind = attrs.get("forum_type", getattr(self.instance, "forum_type", Forum.Type.GENERAL))
        weight = attrs.get("weight", getattr(self.instance, "weight", 0))
        if weight and kind != Forum.Type.GRADED:
            raise serializers.ValidationError({"weight": ["Only a graded forum counts towards coursework."]})
        if "description" in attrs:
            fmt = attrs.pop("body_format", "html")
            text = attrs["description"]
            if text.strip():
                try:
                    attrs["description"] = rich_body(text, fmt, site)
                except serializers.ValidationError as exc:
                    raise serializers.ValidationError({"description": exc.detail["body"]}) from None
        attrs.pop("body_format", None)
        return attrs

    def get_subscribed(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request) and Subscription.objects.filter(user=request.user, forum=obj).exists()

    def get_threads(self, obj) -> int:
        return getattr(obj, "thread_count", None) or obj.threads.count()


class ThreadSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    replies = serializers.IntegerField(read_only=True, source="reply_count", default=0)

    class Meta:
        model = Thread
        fields = (
            "id",
            "forum",
            "title",
            "author_name",
            "is_pinned",
            "is_locked",
            "last_post_at",
            "replies",
            "created_at",
        )
        read_only_fields = fields

    def get_author_name(self, obj) -> str | None:
        return author_name(obj.author)


class StartThreadSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    body = serializers.CharField()
    body_format = BODY_FORMAT


class SubscribedSerializer(serializers.Serializer):
    subscribed = serializers.BooleanField()


class MarkWriteSerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(queryset=PersonRef.objects.all(), help_text="Person id")
    mark = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
    feedback = serializers.CharField(required=False, allow_blank=True)
    rubric_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class MarkRowSerializer(serializers.Serializer):
    person_id = serializers.IntegerField()
    student_no = serializers.CharField()
    name = serializers.CharField()
    posts = serializers.IntegerField(help_text="Posts in the forum, not counting removed ones")
    mark = serializers.CharField(allow_null=True)
    feedback = serializers.CharField()
    rubric_id = serializers.IntegerField(allow_null=True)
    is_released = serializers.BooleanField()


class MarksReleasedSerializer(serializers.Serializer):
    released = serializers.IntegerField()


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("site", OpenApiTypes.INT, description="Only this site"),
            OpenApiParameter("module", OpenApiTypes.INT, description="Only this module"),
        ],
        summary="Forums I can see",
    )
)
class ForumViewSet(TeachingViewSet):
    """Forums of a site or a module. Teaching staff make and change them; members see those open to them."""

    serializer_class = ForumSerializer

    def get_queryset(self):
        qs = (
            Forum.objects.filter(site__in=visible_sites(self.request.user))
            .select_related("site", "module")
            .prefetch_related("groups", "module__groups")
            .annotate(thread_count=Count("threads"))
        )
        params = self.request.query_params
        if params.get("site"):
            qs = qs.filter(site_id=params["site"])
        if params.get("module"):
            qs = qs.filter(module_id=params["module"])
        return qs

    def list(self, request, *args, **kwargs):
        forums = services.visible_forums(request.user, self.get_queryset())
        return Response(self.get_serializer(forums, many=True).data)

    def get_object(self):
        forum = super().get_object()
        if not services.forum_visible(self.request.user, forum):
            raise NotFound()
        return forum

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]

    def get_serializer_class(self):
        return {"threads": StartThreadSerializer, "marks": MarkWriteSerializer}.get(
            self.action, ForumSerializer
        )

    @extend_schema(
        methods=["GET"],
        responses={200: ThreadSerializer(many=True), 404: ErrorSerializer},
        summary="Threads of a forum, pinned first then the most recently active",
    )
    @extend_schema(
        methods=["POST"],
        request=StartThreadSerializer,
        responses={
            201: ThreadSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        summary="Start a thread. Only teaching staff start one in a question-and-answer forum",
    )
    @action(detail=True, methods=["get", "post"])
    def threads(self, request, pk=None):
        forum = self.get_object()
        if request.method == "GET":
            rows = forum.threads.select_related("author").annotate(
                reply_count=Count(
                    "posts", filter=Q(posts__parent__isnull=False, posts__deleted_at__isnull=True)
                )
            )
            return Response(ThreadSerializer(rows, many=True).data)
        moderator = services.is_moderator(request.user, forum)
        if site_role(request.user, forum.site) == "auditor":
            raise PermissionDenied("Auditors read forums but do not post.")
        if forum.forum_type == Forum.Type.QUESTION and not moderator:
            raise PermissionDenied("Only teaching staff start a discussion in a question-and-answer forum.")
        require_conduct(request.user)
        data = StartThreadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        body = rich_body(data.validated_data["body"], data.validated_data["body_format"], forum.site)
        with transaction.atomic():
            now = timezone.now()
            thread = Thread.objects.create(
                forum=forum,
                title=data.validated_data["title"],
                author=request.user,
                last_post_at=now,
                created_by=request.user,
                updated_by=request.user,
            )
            post = Post.objects.create(
                thread=thread,
                author=request.user,
                body=body,
                created_by=request.user,
                updated_by=request.user,
            )
            Subscription.objects.get_or_create(user=request.user, thread=thread)
            record(request, "create", thread, after=snapshot(thread))
            record(request, "create", post, after=snapshot(post))
            services.notify_new_post(post)
        return Response(ThreadSerializer(thread).data, status=201)

    @extend_schema(
        request=None,
        responses={200: SubscribedSerializer, 404: ErrorSerializer},
        summary="Be told of every new post in this forum",
    )
    @action(detail=True, methods=["post"])
    def subscribe(self, request, pk=None):
        forum = self.get_object()
        Subscription.objects.get_or_create(user=request.user, forum=forum)
        return Response({"subscribed": True})

    @extend_schema(
        request=None,
        responses={200: SubscribedSerializer, 404: ErrorSerializer},
        summary="Stop notices of new posts in this forum",
    )
    @action(detail=True, methods=["post"])
    def unsubscribe(self, request, pk=None):
        forum = self.get_object()
        Subscription.objects.filter(user=request.user, forum=forum).delete()
        return Response({"subscribed": False})

    def _graded(self, forum: Forum) -> None:
        if forum.forum_type != Forum.Type.GRADED:
            raise Refused("Only a graded forum has participation marks.", code="not_graded")

    @extend_schema(
        methods=["GET"],
        responses={200: MarkRowSerializer(many=True), 404: ErrorSerializer, 409: ErrorSerializer},
        summary="Participation marks: every student for teaching staff, my own released mark for a student",
    )
    @extend_schema(
        methods=["POST"],
        request=MarkWriteSerializer,
        responses={
            200: MarkRowSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Give or change a student's participation mark (teaching staff), optionally against a rubric",
    )
    @action(detail=True, methods=["get", "post"])
    def marks(self, request, pk=None):
        forum = self.get_object()
        self._graded(forum)
        teaching = can_teach(request.user, forum.site) or site_role(request.user, forum.site) == "auditor"
        if request.method == "GET":
            members = Membership.objects.filter(
                site=forum.site, is_active=True, role=Membership.SiteRole.STUDENT
            ).select_related("person")
            if not teaching:
                members = members.filter(person=person_of(request.user))
            return Response([self._row(forum, m.person, released_only=not teaching) for m in members])
        if not can_teach(request.user, forum.site):
            raise PermissionDenied("Only the course's teaching staff give participation marks.")
        data = MarkWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        student = v["student"]
        if not Membership.objects.filter(
            site=forum.site, person=student, is_active=True, role=Membership.SiteRole.STUDENT
        ).exists():
            raise serializers.ValidationError({"student": ["Choose a student of this course."]})
        if v["mark"] > forum.max_mark:
            raise serializers.ValidationError({"mark": [f"The mark is out of {forum.max_mark}."]})
        if (
            v.get("rubric_id") is not None
            and not Rubric.objects.filter(pk=v["rubric_id"], site=forum.site).exists()
        ):
            raise serializers.ValidationError({"rubric_id": ["Choose a rubric of this course."]})
        with transaction.atomic():
            existing = ParticipationMark.objects.filter(forum=forum, student=student).first()
            before = snapshot(existing) if existing else None
            mark, _ = ParticipationMark.objects.update_or_create(
                forum=forum,
                student=student,
                defaults={
                    "mark": v["mark"],
                    "feedback": v.get("feedback", ""),
                    "rubric_id": v.get("rubric_id", forum.rubric_id),
                    "updated_by": request.user,
                    **({} if existing else {"created_by": request.user}),
                },
            )
            record(request, "mark", mark, before=before, after=snapshot(mark))
        return Response(self._row(forum, student, released_only=False))

    @staticmethod
    def _row(forum: Forum, person: PersonRef, *, released_only: bool) -> dict:
        mark = ParticipationMark.objects.filter(forum=forum, student=person).first()
        shown = mark is not None and (mark.is_released or not released_only)
        posts = Post.objects.filter(
            thread__forum=forum, deleted_at__isnull=True, author__person=person
        ).count()
        return {
            "person_id": person.id,
            "student_no": person.external_id,
            "name": person.full_name,
            "posts": posts,
            "mark": str(mark.mark) if shown else None,
            "feedback": mark.feedback if shown else "",
            "rubric_id": mark.rubric_id if shown else None,
            "is_released": bool(mark and mark.is_released),
        }

    @extend_schema(
        request=None,
        responses={
            200: MarksReleasedSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Release every participation mark of the forum to its student",
    )
    @action(detail=True, methods=["post"], url_path="release-marks")
    def release_marks(self, request, pk=None):
        forum = self.get_object()
        self._graded(forum)
        if not can_teach(request.user, forum.site):
            raise PermissionDenied("Only the course's teaching staff release marks.")
        from notifications.services import notify

        released = 0
        with transaction.atomic():
            for mark in forum.marks.filter(is_released=False).select_related("student__user"):
                before = snapshot(mark)
                mark.is_released = True
                mark.updated_by = request.user
                mark.save(update_fields=["is_released", "updated_by", "updated_at"])
                record(request, "update", mark, before=before, after=snapshot(mark))
                released += 1
                notify(
                    [mark.student.user],
                    title=f"{forum.site.code}: participation mark for {forum.title}"[:160],
                    link=f"/forums/{forum.id}",
                    dedupe_key=f"forum-mark:{mark.id}",
                )
        return Response({"released": released})


# ---------------------------------------------------------------------------------------------------------
# Threads and posts


class PostSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    body = serializers.SerializerMethodField(help_text="Empty when removed, or hidden from the reader")
    removed = serializers.SerializerMethodField()
    removed_reason = serializers.SerializerMethodField(help_text="For moderators and the author")
    hidden = serializers.SerializerMethodField(help_text="Hidden from students while a report is reviewed")
    can_edit = serializers.SerializerMethodField(help_text="The author, within the edit window")

    class Meta:
        model = Post
        fields = (
            "id",
            "thread",
            "parent",
            "author_name",
            "body",
            "created_at",
            "edited_at",
            "removed",
            "removed_reason",
            "hidden",
            "can_edit",
        )
        read_only_fields = fields

    def _moderator(self, obj) -> bool:
        return bool(self.context.get("moderator"))

    def _own(self, obj) -> bool:
        request = self.context.get("request")
        return request is not None and obj.author_id == request.user.pk

    def get_author_name(self, obj) -> str | None:
        return author_name(obj.author)

    def get_body(self, obj) -> str:
        if obj.deleted_at is not None:
            return ""
        if obj.is_hidden and not (self._moderator(obj) or self._own(obj)):
            return ""
        return obj.body

    def get_removed(self, obj) -> bool:
        return obj.deleted_at is not None

    def get_removed_reason(self, obj) -> str | None:
        if obj.deleted_at is None or not (self._moderator(obj) or self._own(obj)):
            return None
        return obj.delete_reason

    def get_hidden(self, obj) -> bool:
        return obj.is_hidden

    def get_can_edit(self, obj) -> bool:
        return (
            self._own(obj)
            and obj.deleted_at is None
            and timezone.now() - obj.created_at <= services.edit_window()
        )


class ThreadDetailSerializer(serializers.Serializer):
    thread = ThreadSerializer()
    posts = PostSerializer(many=True)
    replies_hidden = serializers.BooleanField(
        help_text="Question-and-answer forum: others' replies show once you have replied"
    )
    subscribed = serializers.BooleanField()
    moderator = serializers.BooleanField(help_text="Whether I may pin, lock and remove posts here")


class ReplySerializer(serializers.Serializer):
    body = serializers.CharField()
    body_format = BODY_FORMAT
    parent = serializers.IntegerField(
        required=False, help_text="The post replied to; the opening post if empty"
    )


class FlagSerializer(serializers.Serializer):
    value = serializers.BooleanField(help_text="True to pin (or lock), false to unpin (or unlock)")


def visible_thread(request, pk: int) -> Thread:
    thread = get_object_or_404(
        Thread.objects.select_related("forum__site", "forum__module").filter(
            forum__site__in=visible_sites(request.user)
        ),
        pk=pk,
    )
    if not services.forum_visible(request.user, thread.forum):
        raise NotFound()
    return thread


class ThreadViewSet(viewsets.GenericViewSet):
    """A thread with its posts, replies, pin and lock, subscriptions."""

    permission_classes = [RolePermission]
    serializer_class = ThreadSerializer
    queryset = Thread.objects.none()

    def _thread(self) -> Thread:
        return visible_thread(self.request, self.kwargs["pk"])

    @extend_schema(
        responses={200: ThreadDetailSerializer, 404: ErrorSerializer}, summary="A thread and its posts"
    )
    def retrieve(self, request, pk=None):
        thread = self._thread()
        moderator = services.is_moderator(request.user, thread.forum)
        posts = thread.posts.select_related("author__person")
        hidden = services.replies_hidden_until_posting(request.user, thread)
        if hidden:
            posts = posts.filter(Q(parent__isnull=True) | Q(author=request.user))
        context = {"request": request, "moderator": moderator}
        return Response(
            {
                "thread": ThreadSerializer(thread).data,
                "posts": PostSerializer(posts, many=True, context=context).data,
                "replies_hidden": hidden,
                "subscribed": Subscription.objects.filter(user=request.user, thread=thread).exists(),
                "moderator": moderator,
            }
        )

    @extend_schema(
        request=ReplySerializer,
        responses={
            201: PostSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Reply in a thread. Refused while the thread is locked (except for moderators)",
    )
    @action(detail=True, methods=["post"])
    def replies(self, request, pk=None):
        thread = self._thread()
        forum = thread.forum
        moderator = services.is_moderator(request.user, forum)
        if site_role(request.user, forum.site) == "auditor":
            raise PermissionDenied("Auditors read forums but do not post.")
        if thread.is_locked and not moderator:
            raise Refused("This thread is locked: no new replies.", code="thread_locked")
        require_conduct(request.user)
        data = ReplySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        opening = thread.posts.filter(parent__isnull=True).first()
        parent = opening
        if data.validated_data.get("parent"):
            parent = thread.posts.filter(pk=data.validated_data["parent"], deleted_at__isnull=True).first()
            if parent is None:
                raise serializers.ValidationError({"parent": ["Reply to a post of this thread."]})
            if services.replies_hidden_until_posting(request.user, thread) and parent.pk != opening.pk:
                raise serializers.ValidationError({"parent": ["Reply to the question first."]})
        body = rich_body(data.validated_data["body"], data.validated_data["body_format"], forum.site)
        with transaction.atomic():
            post = Post.objects.create(
                thread=thread,
                parent=parent,
                author=request.user,
                body=body,
                created_by=request.user,
                updated_by=request.user,
            )
            services.touch_thread(thread, post.created_at)
            Subscription.objects.get_or_create(user=request.user, thread=thread)
            record(request, "create", post, after=snapshot(post))
            services.notify_new_post(post)
        context = {"request": request, "moderator": moderator}
        return Response(PostSerializer(post, context=context).data, status=201)

    def _moderate_flag(self, request, field: str):
        thread = self._thread()
        if not services.is_moderator(request.user, thread.forum):
            raise PermissionDenied("Only the course's teaching staff and course administrators moderate.")
        data = FlagSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            before = snapshot(thread)
            setattr(thread, field, data.validated_data["value"])
            thread.updated_by = request.user
            thread.save(update_fields=[field, "updated_by", "updated_at"])
            record(request, "moderate", thread, before=before, after=snapshot(thread))
        return Response(ThreadSerializer(thread).data)

    @extend_schema(
        request=FlagSerializer,
        responses={200: ThreadSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        summary="Pin a thread to the top of its forum, or unpin it (moderators)",
    )
    @action(detail=True, methods=["post"])
    def pin(self, request, pk=None):
        return self._moderate_flag(request, "is_pinned")

    @extend_schema(
        request=FlagSerializer,
        responses={200: ThreadSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
        summary="Lock a thread against new replies, or unlock it (moderators)",
    )
    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        return self._moderate_flag(request, "is_locked")

    @extend_schema(
        request=None,
        responses={200: SubscribedSerializer, 404: ErrorSerializer},
        summary="Be told of new replies in this thread",
    )
    @action(detail=True, methods=["post"])
    def subscribe(self, request, pk=None):
        Subscription.objects.get_or_create(user=request.user, thread=self._thread())
        return Response({"subscribed": True})

    @extend_schema(
        request=None,
        responses={200: SubscribedSerializer, 404: ErrorSerializer},
        summary="Stop notices of new replies in this thread",
    )
    @action(detail=True, methods=["post"])
    def unsubscribe(self, request, pk=None):
        Subscription.objects.filter(user=request.user, thread=self._thread()).delete()
        return Response({"subscribed": False})


class EditPostSerializer(serializers.Serializer):
    body = serializers.CharField()
    body_format = BODY_FORMAT


class RemoveSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=300,
        required=False,
        allow_blank=True,
        help_text="Required from a moderator removing someone else's post",
    )


class PostReportRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)


class PostReportSerializer(serializers.ModelSerializer):
    site = serializers.IntegerField(source="post.thread.forum.site_id", read_only=True)
    thread = serializers.IntegerField(source="post.thread_id", read_only=True)
    forum = serializers.IntegerField(source="post.thread.forum_id", read_only=True)

    class Meta:
        model = PostReport
        fields = (
            "id",
            "post",
            "thread",
            "forum",
            "site",
            "reason",
            "status",
            "created_at",
            "reviewed_at",
            "review_note",
        )
        read_only_fields = fields


class PostViewSet(viewsets.GenericViewSet):
    """One post: the author edits it within the window; a moderator or the author removes it; anyone who
    sees it reports it."""

    permission_classes = [RolePermission]
    serializer_class = PostSerializer
    queryset = Post.objects.none()

    def _post(self) -> Post:
        post = get_object_or_404(
            Post.objects.select_related("thread__forum__site").filter(
                thread__forum__site__in=visible_sites(self.request.user)
            ),
            pk=self.kwargs["pk"],
        )
        thread = post.thread
        if not services.forum_visible(self.request.user, thread.forum):
            raise NotFound()
        moderator = services.is_moderator(self.request.user, thread.forum)
        hidden_reply = (
            post.parent_id is not None
            and post.author_id != self.request.user.pk
            and services.replies_hidden_until_posting(self.request.user, thread)
        )
        if hidden_reply or (post.is_hidden and not moderator and post.author_id != self.request.user.pk):
            raise NotFound()
        return post

    def _context(self, post):
        return {
            "request": self.request,
            "moderator": services.is_moderator(self.request.user, post.thread.forum),
        }

    @extend_schema(
        request=EditPostSerializer,
        responses={
            200: PostSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Change my post within FORUM_EDIT_MINUTES (30) of posting it",
    )
    def partial_update(self, request, pk=None):
        post = self._post()
        if post.author_id != request.user.pk:
            raise PermissionDenied("Only the author changes a post.")
        if post.deleted_at is not None:
            raise Refused("This post has been removed.", code="removed")
        if timezone.now() - post.created_at > services.edit_window():
            raise Refused(
                "Posts can be changed for 30 minutes after posting. Reply instead to correct it.",
                code="edit_window_closed",
            )
        if post.thread.is_locked and not services.is_moderator(request.user, post.thread.forum):
            raise Refused("This thread is locked.", code="thread_locked")
        data = EditPostSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        body = rich_body(
            data.validated_data["body"], data.validated_data["body_format"], post.thread.forum.site
        )
        with transaction.atomic():
            before = snapshot(post)
            post.body = body
            post.edited_at = timezone.now()
            post.updated_by = request.user
            post.save(update_fields=["body", "edited_at", "updated_by", "updated_at"])
            record(request, "update", post, before=before, after=snapshot(post))
        return Response(PostSerializer(post, context=self._context(post)).data)

    @extend_schema(
        request=RemoveSerializer,
        responses={
            200: PostSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Remove a post: a moderator with a reason, or the author within the edit window. The post is "
        "kept for the record and shown as removed",
    )
    @action(detail=True, methods=["post"])
    def remove(self, request, pk=None):
        post = self._post()
        if post.deleted_at is not None:
            raise Refused("This post has already been removed.", code="removed")
        moderator = services.is_moderator(request.user, post.thread.forum)
        data = RemoveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reason = data.validated_data.get("reason", "").strip()
        if post.author_id == request.user.pk and not moderator:
            if timezone.now() - post.created_at > services.edit_window():
                raise Refused(
                    "Posts can be removed by their author for 30 minutes after posting. Report it to a "
                    "moderator instead.",
                    code="edit_window_closed",
                )
            reason = reason or "Removed by the author."
        elif not moderator:
            raise PermissionDenied("Only the course's teaching staff and course administrators remove posts.")
        elif not reason and post.author_id != request.user.pk:
            raise serializers.ValidationError({"reason": ["Say why the post is removed."]})
        with transaction.atomic():
            remove_post(request, post, reason or "Removed by the author.")
        return Response(PostSerializer(post, context=self._context(post)).data)

    @extend_schema(
        request=PostReportRequestSerializer,
        responses={
            201: PostReportSerializer,
            400: OpenApiTypes.OBJECT,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Report a post (item 4.09). A report by the course's teaching staff or a course "
        "administrator hides it from students at once; a student's report waits for a moderator",
    )
    @action(detail=True, methods=["post"])
    def report(self, request, pk=None):
        post = self._post()
        if post.deleted_at is not None:
            raise Refused("This post has already been removed.", code="removed")
        data = PostReportRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        forum = post.thread.forum
        with transaction.atomic():
            report = PostReport.objects.create(
                post=post,
                reported_by=request.user,
                reason=data.validated_data["reason"],
                created_by=request.user,
                updated_by=request.user,
            )
            record(request, "create", report, after=snapshot(report))
            # As for takedowns (item 2.19): only someone responsible for the course hides a post at once,
            # otherwise any one student could silence another by reporting them.
            if services.is_moderator(request.user, forum) and not post.is_hidden:
                before = snapshot(post)
                post.is_hidden = True
                post.save(update_fields=["is_hidden", "updated_at"])
                record(request, "moderate", post, before=before, after=snapshot(post))
            from notifications.services import notify

            notify(
                services.moderators(forum).exclude(pk=request.user.pk),
                title=f"{forum.site.code}: a post was reported in {forum.title}"[:160],
                body=data.validated_data["reason"][:500],
                link=f"/forums/{forum.id}/threads/{post.thread_id}",
                kind="approval",
                dedupe_key=f"post-report:{report.id}",
            )
        return Response(PostReportSerializer(report).data, status=201)


def remove_post(request, post: Post, reason: str) -> None:
    before = snapshot(post)
    post.deleted_at = timezone.now()
    post.deleted_by = request.user
    post.delete_reason = reason[:300]
    post.updated_by = request.user
    post.save()
    record(request, "moderate", post, before=before, after=snapshot(post), reason=reason)


class ReportReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=["remove", "keep"],
        help_text="remove: the post is removed with the note as reason; keep: shown",
    )
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, enum=[s for s, _ in PostReport.Status.choices])
        ],
        summary="Reports: those on the forums I moderate, and my own",
    )
)
class PostReportViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PostReportSerializer
    permission_classes = [RolePermission]
    queryset = PostReport.objects.none()

    def get_queryset(self):
        from courses.access import taught_sites

        qs = PostReport.objects.select_related("post__thread__forum")
        mine = Q(reported_by=self.request.user)
        qs = qs.filter(mine | Q(post__thread__forum__site__in=taught_sites(self.request.user)))
        status = self.request.query_params.get("status")
        return qs.filter(status=status) if status else qs

    @extend_schema(
        request=ReportReviewSerializer,
        responses={
            200: PostReportSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Decide a report: remove the post, or keep it and show it again (moderators)",
    )
    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        report = self.get_object()
        post = report.post
        if not services.is_moderator(request.user, post.thread.forum):
            raise PermissionDenied(
                "Only the course's teaching staff and course administrators review reports."
            )
        if report.status != PostReport.Status.OPEN:
            raise Refused("This report has been decided.", code="already_decided")
        data = ReportReviewSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        remove = data.validated_data["decision"] == "remove"
        note = data.validated_data.get("note", "")
        with transaction.atomic():
            now = timezone.now()
            open_reports = PostReport.objects.filter(post=post, status=PostReport.Status.OPEN)
            for each in open_reports:
                before = snapshot(each)
                each.status = PostReport.Status.REMOVED if remove else PostReport.Status.RESTORED
                each.reviewed_by, each.reviewed_at, each.review_note = request.user, now, note
                each.updated_by = request.user
                each.save()
                record(request, "review", each, before=before, after=snapshot(each))
            if remove and post.deleted_at is None:
                remove_post(request, post, note or "Removed by a moderator after a report.")
            if not remove and post.is_hidden:
                before = snapshot(post)
                post.is_hidden = False
                post.save(update_fields=["is_hidden", "updated_at"])
                record(request, "moderate", post, before=before, after=snapshot(post))
        report.refresh_from_db()
        return Response(PostReportSerializer(report).data)


# ---------------------------------------------------------------------------------------------------------
# The conduct statement


class StatementSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConductStatement
        fields = ("id", "version", "body", "created_at", "published_at")
        read_only_fields = ("id", "version", "created_at", "published_at")

    def validate(self, attrs):
        if self.instance is not None and self.instance.published_at:
            raise serializers.ValidationError("A published statement never changes: write a new version.")
        return attrs


class CurrentStatementSerializer(serializers.Serializer):
    statement = StatementSerializer(allow_null=True)
    accepted = serializers.BooleanField(help_text="Whether I have accepted the statement in force")


class ConductStatementViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    """The conduct statement: everyone reads the one in force and accepts it; course administrators write
    new versions and publish them."""

    serializer_class = StatementSerializer
    permission_classes = [RolePermission]
    write_roles = SITE_ADMIN_ROLES
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if has_role(self.request.user, *SITE_ADMIN_ROLES):
            return ConductStatement.objects.all()
        return ConductStatement.objects.filter(published_at__isnull=False)

    def perform_create(self, serializer):
        with transaction.atomic():
            last = ConductStatement.objects.order_by("-version").first()
            statement = serializer.save(
                version=(last.version + 1) if last else 1, created_by=self.request.user
            )
            record(self.request, "create", statement, after=snapshot(statement))

    def perform_update(self, serializer):
        with transaction.atomic():
            before = snapshot(serializer.instance)
            statement = serializer.save()
            record(self.request, "update", statement, before=before, after=snapshot(statement))

    @extend_schema(
        request=None,
        responses={
            200: StatementSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Publish a draft: everyone accepts it again before they next post (course administrators)",
    )
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        statement = self.get_object()
        if statement.published_at:
            raise Refused("This version is already published.", code="already_published")
        with transaction.atomic():
            before = snapshot(statement)
            statement.published_at = timezone.now()
            statement.save(update_fields=["published_at"])
            record(request, "publish", statement, before=before, after=snapshot(statement))
        return Response(StatementSerializer(statement).data)

    @extend_schema(
        responses=CurrentStatementSerializer,
        summary="The conduct statement in force, and whether I have accepted it",
    )
    @action(detail=False, methods=["get"], permission_classes=[RolePermission])
    def current(self, request):
        statement = services.current_statement()
        accepted = bool(statement) and services.conduct_accepted(request.user)
        return Response(
            {"statement": StatementSerializer(statement).data if statement else None, "accepted": accepted}
        )

    @extend_schema(
        request=None,
        responses={200: CurrentStatementSerializer, 409: ErrorSerializer},
        summary="Accept the conduct statement in force (needed before posting or sending messages)",
    )
    @action(detail=False, methods=["post"], url_path="current/accept")
    def accept(self, request):
        statement = services.current_statement()
        if statement is None:
            raise Refused("No conduct statement is in force.", code="no_statement")
        with transaction.atomic():
            acceptance, created = ConductAcceptance.objects.get_or_create(
                statement=statement, user=request.user
            )
            if created:
                record(request, "conduct_accepted", statement, after={"version": statement.version})
        return Response({"statement": StatementSerializer(statement).data, "accepted": True})

    def get_permissions(self):
        if self.action in ("current", "accept"):
            self.write_roles = None
        return super().get_permissions()


router = DefaultRouter()
router.register("forums", ForumViewSet, basename="forum")
router.register("threads", ThreadViewSet, basename="thread")
router.register("posts", PostViewSet, basename="post")
router.register("post-reports", PostReportViewSet, basename="post-report")
router.register("conduct-statements", ConductStatementViewSet, basename="conduct-statement")
urlpatterns = router.urls
