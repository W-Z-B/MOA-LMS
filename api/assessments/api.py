"""Assignments, handing in, marking and the gradebook.

The marking screen's endpoints are in assessments.marking_api, the gradebook's in assessments.gradebook_api,
and extensions and accommodations in assessments.arrangements_api; their routes are joined here.
"""

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

from assessments import rules
from assessments.models import Assignment, GradeCategory, Submission, SubmissionAttempt, SubmissionFile
from assessments.services import gradebook
from audit.services import record
from core.serializers import ErrorSerializer
from core.uploads import SUBMISSION, narrowed, original_name, validate_upload
from courses.access import TaughtRecord, can_teach, person_of, site_role, taught_sites, visible_sites
from courses.api import TeachingViewSet
from courses.models import CourseSite, Membership, SiteGroup
from iam.permissions import RolePermission
from rubrics.models import Rubric


def refused(refusal: rules.Refusal) -> Response:
    return Response({"code": refusal.code, "detail": refusal.detail}, status=refusal.status)


class ReleasedMarkSerializer(serializers.Serializer):
    """A mark as the submission shows it. Students see it only once it is released."""

    mark = serializers.CharField(
        help_text="The mark that counts, after any late penalty; decimal as a string"
    )
    raw_mark = serializers.CharField(help_text="The mark the marker gave")
    penalty = serializers.CharField(help_text="Marks taken for lateness (item 2.35)")
    penalty_percent = serializers.CharField(help_text="The penalty as a percentage of the maximum mark")
    feedback = serializers.CharField()
    is_released = serializers.BooleanField()
    source = serializers.CharField(help_text="manual, rubric, upload, group or agreed")
    group_mark = serializers.CharField(allow_null=True)
    adjustment = serializers.CharField()
    rubric_scores = serializers.JSONField()


class FileSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    filename = serializers.CharField()
    size = serializers.IntegerField()
    sha256 = serializers.CharField()
    download_url = serializers.CharField()


class FeedbackFileSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    filename = serializers.CharField()
    kind = serializers.CharField(help_text="pdf, jpeg, docx ... or m4a, mp3, ogg, webm for recordings")
    is_audio = serializers.BooleanField()
    size = serializers.IntegerField()
    download_url = serializers.CharField()


def files_of(attempt) -> list[dict]:
    return [
        {
            "id": f.id,
            "filename": f.original_name,
            "size": f.size,
            "sha256": f.sha256,
            "download_url": f"/api/v1/submission-files/{f.id}/download/",
        }
        for f in attempt.files.all()
    ]


def feedback_files_of(submission) -> list[dict]:
    from core.uploads import AUDIO

    return [
        {
            "id": f.id,
            "filename": f.original_name,
            "kind": f.kind,
            "is_audio": f.kind in AUDIO,
            "size": f.size,
            "download_url": f"/api/v1/feedback-files/{f.id}/",
        }
        for f in submission.feedback_files.all()
    ]


