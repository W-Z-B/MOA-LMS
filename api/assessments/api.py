"""Assignments, submissions, marking and the gradebook."""

from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from assessments.models import Assignment, Mark, Submission
from assessments.services import gradebook
from audit.services import record
from courses.access import can_teach, person_of, site_role, visible_sites
from courses.api import TeachingViewSet
from courses.models import Membership
from iam.permissions import RolePermission


class AssignmentSerializer(serializers.ModelSerializer):
    my_submission = serializers.SerializerMethodField()
    submissions_count = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = (
            "id",
            "site",
            "title",
            "instructions",
            "opens_at",
            "due_at",
            "max_mark",
            "weight",
            "allow_late",
            "is_published",
            "my_submission",
            "submissions_count",
        )

    def get_my_submission(self, obj):
        request = self.context.get("request")
        person = person_of(request.user) if request else None
        if person is None:
            return None
        submission = obj.submissions.filter(student=person).select_related("mark").first()
        return SubmissionSerializer(submission, context={"released_only": True}).data if submission else None

    def get_submissions_count(self, obj):
        request = self.context.get("request")
        return obj.submissions.count() if request and can_teach(request.user, obj.site) else None


class SubmissionSerializer(serializers.ModelSerializer):
    student_no = serializers.CharField(source="student.external_id", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    filename = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    mark = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = (
            "id",
            "assignment",
            "student_no",
            "student_name",
            "text",
            "filename",
            "download_url",
            "submitted_at",
            "is_late",
            "mark",
        )

    def get_filename(self, obj):
        return obj.file.name.rsplit("/", 1)[-1] if obj.file else None

    def get_download_url(self, obj):
        return f"/api/v1/submissions/{obj.id}/download/" if obj.file else None

    def get_mark(self, obj):
        mark = getattr(obj, "mark", None)
        if mark is None or (self.context.get("released_only") and not mark.is_released):
            return None
        return {"mark": str(mark.mark), "feedback": mark.feedback, "is_released": mark.is_released}


class SubmitSerializer(serializers.Serializer):
    text = serializers.CharField(required=False, allow_blank=True)
    file = serializers.FileField(required=False)

    def validate(self, attrs):
        if not attrs.get("text") and not attrs.get("file"):
            raise serializers.ValidationError("Provide text or a file.")
        return attrs


class MarkSerializer(serializers.Serializer):
    mark = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
    feedback = serializers.CharField(required=False, allow_blank=True)
    is_released = serializers.BooleanField(required=False, default=False)


class AssignmentViewSet(TeachingViewSet):
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Assignment.objects.filter(site__in=visible_sites(user)).select_related("site")
        site = self.request.query_params.get("site")
        if site:
            qs = qs.filter(site_id=site)
        teaching_sites = [s.id for s in visible_sites(user) if can_teach(user, s)]
        return qs.filter(is_published=True) | qs.filter(site_id__in=teaching_sites)

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        assignment = self.get_object()
        person = person_of(request.user)
        if person is None or site_role(request.user, assignment.site) != Membership.SiteRole.STUDENT:
            raise PermissionDenied("Only students of this course can submit.")
        if not assignment.is_published:
            raise PermissionDenied("This assignment is not open.")
        now = timezone.now()
        if assignment.opens_at and now < assignment.opens_at:
            return Response({"code": "not_open", "detail": "The assignment has not opened yet."}, status=409)
        late = now > assignment.due_at
        if late and not assignment.allow_late:
            return Response({"code": "closed", "detail": "The deadline has passed."}, status=409)
        data = SubmitSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            existing = Submission.objects.filter(assignment=assignment, student=person).first()
            if existing and hasattr(existing, "mark"):
                return Response(
                    {"code": "already_marked", "detail": "A marked submission cannot be replaced."},
                    status=409,
                )
            submission, _ = Submission.objects.update_or_create(
                assignment=assignment,
                student=person,
                defaults={
                    "text": data.validated_data.get("text", ""),
                    "file": data.validated_data.get("file") or "",
                    "submitted_at": now,
                    "is_late": late,
                    "updated_by": request.user,
                },
            )
            record(request, "submit", submission, after={"assignment": assignment.id, "late": late})
        return Response(SubmissionSerializer(submission, context={"released_only": True}).data, status=201)

    @action(detail=True, methods=["get"])
    def submissions(self, request, pk=None):
        assignment = self.get_object()
        self._require_teaching(assignment.site)
        rows = assignment.submissions.select_related("student", "mark")
        return Response(SubmissionSerializer(rows, many=True).data)


@api_view(["POST"])
@permission_classes([RolePermission])
def mark_submission(request, pk: int):
    submission = get_object_or_404(Submission.objects.select_related("assignment__site", "student"), pk=pk)
    site = submission.assignment.site
    if not can_teach(request.user, site):
        raise PermissionDenied("Only the site's teaching staff can mark.")
    data = MarkSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    if data.validated_data["mark"] > submission.assignment.max_mark:
        return Response({"mark": [f"The maximum is {submission.assignment.max_mark}."]}, status=400)
    with transaction.atomic():
        mark, _ = Mark.objects.update_or_create(
            submission=submission,
            defaults={
                "mark": data.validated_data["mark"],
                "feedback": data.validated_data.get("feedback", ""),
                "is_released": data.validated_data["is_released"],
                "marked_by": person_of(request.user),
                "updated_by": request.user,
            },
        )
        record(request, "mark", submission, after={"mark": str(mark.mark), "released": mark.is_released})
    if mark.is_released and submission.student.user:
        from notifications.services import notify

        notify(
            [submission.student.user],
            title=f"Marked: {submission.assignment.title}",
            body=f"{site.code}: {mark.mark} out of {submission.assignment.max_mark}.",
            link=f"/sites/{site.id}",
            dedupe_key=f"mark:{mark.id}:released",
        )
    submission.refresh_from_db()
    return Response(SubmissionSerializer(submission).data)


@api_view(["GET"])
@permission_classes([RolePermission])
def download_submission(request, pk: int):
    submission = get_object_or_404(Submission.objects.select_related("assignment__site", "student"), pk=pk)
    own = person_of(request.user) is not None and submission.student_id == person_of(request.user).id
    if not own and not can_teach(request.user, submission.assignment.site):
        raise PermissionDenied("You cannot open this submission.")
    if not submission.file:
        return Response({"code": "no_file", "detail": "This submission has no file."}, status=404)
    record(request, "download", submission)
    return FileResponse(
        submission.file.open("rb"), as_attachment=True, filename=submission.file.name.rsplit("/", 1)[-1]
    )


@api_view(["GET"])
@permission_classes([RolePermission])
def site_gradebook(request, pk: int):
    site = get_object_or_404(visible_sites(request.user), pk=pk)
    role = site_role(request.user, site)
    if role == Membership.SiteRole.STUDENT:
        return Response(gradebook(site, only_person=person_of(request.user), released_only=True))
    if role is None:
        raise PermissionDenied("You are not a member of this course.")
    return Response(gradebook(site))


router = DefaultRouter()
router.register("assignments", AssignmentViewSet, basename="assignment")
urlpatterns = [
    path("submissions/<int:pk>/mark/", mark_submission, name="submission-mark"),
    path("submissions/<int:pk>/download/", download_submission, name="submission-download"),
    path("sites/<int:pk>/gradebook/", site_gradebook, name="site-gradebook"),
    *router.urls,
]
