"""Messages (item 4.11).

- A student writes to the teaching staff of a site they are on (all of them, or those they choose); teaching
  staff write to any member of their site. Students never write to other students unless
  MESSAGING_STUDENT_TO_STUDENT is on (off by default, decision in the feature audit: fewer conduct risks).
- Teaching staff send a notice to one of the site's groups or to the whole site. Students read it but do
  not reply in it (a reply would reach every student); they start a conversation with the staff instead.
- Each participant has a read receipt: the time up to which they have read. A sender sees who has read
  each message.
- Sending takes an Idempotency-Key (practicals.offline), so a phone's offline queue never sends twice, and
  the phone's own time is kept beside the server's.
- Nobody sends before accepting the conduct statement in force (forums), and every message is cleaned
  with courses.richtext.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from courses.access import can_teach, site_role, visible_sites
from courses.models import CourseSite, Membership, SiteGroup
from forums.api import author_name, require_conduct, rich_body
from iam.permissions import RolePermission
from messaging.models import Conversation, Message, Participant
from practicals.offline import IDEMPOTENCY_HEADER, check_client_time, idempotent

TEACHING_ROLES = [Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT]


def may_write_to(user, site: CourseSite):
    """The people the user may start a direct conversation with on the site."""
    members = Membership.objects.filter(site=site, is_active=True, person__user__isnull=False).exclude(
        person__user=user
    )
    if can_teach(user, site):
        return members
    if site_role(user, site) != Membership.SiteRole.STUDENT:
        return members.none()
    if settings.MESSAGING_STUDENT_TO_STUDENT:
        return members
    return members.filter(role__in=TEACHING_ROLES)


class RecipientSerializer(serializers.Serializer):
    person_id = serializers.IntegerField()
    name = serializers.CharField()
    role = serializers.ChoiceField(choices=Membership.SiteRole.choices)


class ParticipantSerializer(serializers.Serializer):
    name = serializers.CharField(allow_null=True)
    last_read_at = serializers.DateTimeField(allow_null=True)
    may_send = serializers.BooleanField()


class ConversationSerializer(serializers.ModelSerializer):
    site_code = serializers.CharField(source="site.code", read_only=True)
    unread = serializers.IntegerField(
        read_only=True, default=0, help_text="Messages from others I have not read"
    )
    may_send = serializers.SerializerMethodField(help_text="Whether I may send in it")

    class Meta:
        model = Conversation
        fields = (
            "id",
            "site",
            "site_code",
            "audience",
            "subject",
            "group",
            "last_message_at",
            "unread",
            "may_send",
        )
        read_only_fields = fields

    def get_may_send(self, obj) -> bool:
        return bool(getattr(obj, "mine_may_send", False))


@extend_schema_field(OpenApiTypes.INT)
class SiteField(serializers.PrimaryKeyRelatedField):
    """A site the caller can open; others read as "does not exist"."""

    def get_queryset(self):
        return visible_sites(self.context["request"].user)


class StartSerializer(serializers.Serializer):
    site = SiteField()
    audience = serializers.ChoiceField(
        choices=Conversation.Audience.choices, default=Conversation.Audience.DIRECT
    )
    subject = serializers.CharField(max_length=200)
    body = serializers.CharField()
    body_format = serializers.ChoiceField(choices=["html", "text"], default="text", write_only=True)
    recipients = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="Person ids for a direct conversation; a student who names none writes to all the teaching "
        "staff",
    )
    group = serializers.IntegerField(required=False, help_text="The group, for audience 'group'")
    client_sent_at = serializers.DateTimeField(required=False, allow_null=True)


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    mine = serializers.SerializerMethodField()
    read_by = serializers.SerializerMethodField(help_text="Names of the others who have read it")

    class Meta:
        model = Message
        fields = ("id", "sender_name", "mine", "body", "created_at", "client_sent_at", "read_by")
        read_only_fields = fields

    def get_sender_name(self, obj) -> str | None:
        return author_name(obj.sender)

    def get_mine(self, obj) -> bool:
        return obj.sender_id == self.context["request"].user.pk

    def get_read_by(self, obj) -> list[str]:
        return [
            author_name(p.user)
            for p in self.context["participants"]
            if p.user_id != obj.sender_id and p.last_read_at and p.last_read_at >= obj.created_at
        ]


class ConversationDetailSerializer(serializers.Serializer):
    conversation = ConversationSerializer()
    participants = ParticipantSerializer(many=True)
    messages = MessageSerializer(many=True)


class SendSerializer(serializers.Serializer):
    body = serializers.CharField()
    body_format = serializers.ChoiceField(choices=["html", "text"], default="text", write_only=True)
    client_sent_at = serializers.DateTimeField(
        required=False, allow_null=True, help_text="When it was written on the phone"
    )


class ReadSerializer(serializers.Serializer):
    last_read_at = serializers.DateTimeField()


def _notify(message: Message) -> None:
    from notifications.services import notify

    conversation = message.conversation
    others = get_user_model().objects.filter(
        pk__in=conversation.participants.exclude(user=message.sender).values("user"), is_active=True
    )
    notify(
        others,
        title=f"{conversation.site.code}: {conversation.subject}"[:160],
        body=f"New message from {author_name(message.sender)}",
        link=f"/messages/{conversation.id}",
        dedupe_key=f"message:{message.id}",
    )


def _create_message(request, conversation: Conversation, body: str, client_sent_at) -> Message:
    message = Message.objects.create(
        conversation=conversation,
        sender=request.user,
        body=body,
        client_sent_at=client_sent_at,
        created_by=request.user,
        updated_by=request.user,
    )
    conversation.last_message_at = message.created_at
    conversation.save(update_fields=["last_message_at", "updated_at"])
    Participant.objects.filter(conversation=conversation, user=request.user).update(
        last_read_at=message.created_at
    )
    record(request, "create", message, after=snapshot(message))
    _notify(message)
    return message


class ConversationViewSet(viewsets.GenericViewSet):
    """My conversations. Only participants ever see a conversation."""

    permission_classes = [RolePermission]
    serializer_class = ConversationSerializer
    queryset = Conversation.objects.none()

    def get_queryset(self):
        me = self.request.user
        return (
            Conversation.objects.filter(participants__user=me)
            .select_related("site")
            .annotate(
                mine_may_send=F("participants__may_send"),
                unread=Count(
                    "messages",
                    filter=~Q(messages__sender=me)
                    & (
                        Q(participants__last_read_at__isnull=True)
                        | Q(messages__created_at__gt=F("participants__last_read_at"))
                    ),
                    distinct=True,
                ),
            )
        )

    def _conversation(self, pk) -> Conversation:
        return get_object_or_404(self.get_queryset(), pk=pk)

    @extend_schema(
        parameters=[OpenApiParameter("site", OpenApiTypes.INT, description="Only this site")],
        responses=ConversationSerializer(many=True),
        summary="My conversations, the most recently active first",
    )
    def list(self, request):
        qs = self.get_queryset()
        if request.query_params.get("site"):
            qs = qs.filter(site_id=request.query_params["site"])
        return Response(ConversationSerializer(qs[:200], many=True).data)

    @extend_schema(
        request=StartSerializer,
        parameters=[IDEMPOTENCY_HEADER],
        responses={
            201: ConversationSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Start a conversation with its first message: a student to the teaching staff, teaching "
        "staff to members, a group or the whole site",
    )
    @idempotent
    def create(self, request):
        data = StartSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        v = data.validated_data
        site = v["site"]
        role = site_role(request.user, site)
        if role in (None, "auditor"):
            raise PermissionDenied("Only members of the course send messages on it.")
        require_conduct(request.user)
        client_sent_at = check_client_time(v.get("client_sent_at"))
        teaching = can_teach(request.user, site)
        audience = v["audience"]
        group = None
        if audience == Conversation.Audience.DIRECT:
            allowed = may_write_to(request.user, site)
            if v.get("recipients"):
                chosen = allowed.filter(person_id__in=v["recipients"])
                if chosen.count() != len(set(v["recipients"])):
                    if teaching or settings.MESSAGING_STUDENT_TO_STUDENT:
                        raise serializers.ValidationError({"recipients": ["Choose members of this course."]})
                    raise PermissionDenied(
                        "Students write to the course's teaching staff, not to other students."
                    )
            elif teaching:
                raise serializers.ValidationError({"recipients": ["Choose who to write to."]})
            else:
                chosen = allowed.filter(role__in=TEACHING_ROLES)
            members = list(chosen.select_related("person__user"))
            if not members:
                raise serializers.ValidationError(
                    {"recipients": ["Nobody on this course can receive it yet."]}
                )
            receivers = [(m.person.user, True) for m in members]
        else:
            if not teaching:
                raise PermissionDenied("Only teaching staff send a notice to a group or to the whole course.")
            members = Membership.objects.filter(
                site=site, is_active=True, person__user__isnull=False
            ).exclude(person__user=request.user)
            if audience == Conversation.Audience.GROUP:
                group = SiteGroup.objects.filter(site=site, pk=v.get("group")).first()
                if group is None:
                    raise serializers.ValidationError({"group": ["Choose a group of this course."]})
                members = members.filter(groups=group)
            receivers = [
                (m.person.user, m.role in TEACHING_ROLES) for m in members.select_related("person__user")
            ]
            if not receivers:
                raise serializers.ValidationError({"group": ["Nobody is in this group yet."]})
        body = rich_body(v["body"], v["body_format"], site)
        with transaction.atomic():
            conversation = Conversation.objects.create(
                site=site,
                audience=audience,
                subject=v["subject"],
                group=group,
                started_by=request.user,
                created_by=request.user,
                updated_by=request.user,
            )
            Participant.objects.create(conversation=conversation, user=request.user, may_send=True)
            Participant.objects.bulk_create(
                [Participant(conversation=conversation, user=u, may_send=s) for u, s in receivers]
            )
            record(
                request,
                "create",
                conversation,
                after={**snapshot(conversation), "participants": len(receivers) + 1},
            )
            _create_message(request, conversation, body, client_sent_at)
        return Response(ConversationSerializer(self._conversation(conversation.pk)).data, status=201)

    @extend_schema(
        responses={200: ConversationDetailSerializer, 404: ErrorSerializer},
        summary="A conversation with its messages and who has read them",
    )
    def retrieve(self, request, pk=None):
        conversation = self._conversation(pk)
        participants = list(conversation.participants.select_related("user__person"))
        context = {"request": request, "participants": participants}
        messages = conversation.messages.select_related("sender__person")
        return Response(
            {
                "conversation": ConversationSerializer(conversation).data,
                "participants": [
                    {"name": author_name(p.user), "last_read_at": p.last_read_at, "may_send": p.may_send}
                    for p in participants
                ],
                "messages": MessageSerializer(messages, many=True, context=context).data,
            }
        )

    @extend_schema(
        request=SendSerializer,
        parameters=[IDEMPOTENCY_HEADER],
        responses={
            201: MessageSerializer,
            400: OpenApiTypes.OBJECT,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Send a message in a conversation",
    )
    @action(detail=True, methods=["post"])
    @idempotent
    def messages(self, request, pk=None):
        conversation = self._conversation(pk)
        me = conversation.participants.get(user=request.user)
        if not me.may_send:
            raise PermissionDenied("This is a notice from the teaching staff. Start a conversation to reply.")
        if site_role(request.user, conversation.site) in (None, "auditor"):
            raise PermissionDenied("You are no longer a member of this course.")
        require_conduct(request.user)
        data = SendSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        client_sent_at = check_client_time(data.validated_data.get("client_sent_at"))
        body = rich_body(data.validated_data["body"], data.validated_data["body_format"], conversation.site)
        with transaction.atomic():
            message = _create_message(request, conversation, body, client_sent_at)
        participants = list(conversation.participants.select_related("user__person"))
        context = {"request": request, "participants": participants}
        return Response(MessageSerializer(message, context=context).data, status=201)

    @extend_schema(
        request=None,
        responses={200: ReadSerializer, 404: ErrorSerializer},
        summary="Mark the conversation read up to now (my read receipt)",
    )
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        conversation = self._conversation(pk)
        now = timezone.now()
        Participant.objects.filter(conversation=conversation, user=request.user).update(last_read_at=now)
        return Response({"last_read_at": now})

    @extend_schema(
        parameters=[OpenApiParameter("site", OpenApiTypes.INT, required=True)],
        responses={200: RecipientSerializer(many=True), 404: ErrorSerializer},
        summary="Who I may write to on a site",
    )
    @action(detail=False, methods=["get"])
    def recipients(self, request):
        site = get_object_or_404(visible_sites(request.user), pk=request.query_params.get("site") or 0)
        rows = may_write_to(request.user, site).select_related("person").order_by("role", "person__last_name")
        return Response(
            [{"person_id": m.person_id, "name": m.person.full_name, "role": m.role} for m in rows]
        )


router = DefaultRouter()
router.register("conversations", ConversationViewSet, basename="conversation")
urlpatterns = router.urls