class SubmissionSerializer(serializers.ModelSerializer):
    """A submission as its student (context released_only) or its markers see it. While an anonymous
    assignment's names are hidden, markers see a pseudonym in place of the student number and no name."""

    student_no = serializers.SerializerMethodField(help_text="The student number, or the pseudonym")
    student_name = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField(help_text="The group's name, for a group assignment")
    filename = serializers.SerializerMethodField(
        help_text="The name the first file had when it was handed in"
    )
    download_url = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField(help_text="The files of the latest attempt, the one marked")
    attempts = serializers.SerializerMethodField(help_text="How many times work was handed in")
    receipt = serializers.SerializerMethodField(help_text="The latest attempt's receipt code")
    due_at = serializers.SerializerMethodField(help_text="The student's due date, extensions included")
    extended = serializers.SerializerMethodField()
    accommodation_applies = serializers.SerializerMethodField(
        help_text="For markers only: an accommodation applies (never the reason); null for the student"
    )
    srms_locked_at = serializers.SerializerMethodField(
        help_text="When the SRMS took the student's coursework: the mark is locked from then (item 3.18)"
    )
    mark = serializers.SerializerMethodField()
    feedback_files = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = (
            "id",
            "assignment",
            "student_no",
            "student_name",
            "group",
            "text",
            "filename",
            "download_url",
            "files",
            "submitted_at",
            "client_submitted_at",
            "is_late",
            "due_at",
            "extended",
            "attempts",
            "receipt",
            "accommodation_applies",
            "srms_locked_at",
            "mark",
            "feedback_files",
        )

    def _hidden(self, obj) -> bool:
        return not self.context.get("released_only") and obj.assignment.names_hidden

    def _latest(self, obj):
        cached = getattr(obj, "_latest_attempt", None)
        if cached is None:
            cached = rules.attempts_of(obj).prefetch_related("files").last()
            obj._latest_attempt = cached
        return cached

    def get_student_no(self, obj) -> str:
        return rules.label_for(obj) if self._hidden(obj) else obj.student.external_id

    def get_student_name(self, obj) -> str:
        return "" if self._hidden(obj) else obj.student.full_name

    def get_group(self, obj) -> str | None:
        return obj.group.name if obj.group_id else None

    def get_filename(self, obj) -> str | None:
        return (obj.original_name or obj.file.name.rsplit("/", 1)[-1]) if obj.file else None

    def get_download_url(self, obj) -> str | None:
        return f"/api/v1/submissions/{obj.id}/download/" if obj.file else None

    @extend_schema_field(FileSerializer(many=True))
    def get_files(self, obj) -> list:
        latest = self._latest(obj)
        return files_of(latest) if latest else []

    def get_attempts(self, obj) -> int:
        return rules.attempts_of(obj).count()

    def get_receipt(self, obj) -> str | None:
        latest = self._latest(obj)
        return latest.receipt if latest else None

    def _due(self, obj):
        cached = getattr(obj, "_due", None)
        if cached is None:
            cached = rules.due_for(obj.assignment, obj.student)
            obj._due = cached
        return cached

    def get_due_at(self, obj) -> str:
        return self._due(obj).at.isoformat()

    def get_extended(self, obj) -> bool:
        return self._due(obj).extended

    def get_accommodation_applies(self, obj) -> bool | None:
        return None if self.context.get("released_only") else rules.accommodation_applies(obj.student)

    def get_srms_locked_at(self, obj) -> str | None:
        lock = rules.srms_lock(obj.assignment.site, obj.student)
        return lock.sent_at.isoformat() if lock else None

    @extend_schema_field(ReleasedMarkSerializer(allow_null=True))
    def get_mark(self, obj) -> dict | None:
        mark = getattr(obj, "mark", None)
        if mark is None or (self.context.get("released_only") and not mark.is_released):
            return None
        shown = rules.penalised(obj, mark.mark, self._due(obj))
        return {
            "mark": str(shown.final),
            "raw_mark": str(shown.raw),
            "penalty": str(shown.penalty),
            "penalty_percent": str(shown.percent),
            "feedback": mark.feedback,
            "is_released": mark.is_released,
            "source": mark.source,
            "group_mark": str(mark.group_mark) if mark.group_mark is not None else None,
            "adjustment": str(mark.adjustment),
            "rubric_scores": mark.rubric_scores,
        }

    @extend_schema_field(FeedbackFileSerializer(many=True))
    def get_feedback_files(self, obj) -> list:
        mark = getattr(obj, "mark", None)
        if self.context.get("released_only") and (mark is None or not mark.is_released):
            return []
        return feedback_files_of(obj)


