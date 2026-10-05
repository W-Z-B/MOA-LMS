"""Assignments, submissions, marking and the gradebook."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, extend_schema_view
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from assessments.models import Assignment, Mark, Submission
from assessments.services import gradebook
from audit.services import record
from core.serializers import ErrorSerializer
from core.uploads import SUBMISSION, original_name, validate_upload
from courses.access import TaughtRecord, can_teach, person_of, site_role, taught_sites, visible_sites
from courses.api import TeachingViewSet
from courses.models import CourseSite, Membership
from iam.permissions import RolePermission


class ReleasedMarkSerializer(serializers.Serializer):
    """A mark as the submission shows it. Students see it only once it is released."""

    mark = serializers.CharField(help_text="Decimal, as a string")
    feedback = serializers.CharField()
    is_released = serializers.BooleanField()


class AssignmentSerializer(serializers.ModelSerializer):
    site = TaughtRecord(CourseSite)
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

    def get_my_submission(self, obj) -> dict | None:
        request = self.context.get("request")
        person = person_of(request.user) if request else None
        if person is None:
            return None
        submission = obj.submissions.filter(student=person).select_related("mark").first()
        return SubmissionSerializer(submission, context={"released_only": True}).data if submission else None

    def get_submissions_count(self, obj) -> int | None:
        request = self.context.get("request")
        return obj.submissions.count() if request and can_teach(request.user, obj.site) else None


class SubmissionSerializer(serializers.ModelSerializer):
    student_no = serializers.CharField(source="student.external_id", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    filename = serializers.SerializerMethodField(help_text="The name the file had when it was handed in")
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
            "client_submitted_at",
            "is_late",
            "mark",
        )

    def get_filename(self, obj) -> str | None:
        return (obj.original_name or obj.file.name.rsplit("/", 1)[-1]) if obj.file else None

    def get_download_url(self, obj) -> str | None:
        return f"/api/v1/submissions/{obj.id}/download/" if obj.file else None

    @extend_schema_field(ReleasedMarkSerializer(allow_null=True))
    def get_mark(self, obj) -> dict | None:
        mark = getattr(obj, "mark", None)
        if mark is None or (self.context.get("released_only") and not mark.is_released):
            return None
        return {"mark": str(mark.mark), "feedback": mark.feedback, "is_released": mark.is_released}


# A device clock may run a little fast; further ahead than this it is wrong (as practicals.offline).
CLIENT_AHEAD = timedelta(minutes=10)


class SubmitSerializer(serializers.Serializer):
    text = serializers.CharField(required=False, allow_blank=True)
    file = serializers.FileField(
        required=False,
        help_text="A PDF, a photograph, or a Word, Excel or PowerPoint file without macros; at most "
        "UPLOAD_LIMIT_SUBMISSION_MB (20 MB by default)",
    )
    client_submitted_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text="When the device handed it in, sent by the offline queue (item 4.02). Kept beside the "
        "server time, which alone decides lateness; refused when more than 10 minutes ahead of the server.",
    )

    def validate_file(self, upload):
        return validate_upload(upload, SUBMISSION)

    def validate_client_submitted_at(self, value):
        if value is not None and value > timezone.now() + CLIENT_AHEAD:
            raise serializers.ValidationError(
                "The device's clock is ahead of the server. Set it right and send again."
            )
        return value

    def validate(self, attrs):
        if not attrs.get("text") and not attrs.get("file"):
            raise serializers.ValidationError("Provide text or a file.")
        return attrs


class MarkSerializer(serializers.Serializer):
    mark = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
    feedback = serializers.CharField(required=False, allow_blank=True)
    is_released = serializers.BooleanField(required=False, default=False)


class GradebookAssignmentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    max_mark = serializers.CharField()
    weight = serializers.CharField()


class GradebookCellSerializer(serializers.Serializer):
    submitted = serializers.BooleanField()
    late = serializers.BooleanField()
    mark = serializers.CharField(allow_null=True)
    feedback = serializers.CharField()


class GradebookRowSerializer(serializers.Serializer):
    person_id = serializers.IntegerField()
    student_no = serializers.CharField()
    name = serializers.CharField()
    marks = serializers.DictField(child=GradebookCellSerializer(), help_text="Keyed by assignment id")
    coursework_percent = serializers.CharField(allow_null=True, help_text="Weighted, as a string")


class GradebookSerializer(serializers.Serializer):
    """Describes assessments.services.gradebook for the API documentation."""

    site = serializers.CharField(help_text="Site code")
    assignments = GradebookAssignmentSerializer(many=True)
    rows = GradebookRowSerializer(many=True)


@extend_schema_view(
    list=extend_schema(parameters=[OpenApiParameter("site", OpenApiTypes.INT, description="Only this site")])
)
class AssignmentViewSet(TeachingViewSet):
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Assignment.objects.filter(site__in=visible_sites(user)).select_related("site")
        site = self.request.query_params.get("site")
        if site:
            qs = qs.filter(site_id=site)
        return qs.filter(is_published=True) | qs.filter(site__in=taught_sites(user))

    def site_of(self, instance):
        return instance.site

    def site_from_data(self, data):
        return data["site"]

    @extend_schema(
        request={"multipart/form-data": SubmitSerializer, "application/json": SubmitSerializer},
        responses={
            201: SubmissionSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Hand in work for an assignment, or replace work not yet marked",
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        assignment = self.get_object()  # an assignment the student cannot open reads as unknown (404)
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
        upload = data.validated_data.get("file")
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
                    "file": upload or "",
                    "original_name": original_name(upload) if upload else "",
                    "submitted_at": now,
                    "client_submitted_at": data.validated_data.get("client_submitted_at"),
                    "is_late": late,
                    "updated_by": request.user,
                },
            )
            record(
                request,
                "submit",
                submission,
                after={
                    "assignment": assignment.id,
                    "late": late,
                    "client_submitted_at": submission.client_submitted_at.isoformat()
                    if submission.client_submitted_at
                    else None,
                },
            )
        return Response(SubmissionSerializer(submission, context={"released_only": True}).data, status=201)

    @extend_schema(
        responses={200: SubmissionSerializer(many=True), 403: ErrorSerializer},
        summary="All submissions (teaching staff)",
    )
    @action(detail=True, methods=["get"])
    def submissions(self, request, pk=None):
        assignment = self.get_object()
        self._require_teaching(assignment.site)
        rows = assignment.submissions.select_related("student", "mark")
        return Response(SubmissionSerializer(rows, many=True).data)


def visible_submissions(user):
    """A student's own submissions, and every submission on the sites the user teaches. Any other
    submission reads as unknown."""
    person = person_of(user)
    mine = Q(student=person) if person is not None else Q(pk__in=[])
    return Submission.objects.filter(mine | Q(assignment__site__in=taught_sites(user))).select_related(
        "assignment__site", "student"
    )


@extend_schema(
    request=MarkSerializer,
    responses={200: SubmissionSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Mark a submission, and release the mark to the student when ready",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def mark_submission(request, pk: int):
    # The site is settled before the mark is looked at (item 1.15): a submission on a site the caller does
    # not teach on is unknown to them, unless it is their own, which they still may not mark.
    submission = get_object_or_404(visible_submissions(request.user), pk=pk)
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


@extend_schema(
    responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 404: ErrorSerializer},
    summary="Download the file handed in, under the name it had",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def download_submission(request, pk: int):
    submission = get_object_or_404(visible_submissions(request.user), pk=pk)
    if not submission.file:
        return Response({"code": "no_file", "detail": "This submission has no file."}, status=404)
    record(request, "download", submission)
    return FileResponse(
        submission.file.open("rb"),
        as_attachment=True,
        filename=submission.original_name or submission.file.name.rsplit("/", 1)[-1],
    )


@extend_schema(
    responses={200: GradebookSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Gradebook: the whole class for teaching staff, own released marks for a student",
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