class AssignmentSerializer(serializers.ModelSerializer):
    site = TaughtRecord(CourseSite)
    category = serializers.PrimaryKeyRelatedField(
        queryset=GradeCategory.objects.all(), required=False, allow_null=True, help_text="Gradebook category"
    )
    groups = serializers.PrimaryKeyRelatedField(
        queryset=SiteGroup.objects.all(), many=True, required=False, help_text="Groups that take part"
    )
    rubric = serializers.PrimaryKeyRelatedField(
        queryset=Rubric.objects.all(),
        required=False,
        allow_null=True,
        help_text="A rubric or marking guide of the same site (copy a library rubric to the site first)",
    )
    accepted_kinds = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(SUBMISSION.kinds)),
        required=False,
        help_text="File kinds accepted; empty accepts every kind a submission may be",
    )
    accepts = serializers.SerializerMethodField(help_text="What files are accepted, said in words")
    upload_limit_mb = serializers.SerializerMethodField(help_text="The size limit of each file, in MB")
    integrity_statement = serializers.SerializerMethodField(
        help_text="The statement accepted with each hand-in, when the assignment asks for it"
    )
    rubric_detail = serializers.SerializerMethodField(help_text="The rubric, shown with the assignment")
    my_due_at = serializers.SerializerMethodField(help_text="The caller's own due date, extensions included")
    my_submission = serializers.SerializerMethodField()
    submissions_count = serializers.SerializerMethodField()
    peer_review = serializers.SerializerMethodField(
        help_text="Peer review (item 4.13): {reviews_due_at, allocated, released}, or null when it has none"
    )

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
            "category",
            "allow_resubmission",
            "accepted_kinds",
            "max_files",
            "accepts",
            "upload_limit_mb",
            "requires_integrity",
            "integrity_statement",
            "late_penalty",
            "late_penalty_percent",
            "late_penalty_cap",
            "is_group",
            "groups",
            "rubric",
            "rubric_detail",
            "anonymous",
            "moderation",
            "marks_released_at",
            "my_due_at",
            "my_submission",
            "submissions_count",
            "peer_review",
        )
        read_only_fields = ("marks_released_at",)

    def validate(self, attrs):
        site = attrs.get("site") or getattr(self.instance, "site", None)
        category = attrs.get("category")
        if category is not None and category.site_id != site.id:
            raise serializers.ValidationError({"category": ["Choose a category of the same course."]})
        for group in attrs.get("groups", []):
            if group.site_id != site.id:
                raise serializers.ValidationError({"groups": ["Choose groups of the same course."]})
        rubric = attrs.get("rubric")
        if rubric is not None and rubric.site_id != site.id:
            raise serializers.ValidationError(
                {"rubric": ["Choose a rubric of the same course; copy one from the library first."]}
            )
        rule = attrs.get("late_penalty", getattr(self.instance, "late_penalty", Assignment.LatePenalty.NONE))
        rate = attrs.get("late_penalty_percent", getattr(self.instance, "late_penalty_percent", 0))
        if rule != Assignment.LatePenalty.NONE and not rate:
            raise serializers.ValidationError({"late_penalty_percent": ["Give the percentage taken."]})
        if self.instance is not None and self.instance.submissions.exists():
            for name in ("is_group", "anonymous"):
                if name in attrs and attrs[name] != getattr(self.instance, name):
                    raise serializers.ValidationError(
                        {name: ["This cannot change once work has been handed in."]}
                    )
        return attrs

    def get_accepts(self, obj) -> str:
        return narrowed(SUBMISSION, obj.accepted_kinds).accepts

    def get_upload_limit_mb(self, obj) -> int:
        return SUBMISSION.limit_mb

    def get_integrity_statement(self, obj) -> str | None:
        return rules.INTEGRITY_STATEMENT if obj.requires_integrity else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_rubric_detail(self, obj) -> dict | None:
        from rubrics.api import rubric_for_students

        return rubric_for_students(obj.rubric) if obj.rubric_id else None

    def _person(self):
        request = self.context.get("request")
        return person_of(request.user) if request else None

    def get_my_due_at(self, obj) -> str | None:
        person = self._person()
        if person is None:
            return None
        return rules.due_for(obj, person).at.isoformat()

    @extend_schema_field(SubmissionSerializer(allow_null=True))
    def get_my_submission(self, obj) -> dict | None:
        person = self._person()
        if person is None:
            return None
        submission = (
            obj.submissions.filter(student=person).select_related("mark", "assignment", "student").first()
        )
        return SubmissionSerializer(submission, context={"released_only": True}).data if submission else None

    def get_submissions_count(self, obj) -> int | None:
        request = self.context.get("request")
        return obj.submissions.count() if request and can_teach(request.user, obj.site) else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_peer_review(self, obj) -> dict | None:
        setup = getattr(obj, "peer_review", None)
        if setup is None:
            return None
        return {
            "reviews_due_at": setup.reviews_due_at.isoformat(),
            "allocated": setup.allocated_at is not None,
            "released": setup.released_at is not None,
        }


# A device clock may run a little fast; further ahead than this it is wrong (as practicals.offline).
CLIENT_AHEAD = timedelta(minutes=10)


class SubmitSerializer(serializers.Serializer):
    text = serializers.CharField(required=False, allow_blank=True)
    files = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        help_text="Up to the assignment's max_files files of the kinds it accepts, each at most "
        "UPLOAD_LIMIT_SUBMISSION_MB (20 MB by default)",
    )
    file = serializers.FileField(required=False, help_text="One file; the older way of sending a single file")
    integrity_accepted = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Required when the assignment asks for the integrity statement",
    )
    client_submitted_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text="When the device handed it in, sent by the offline queue (item 4.02). Kept beside the "
        "server time, which alone decides lateness; refused when more than 10 minutes ahead of the server.",
    )

    def validate_client_submitted_at(self, value):
        if value is not None and value > timezone.now() + CLIENT_AHEAD:
            raise serializers.ValidationError(
                "The device's clock is ahead of the server. Set it right and send again."
            )
        return value


class MarkSerializer(serializers.Serializer):
    mark = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
    feedback = serializers.CharField(required=False, allow_blank=True)
    is_released = serializers.BooleanField(
        required=False, default=False, help_text="false keeps the mark and feedback as a draft"
    )


class GradebookAssignmentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    max_mark = serializers.CharField()
    weight = serializers.CharField()
    category = serializers.IntegerField(allow_null=True)


class GradebookCellSerializer(serializers.Serializer):
    submitted = serializers.BooleanField()
    late = serializers.BooleanField()
    mark = serializers.CharField(allow_null=True, help_text="The mark that counts, after any late penalty")
    raw_mark = serializers.CharField(allow_null=True)
    penalty = serializers.CharField(allow_null=True)
    feedback = serializers.CharField()
    anonymous = serializers.BooleanField(help_text="Hidden while an anonymous assignment's names are hidden")


class GradebookCategorySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    weight = serializers.CharField()
    drop_lowest = serializers.IntegerField()


class GradebookColumnSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    weight = serializers.CharField()
    category = serializers.IntegerField(allow_null=True)


class GradebookItemCellSerializer(serializers.Serializer):
    state = serializers.CharField(help_text="graded, zero, pending, not_due or dropped")
    percent = serializers.CharField(allow_null=True)


class GradebookSrmsSerializer(serializers.Serializer):
    outcome = serializers.CharField(help_text="What the SRMS last answered: accepted, locked or unknown")
    percent = serializers.CharField(help_text="The coursework total sent")
    sent_at = serializers.DateTimeField()
    locked_since = serializers.DateTimeField(
        allow_null=True, help_text="Since when the student's marks on the site are locked (item 3.18)"
    )


class GradebookRowSerializer(serializers.Serializer):
    person_id = serializers.IntegerField()
    student_no = serializers.CharField()
    name = serializers.CharField()
    marks = serializers.DictField(child=GradebookCellSerializer(), help_text="Keyed by assignment id")
    quizzes = serializers.DictField(child=serializers.JSONField(), help_text="Keyed by quiz id")
    practicals = serializers.DictField(child=GradebookItemCellSerializer(), help_text="Keyed by task id")
    forums = serializers.DictField(child=GradebookItemCellSerializer(), help_text="Keyed by forum id")
    packages = serializers.DictField(
        child=GradebookItemCellSerializer(), help_text="Keyed by package id (SCORM and H5P, item 5.12)"
    )
    tools = serializers.DictField(
        child=GradebookItemCellSerializer(), help_text="Keyed by line item id: outside tools (item 6.07)"
    )
    categories = serializers.DictField(
        child=serializers.CharField(allow_null=True), help_text="Percent per category id"
    )
    coursework_percent = serializers.CharField(allow_null=True, help_text="Weighted, as a string")
    srms = GradebookSrmsSerializer(allow_null=True, help_text="The last sending to the SRMS, if any")


class GradebookSerializer(serializers.Serializer):
    """Describes assessments.services.gradebook for the API documentation."""

    site = serializers.CharField(help_text="Site code")
    categories = GradebookCategorySerializer(many=True)
    assignments = GradebookAssignmentSerializer(many=True)
    quizzes = serializers.ListField(child=serializers.JSONField())
    practicals = GradebookColumnSerializer(many=True, help_text="Practical tasks that count")
    forums = GradebookColumnSerializer(many=True, help_text="Graded forums that count")
    packages = GradebookColumnSerializer(many=True, help_text="SCORM and H5P packages that count")
    tools = GradebookColumnSerializer(
        many=True, help_text="Columns outside tools post scores to; weight 0 shows but does not count"
    )
    rows = GradebookRowSerializer(many=True)


def _students_of_group(group) -> list:
    return [
        m.person
        for m in group.members.filter(is_active=True, role=Membership.SiteRole.STUDENT).select_related(
            "person"
        )
    ]


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
        summary="Hand in work: text and up to max_files files; each hand-in is kept with a receipt",
        description="Work may be handed in again until the student's due date while it is not marked, when "
        "the assignment allows it; the latest attempt is the one marked (items 2.21, 2.22, 3.22). For a "
        "group assignment one member hands in for the whole group (item 2.27). Refusals: not_open, closed, "
        "already_submitted, already_marked, no_group, integrity_required, too_many_files.",
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
        due = rules.due_for(assignment, person)
        late = now > due.at
        if late and not assignment.allow_late:
            return Response({"code": "closed", "detail": "The deadline has passed."}, status=409)
        group = rules.group_of(assignment, person)
        if assignment.is_group and group is None:
            return Response(
                {
                    "code": "no_group",
                    "detail": "You are not in one group of this assignment. Ask your lecturer.",
                },
                status=409,
            )
        data = SubmitSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        uploads = self._checked_uploads(assignment, data.validated_data)
        text = data.validated_data.get("text", "")
        if not text and not uploads:
            raise serializers.ValidationError("Provide text or a file.")
        if assignment.requires_integrity and not data.validated_data["integrity_accepted"]:
            return Response(
                {
                    "code": "integrity_required",
                    "detail": "Accept the academic integrity statement to hand in.",
                },
                status=400,
            )
        members = _students_of_group(group) if group else [person]
        with transaction.atomic():
            existing = list(
                Submission.objects.select_for_update(of=("self",))
                .filter(assignment=assignment, student__in=members)
                .select_related("mark")
            )
            if any(hasattr(s, "mark") for s in existing):
                return Response(
                    {"code": "already_marked", "detail": "A marked submission cannot be replaced."},
                    status=409,
                )
            if existing and not assignment.allow_resubmission:
                return Response(
                    {
                        "code": "already_submitted",
                        "detail": "Work for this assignment can be handed in once.",
                    },
                    status=409,
                )
            if existing and late:
                return Response(
                    {"code": "closed", "detail": "The due date has passed, so the work cannot be replaced."},
                    status=409,
                )
            own, attempt = self._hand_in(
                request, assignment, person, group, members, text, uploads, now, data
            )
        _send_receipt(person, assignment, attempt)
        return Response(SubmissionSerializer(own, context={"released_only": True}).data, status=201)

    def _checked_uploads(self, assignment, validated) -> list:
        policy = narrowed(SUBMISSION, assignment.accepted_kinds)
        uploads = []
        if validated.get("file"):
            try:
                uploads.append(validate_upload(validated["file"], policy))
            except serializers.ValidationError as error:
                raise serializers.ValidationError({"file": error.detail}) from error
        for upload in validated.get("files", []):
            try:
                uploads.append(validate_upload(upload, policy))
            except serializers.ValidationError as error:
                raise serializers.ValidationError({"files": [f"{upload.name}: {error.detail[0]}"]}) from error
        if len(uploads) > assignment.max_files:
            limit = assignment.max_files
            raise serializers.ValidationError(
                {
                    "files": [
                        f"Send at most {limit} file{'s' if limit != 1 else ''}."
                        if limit
                        else "Send text only."
                    ]
                }
            )
        return uploads

    def _hand_in(self, request, assignment, person, group, members, text, uploads, now, data):
        due = rules.due_for(assignment, person)
        own, _ = Submission.objects.get_or_create(
            assignment=assignment,
            student=person,
            defaults={"submitted_at": now, "created_by": request.user, "group": group},
        )
        own.group = group
        number = (
            rules.attempts_of(own).order_by("-number").values_list("number", flat=True).first() or 0
        ) + 1
        hashes = [(original_name(u), rules.file_sha256(u)) for u in uploads]
        client_at = data.validated_data.get("client_submitted_at")
        attempt = SubmissionAttempt.objects.create(
            submission=own,
            number=number,
            submitted_by=person,
            submitted_at=now,
            client_submitted_at=client_at,
            text=text,
            is_late=now > due.at,
            receipt=rules.new_receipt(),
            content_hash=rules.content_hash(text, hashes),
            integrity_statement=rules.INTEGRITY_STATEMENT
            if data.validated_data["integrity_accepted"]
            else "",
        )
        stored = []
        for position, (upload, (name, sha)) in enumerate(zip(uploads, hashes, strict=True), start=1):
            stored.append(
                SubmissionFile.objects.create(
                    attempt=attempt,
                    position=position,
                    file=upload,
                    original_name=name,
                    size=upload.size,
                    sha256=sha,
                )
            )
        first = stored[0] if stored else None
        for member in members:
            member_due = due if member == person else rules.due_for(assignment, member)
            submission, created = Submission.objects.update_or_create(
                assignment=assignment,
                student=member,
                defaults={
                    "text": text,
                    "file": first.file.name if first else "",
                    "original_name": first.original_name if first else "",
                    "submitted_at": now,
                    "client_submitted_at": client_at,
                    "is_late": now > member_due.at,
                    "group": group,
                    "updated_by": request.user,
                },
            )
            record(
                request,
                "submit",
                submission,
                after={
                    "assignment": assignment.id,
                    "late": submission.is_late,
                    "attempt": number,
                    "receipt": attempt.receipt,
                    "content_hash": attempt.content_hash,
                    "files": [f.original_name for f in stored],
                    "integrity_accepted": bool(attempt.integrity_statement),
                    "group": group.id if group else None,
                    "client_submitted_at": client_at.isoformat() if client_at else None,
                },
            )
            if member == person:
                own = submission
        return own, attempt

    @extend_schema(
        responses={200: SubmissionSerializer(many=True), 403: ErrorSerializer},
        summary="All submissions (teaching staff); pseudonyms in place of names while marking is anonymous",
    )
    @action(detail=True, methods=["get"])
    def submissions(self, request, pk=None):
        assignment = self.get_object()
        self._require_teaching(assignment.site)
        rows = sorted(
            assignment.submissions.select_related("student", "mark", "assignment", "group"),
            key=lambda s: rules.label_for(s),
        )
        return Response(SubmissionSerializer(rows, many=True).data)


def _send_receipt(person, assignment, attempt) -> None:
    from notifications.models import Notification
    from notifications.services import notify

    if person.user is None:
        return
    when = timezone.localtime(attempt.submitted_at)
    notify(
        [person.user],
        title=f"Received: {assignment.title}",
        body=f"{assignment.site.code}: handed in at {when:%d/%m/%Y %H:%M}. "
        f"Receipt {attempt.receipt}; content fingerprint {attempt.content_hash[:16]}.",
        link=f"/sites/{assignment.site_id}",
        kind=Notification.Kind.RECEIPT,
        dedupe_key=f"receipt:{attempt.receipt}",
    )


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
    responses={
        200: SubmissionSerializer,
        400: ErrorSerializer,
        403: ErrorSerializer,
        404: ErrorSerializer,
        409: ErrorSerializer,
    },
    summary="Mark a submission; keep it as a draft or release it to the student",
    description="Refused above the maximum (above_max), once the SRMS holds the student's coursework "
    "(locked_in_srms), and, for a release, while a second marking is not agreed (moderation_outstanding). "
    "Every change is kept in the submission's history.",
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
    try:
        with transaction.atomic():
            mark = rules.save_mark(
                request,
                submission,
                mark=data.validated_data["mark"],
                feedback=data.validated_data.get("feedback", ""),
                is_released=data.validated_data["is_released"],
            )
    except rules.Refusal as refusal:
        return refused(refusal)
    if mark.is_released:
        rules.notify_released(mark)
    submission.refresh_from_db()
    return Response(SubmissionSerializer(submission).data)


@extend_schema(
    responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 404: ErrorSerializer},
    summary="Download the first file of the latest hand-in, under the name it had",
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


def _routes():
    from assessments import arrangements_api, gradebook_api, marking_api

    router = DefaultRouter()
    router.register("assignments", AssignmentViewSet, basename="assignment")
    router.register("grade-categories", gradebook_api.GradeCategoryViewSet, basename="grade-category")
    router.register("extensions", arrangements_api.ExtensionViewSet, basename="extension")
    router.register("accommodations", arrangements_api.AccommodationViewSet, basename="accommodation")
    return [
        path("submissions/<int:pk>/mark/", mark_submission, name="submission-mark"),
        path("submissions/<int:pk>/download/", download_submission, name="submission-download"),
        path("sites/<int:pk>/gradebook/", site_gradebook, name="site-gradebook"),
        *marking_api.urlpatterns,
        *gradebook_api.urlpatterns,
        *router.urls,
    ]


urlpatterns = _routes()
