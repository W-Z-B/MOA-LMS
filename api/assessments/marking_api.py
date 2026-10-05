"""The marking screen's endpoints (Canvas SpeedGrader and Moodle's assignment grader are the reference).

Moving from one student to the next, drafts and release (2.23), feedback files and recordings (2.24), every
submission in one archive and marks from a spreadsheet (2.25), group marks (2.27), rubrics and marking
guides (3.09, 3.10), moderation (3.17), receipts and the history kept for appeals (2.21, 3.19).
"""

import csv
import hashlib
import io
import random
import tempfile
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import PurePath

from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from assessments import rules
from assessments.api import (
    FileSerializer,
    SubmissionSerializer,
    files_of,
    refused,
    visible_submissions,
)
from assessments.models import (
    Assignment,
    FeedbackFile,
    Mark,
    MarkVersion,
    Moderation,
    Submission,
    SubmissionAttempt,
    SubmissionFile,
)
from audit.services import record
from core.serializers import ErrorSerializer
from core.uploads import FEEDBACK, original_name, sniff, validate_upload
from courses.access import can_teach, person_of, visible_sites
from courses.models import Membership, SiteGroup
from iam.permissions import RolePermission

MAX_CSV_BYTES = 2 * 1024 * 1024
STUDENT_HEADERS = ("student_no", "student number", "student_number", "student", "candidate")


def _staff_submission(request, pk: int) -> Submission:
    """A submission the caller marks: unknown (404) when they cannot see it, refused when it is their own."""
    submission = get_object_or_404(visible_submissions(request.user), pk=pk)
    if not can_teach(request.user, submission.assignment.site):
        raise PermissionDenied("Only the site's teaching staff can do this.")
    return submission


def _staff_assignment(request, pk: int) -> Assignment:
    assignment = get_object_or_404(
        Assignment.objects.filter(site__in=visible_sites(request.user)).select_related("site"), pk=pk
    )
    if not can_teach(request.user, assignment.site):
        raise PermissionDenied("Only the site's teaching staff can do this.")
    return assignment


def _ordered(assignment) -> list[Submission]:
    """The assignment's submissions in marking order: by student number, or by pseudonym while hidden."""
    rows = assignment.submissions.select_related("student", "assignment", "mark")
    return sorted(rows, key=rules.label_for)


def _can_see_attempt(user, attempt: SubmissionAttempt) -> bool:
    submission = attempt.submission
    if can_teach(user, submission.assignment.site):
        return True
    person = person_of(user)
    if person is None:
        return False
    if submission.student_id == person.id:
        return True
    # A member of the group sees the group's hand-ins.
    return bool(
        submission.group_id
        and Submission.objects.filter(
            assignment_id=submission.assignment_id, group_id=submission.group_id, student=person
        ).exists()
    )


# ---------------------------------------------------------------------------------------------------------
# Receipts and history (items 2.21, 3.19)


class AttemptSerializer(serializers.Serializer):
    number = serializers.IntegerField()
    submitted_at = serializers.DateTimeField()
    submitted_by = serializers.CharField(help_text="Who handed in: a student number, or the pseudonym")
    is_late = serializers.BooleanField()
    receipt = serializers.CharField()
    content_hash = serializers.CharField(help_text="SHA-256 of the text and every file, in order")
    integrity_accepted = serializers.BooleanField()
    text = serializers.CharField()
    files = FileSerializer(many=True)
    is_marked_attempt = serializers.BooleanField(help_text="The latest attempt is the one marked")


class MarkVersionSerializer(serializers.Serializer):
    mark = serializers.CharField()
    feedback = serializers.CharField()
    is_released = serializers.BooleanField()
    source = serializers.CharField()
    rubric_scores = serializers.JSONField()
    changed_by = serializers.CharField(allow_null=True)
    changed_at = serializers.DateTimeField()


class ModerationSerializer(serializers.Serializer):
    first_mark = serializers.CharField(allow_null=True)
    second_mark = serializers.CharField(allow_null=True)
    second_note = serializers.CharField()
    agreed_mark = serializers.CharField(allow_null=True)
    agreed_note = serializers.CharField()
    agreed_at = serializers.DateTimeField(allow_null=True)


class HistorySerializer(serializers.Serializer):
    submission = serializers.IntegerField()
    attempts = AttemptSerializer(many=True)
    marks = MarkVersionSerializer(
        many=True, help_text="Every version (teaching staff); released ones (student)"
    )
    moderation = ModerationSerializer(allow_null=True, help_text="Teaching staff only")


def _attempt_row(attempt, label: str, latest_id: int) -> dict:
    return {
        "number": attempt.number,
        "submitted_at": attempt.submitted_at,
        "submitted_by": label,
        "is_late": attempt.is_late,
        "receipt": attempt.receipt,
        "content_hash": attempt.content_hash,
        "integrity_accepted": bool(attempt.integrity_statement),
        "text": attempt.text,
        "files": files_of(attempt),
        "is_marked_attempt": attempt.id == latest_id,
    }


def _moderation_row(moderation) -> dict | None:
    if moderation is None:
        return None
    return {
        "first_mark": str(moderation.first_mark) if moderation.first_mark is not None else None,
        "second_mark": str(moderation.second_mark) if moderation.second_mark is not None else None,
        "second_note": moderation.second_note,
        "agreed_mark": str(moderation.agreed_mark) if moderation.agreed_mark is not None else None,
        "agreed_note": moderation.agreed_note,
        "agreed_at": moderation.agreed_at,
    }


@extend_schema(
    responses={200: HistorySerializer, 404: ErrorSerializer},
    summary="A submission's history: every hand-in with its receipt, and every version of its mark",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def submission_history(request, pk: int):
    submission = get_object_or_404(visible_submissions(request.user), pk=pk)
    staff = can_teach(request.user, submission.assignment.site)
    attempts = list(rules.attempts_of(submission).select_related("submitted_by").prefetch_related("files"))
    latest_id = attempts[-1].id if attempts else 0
    hidden = staff and submission.assignment.names_hidden
    versions = MarkVersion.objects.filter(submission=submission).select_related("changed_by")
    if not staff:
        versions = versions.filter(is_released=True)
    data = {
        "submission": submission.id,
        "attempts": [
            _attempt_row(
                a,
                rules.pseudonym(submission.assignment, a.submitted_by)
                if hidden
                else a.submitted_by.external_id,
                latest_id,
            )
            for a in attempts
        ],
        "marks": [
            {
                "mark": str(v.mark),
                "feedback": v.feedback,
                "is_released": v.is_released,
                "source": v.source,
                "rubric_scores": v.rubric_scores,
                "changed_by": (v.changed_by.get_full_name() or v.changed_by.username)
                if staff and v.changed_by
                else None,
                "changed_at": v.changed_at,
            }
            for v in versions
        ],
        "moderation": _moderation_row(getattr(submission, "moderation", None)) if staff else None,
    }
    return Response(HistorySerializer(data).data)


class ReceiptSerializer(serializers.Serializer):
    receipt = serializers.CharField()
    site = serializers.CharField()
    assignment = serializers.CharField()
    student_no = serializers.CharField()
    attempt = serializers.IntegerField()
    submitted_at = serializers.DateTimeField()
    is_late = serializers.BooleanField()
    content_hash = serializers.CharField()
    files = FileSerializer(many=True)


@extend_schema(
    responses={200: ReceiptSerializer, 404: ErrorSerializer},
    summary="Look up a receipt: what was handed in, when, and its content fingerprint",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def receipt(request, code: str):
    attempt = (
        SubmissionAttempt.objects.select_related("submission__assignment__site", "submitted_by")
        .filter(receipt=code.strip().upper())
        .first()
    )
    if attempt is None or not _can_see_attempt(request.user, attempt):
        return Response({"code": "not_found", "detail": "No such receipt."}, status=404)
    assignment = attempt.submission.assignment
    staff_hidden = can_teach(request.user, assignment.site) and assignment.names_hidden
    data = {
        "receipt": attempt.receipt,
        "site": assignment.site.code,
        "assignment": assignment.title,
        "student_no": rules.pseudonym(assignment, attempt.submitted_by)
        if staff_hidden
        else attempt.submitted_by.external_id,
        "attempt": attempt.number,
        "submitted_at": attempt.submitted_at,
        "is_late": attempt.is_late,
        "content_hash": attempt.content_hash,
        "files": files_of(attempt),
    }
    return Response(ReceiptSerializer(data).data)


@extend_schema(
    responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 404: ErrorSerializer},
    summary="Download one file of a hand-in, under the name it had",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def download_file(request, pk: int):
    stored = (
        SubmissionFile.objects.select_related("attempt__submission__assignment__site").filter(pk=pk).first()
    )
    if stored is None or not _can_see_attempt(request.user, stored.attempt):
        return Response({"code": "not_found", "detail": "No such file."}, status=404)
    record(request, "download", stored.attempt.submission, after={"file": stored.original_name})
    return FileResponse(stored.file.open("rb"), as_attachment=True, filename=stored.original_name)


# ---------------------------------------------------------------------------------------------------------
# Moving through the class, and release (item 2.23)


class NeighboursSerializer(serializers.Serializer):
    position = serializers.IntegerField(help_text="This submission's place in marking order, from 1")
    total = serializers.IntegerField()
    previous = serializers.IntegerField(allow_null=True)
    next = serializers.IntegerField(allow_null=True)
    previous_unmarked = serializers.IntegerField(allow_null=True)
    next_unmarked = serializers.IntegerField(allow_null=True)


@extend_schema(
    responses={200: NeighboursSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="The previous and next submissions in marking order, and the nearest not yet marked",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def neighbours(request, pk: int):
    submission = _staff_submission(request, pk)
    rows = _ordered(submission.assignment)
    index = next(i for i, s in enumerate(rows) if s.id == submission.id)

    def unmarked(candidates):
        return next((s.id for s in candidates if not hasattr(s, "mark")), None)

    return Response(
        {
            "position": index + 1,
            "total": len(rows),
            "previous": rows[index - 1].id if index > 0 else None,
            "next": rows[index + 1].id if index + 1 < len(rows) else None,
            "previous_unmarked": unmarked(reversed(rows[:index])),
            "next_unmarked": unmarked(rows[index + 1 :]),
        }
    )


class MarksReleasedSerializer(serializers.Serializer):
    released = serializers.IntegerField(help_text="How many marks were released now")


@extend_schema(
    request=None,
    responses={
        200: MarksReleasedSerializer,
        403: ErrorSerializer,
        404: ErrorSerializer,
        409: ErrorSerializer,
    },
    summary="Release every mark of the assignment to the students, with their feedback",
    description="Refused (moderation_outstanding) while a second marking is not agreed. Releasing also ends "
    "anonymous marking: markers then see names.",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def release_all(request, pk: int):
    assignment = _staff_assignment(request, pk)
    marks = list(
        Mark.objects.filter(submission__assignment=assignment, is_released=False).select_related(
            "submission__assignment", "submission__student"
        )
    )
    waiting = [m.submission for m in marks if rules.moderation_outstanding(m.submission)]
    if waiting:
        return Response(
            {
                "code": "moderation_outstanding",
                "detail": f"Second markings not yet agreed: {len(waiting)}.",
            },
            status=409,
        )
    with transaction.atomic():
        for mark in marks:
            mark.is_released = True
            mark.updated_by = request.user
            mark.save(update_fields=["is_released", "updated_by", "updated_at"])
            MarkVersion.objects.create(
                submission=mark.submission,
                mark=mark.mark,
                feedback=mark.feedback,
                is_released=True,
                source=mark.source,
                rubric_scores=mark.rubric_scores,
                changed_by=request.user,
            )
            record(request, "mark", mark.submission, after={"mark": str(mark.mark), "released": True})
        assignment.marks_released_at = timezone.now()
        assignment.save(update_fields=["marks_released_at", "updated_at"])
        record(request, "marks_released", assignment, after={"released": len(marks)})
    for mark in marks:
        rules.notify_released(mark)
    return Response({"released": len(marks)})


# ---------------------------------------------------------------------------------------------------------
# Marking by rubric or guide, and group marks (items 3.09, 3.10, 2.27)


class RubricScoreSerializer(serializers.Serializer):
    criterion = serializers.IntegerField()
    level = serializers.IntegerField(required=False, allow_null=True, help_text="Rubrics: the level chosen")
    points = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="Marking guides: the points",
    )
    comment = serializers.CharField(required=False, allow_blank=True)


class RubricMarkSerializer(serializers.Serializer):
    scores = RubricScoreSerializer(many=True)
    mark = serializers.DecimalField(
        max_digits=6, decimal_places=2, min_value=0, required=False, help_text="Descriptive rubrics only"
    )
    feedback = serializers.CharField(required=False, allow_blank=True)
    is_released = serializers.BooleanField(required=False, default=False)


@extend_schema(
    request=RubricMarkSerializer,
    responses={200: SubmissionSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
    summary="Mark with the assignment's rubric or marking guide; the scores fill the mark",
    description="A scored rubric or a marking guide fills the mark from the points, scaled to the "
    "assignment's maximum; a descriptive rubric records the levels and the marker gives the mark.",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def rubric_mark(request, pk: int):
    from rubrics.models import Rubric
    from rubrics.services import score

    submission = _staff_submission(request, pk)
    assignment = submission.assignment
    if assignment.rubric_id is None:
        return Response({"code": "no_rubric", "detail": "This assignment has no rubric."}, status=409)
    data = RubricMarkSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    scores = [
        {**row, "points": str(row["points"]) if row.get("points") is not None else None}
        for row in data.validated_data["scores"]
    ]
    filled, kept = score(assignment.rubric, scores, assignment.max_mark)
    if filled is None:
        if "mark" not in data.validated_data:
            raise serializers.ValidationError({"mark": ["A descriptive rubric needs the mark as well."]})
        filled = data.validated_data["mark"]
    try:
        with transaction.atomic():
            mark = rules.save_mark(
                request,
                submission,
                mark=filled,
                feedback=data.validated_data.get("feedback", ""),
                is_released=data.validated_data["is_released"],
                source=Mark.Source.RUBRIC
                if assignment.rubric.kind != Rubric.Kind.DESCRIPTIVE
                else Mark.Source.MANUAL,
                rubric_scores=kept,
            )
    except rules.Refusal as refusal:
        return refused(refusal)
    if mark.is_released:
        rules.notify_released(mark)
    submission.refresh_from_db()
    return Response(SubmissionSerializer(submission).data)


class AdjustmentSerializer(serializers.Serializer):
    student_no = serializers.CharField()
    adjustment = serializers.DecimalField(
        max_digits=6, decimal_places=2, help_text="Added to the group's mark"
    )


class GroupMarkSerializer(serializers.Serializer):
    group = serializers.IntegerField()
    mark = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
    feedback = serializers.CharField(required=False, allow_blank=True)
    is_released = serializers.BooleanField(required=False, default=False)
    adjustments = AdjustmentSerializer(many=True, required=False, default=list)


@extend_schema(
    request=GroupMarkSerializer,
    responses={
        200: SubmissionSerializer(many=True),
        400: ErrorSerializer,
        403: ErrorSerializer,
        409: ErrorSerializer,
    },
    summary="Mark a group's work: the mark is copied to every member, with any individual adjustment",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def group_mark(request, pk: int):
    assignment = _staff_assignment(request, pk)
    if not assignment.is_group:
        return Response({"code": "not_group", "detail": "This is not a group assignment."}, status=409)
    data = GroupMarkSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    group = SiteGroup.objects.filter(site=assignment.site, pk=data.validated_data["group"]).first()
    members = list(assignment.submissions.filter(group=group).select_related("student", "assignment"))
    if group is None or not members:
        return Response({"code": "no_submission", "detail": "This group has handed nothing in."}, status=409)
    by_number = {s.student.external_id: s for s in members}
    adjustments = {}
    for row in data.validated_data["adjustments"]:
        if row["student_no"] not in by_number:
            raise serializers.ValidationError({"adjustments": [f"{row['student_no']} is not in this group."]})
        adjustments[row["student_no"]] = row["adjustment"]
    base = data.validated_data["mark"]
    try:
        with transaction.atomic():
            for submission in members:
                adjustment = adjustments.get(submission.student.external_id, Decimal(0))
                rules.save_mark(
                    request,
                    submission,
                    mark=base + adjustment,
                    feedback=data.validated_data.get("feedback", ""),
                    is_released=data.validated_data["is_released"],
                    source=Mark.Source.GROUP,
                    group_mark=base,
                    adjustment=adjustment,
                )
    except rules.Refusal as refusal:
        refusal.detail = f"{refusal.detail} (group {group.name})"
        return refused(refusal)
    if data.validated_data["is_released"]:
        for submission in members:
            rules.notify_released(submission.mark)
    rows = assignment.submissions.filter(group=group).select_related("student", "mark", "assignment")
    return Response(SubmissionSerializer(rows, many=True).data)


# ---------------------------------------------------------------------------------------------------------
# Feedback files and recordings (item 2.24)


class FeedbackUploadSerializer(serializers.Serializer):
    file = serializers.FileField(
        help_text="A feedback sheet, marked-up work or a recording (M4A, MP3, Ogg, WebM), at most "
        "UPLOAD_LIMIT_SUBMISSION_MB"
    )

    def validate_file(self, upload):
        return validate_upload(upload, FEEDBACK)


@extend_schema(
    request={"multipart/form-data": FeedbackUploadSerializer},
    responses={201: SubmissionSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
    summary="Return a feedback file or recorded feedback with the mark; the student sees it once released",
)
@api_view(["POST"])
@permission_classes([RolePermission])
@parser_classes([MultiPartParser, FormParser])
def add_feedback_file(request, pk: int):
    submission = _staff_submission(request, pk)
    try:
        rules.refuse_if_locked(submission)
    except rules.Refusal as refusal:
        return refused(refusal)
    data = FeedbackUploadSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    upload = data.validated_data["file"]
    with transaction.atomic():
        stored = FeedbackFile.objects.create(
            submission=submission,
            file=upload,
            original_name=original_name(upload),
            kind=sniff(upload) or "",
            size=upload.size,
            created_by=request.user,
            updated_by=request.user,
        )
        record(
            request, "feedback_added", submission, after={"file": stored.original_name, "kind": stored.kind}
        )
    submission.refresh_from_db()
    return Response(SubmissionSerializer(submission).data, status=201)


@extend_schema(
    methods=["GET"],
    responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 404: ErrorSerializer},
    summary="Download or play a feedback file (the student once the mark is released)",
)
@extend_schema(
    methods=["DELETE"],
    responses={204: None, 403: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
    summary="Take a feedback file back (teaching staff)",
)
@api_view(["GET", "DELETE"])
@permission_classes([RolePermission])
def feedback_file(request, pk: int):
    stored = (
        FeedbackFile.objects.select_related("submission__assignment__site", "submission__student")
        .filter(pk=pk, submission__in=visible_submissions(request.user))
        .first()
    )
    if stored is None:
        return Response({"code": "not_found", "detail": "No such file."}, status=404)
    submission = stored.submission
    staff = can_teach(request.user, submission.assignment.site)
    mark = Mark.objects.filter(submission=submission).first()
    if not staff and (mark is None or not mark.is_released):
        return Response({"code": "not_found", "detail": "No such file."}, status=404)
    if request.method == "DELETE":
        if not staff:
            raise PermissionDenied("Only the site's teaching staff can do this.")
        try:
            rules.refuse_if_locked(submission)
        except rules.Refusal as refusal:
            return refused(refusal)
        with transaction.atomic():
            record(request, "feedback_removed", submission, before={"file": stored.original_name})
            stored.file.delete(save=False)
            stored.delete()
        return Response(status=204)
    record(request, "download", submission, after={"feedback_file": stored.original_name})
    return FileResponse(stored.file.open("rb"), as_attachment=True, filename=stored.original_name)


# ---------------------------------------------------------------------------------------------------------
# Every submission in one archive; marks from a spreadsheet (item 2.25)


def _unique(name: str, used: set[str]) -> str:
    candidate, stem, suffix, n = name, PurePath(name).stem, PurePath(name).suffix, 2
    while candidate.lower() in used:
        candidate = f"{stem} ({n}){suffix}"
        n += 1
    used.add(candidate.lower())
    return candidate


@extend_schema(
    responses={(200, "application/zip"): OpenApiTypes.BINARY, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Download every submission as one zip: a folder per student number (or pseudonym), "
    "the files under their own names inside",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def download_all(request, pk: int):
    assignment = _staff_assignment(request, pk)
    archive = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)  # noqa: SIM115 - FileResponse closes it
    count = 0
    seen_attempts = set()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for submission in _ordered(assignment):
            attempt = rules.attempts_of(submission).prefetch_related("files").last()
            folder = rules.label_for(submission).replace("/", "-")
            if attempt is None or attempt.id in seen_attempts:
                continue  # a group's work is filed once, under the member who handed it in
            seen_attempts.add(attempt.id)
            used: set[str] = set()
            if attempt.text:
                bundle.writestr(f"{folder}/{_unique('text.txt', used)}", attempt.text)
            for stored in attempt.files.all():
                with stored.file.open("rb") as handle:
                    bundle.writestr(f"{folder}/{_unique(stored.original_name, used)}", handle.read())
            count += 1
    record(request, "downloaded_all", assignment, after={"submissions": count})
    archive.seek(0)
    safe_title = "".join(ch if ch.isalnum() else "-" for ch in assignment.title)[:60]
    return FileResponse(
        archive,
        as_attachment=True,
        filename=f"{assignment.site.code}-{safe_title}.zip",
        content_type="application/zip",
    )


class UploadMarksSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="CSV with the columns student number, mark and feedback")
    apply = serializers.BooleanField(
        required=False, default=False, help_text="false (the default) checks only; true saves the marks"
    )
    token = serializers.CharField(
        required=False, allow_blank=True, help_text="The token the check returned; needed to apply"
    )


class UploadRowSerializer(serializers.Serializer):
    line = serializers.IntegerField()
    student_no = serializers.CharField()
    mark = serializers.CharField(allow_null=True)
    feedback = serializers.CharField()
    outcome = serializers.CharField(
        help_text="new, changed, unchanged, or a refusal: unknown_student, no_submission, not_a_number, "
        "negative, above_max, locked_in_srms, repeated"
    )
    detail = serializers.CharField()


class UploadResultSerializer(serializers.Serializer):
    applied = serializers.BooleanField()
    token = serializers.CharField(help_text="Send it back with apply=true to save exactly what was checked")
    rows = UploadRowSerializer(many=True)
    refused = serializers.IntegerField()
    to_save = serializers.IntegerField()


def _read_csv(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise serializers.ValidationError({"file": ["The file is empty."]})
    header = [h.strip().lower() for h in rows[0]]
    student_col = next((header.index(h) for h in STUDENT_HEADERS if h in header), None)
    mark_col = header.index("mark") if "mark" in header else None
    if student_col is None or mark_col is None:
        raise serializers.ValidationError(
            {"file": ["The first line must name the columns: student number, mark and feedback."]}
        )
    feedback_col = header.index("feedback") if "feedback" in header else None
    parsed = []
    for line, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue

        def cell(col, row=row):
            return row[col].strip() if col is not None and col < len(row) else ""

        parsed.append(
            {
                "line": line,
                "student_no": cell(student_col),
                "mark": cell(mark_col),
                "feedback": cell(feedback_col),
            }
        )
    return parsed


def _check_rows(assignment, parsed: list[dict]) -> list[dict]:
    by_label = {
        rules.label_for(s): s for s in assignment.submissions.select_related("student", "assignment", "mark")
    }
    students = set(
        Membership.objects.filter(site=assignment.site, role=Membership.SiteRole.STUDENT).values_list(
            "person__external_id", flat=True
        )
    )
    seen = set()
    for row in parsed:
        key = row["student_no"]
        submission = by_label.get(key)
        outcome, detail = "", ""
        try:
            value = Decimal(row["mark"])
            if not value.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            value = None
        if key in seen:
            outcome, detail = "repeated", "This student is already on an earlier line."
        elif submission is None and (assignment.names_hidden or key not in students):
            outcome, detail = "unknown_student", "No student of this course has this number."
        elif submission is None:
            outcome, detail = "no_submission", "Nothing was handed in, so there is nothing to mark."
        elif value is None:
            outcome, detail = "not_a_number", "The mark is not a number."
        elif value < 0:
            outcome, detail = "negative", "A mark cannot be below zero."
        elif value > assignment.max_mark:
            outcome, detail = "above_max", f"The maximum is {assignment.max_mark}."
        elif rules.srms_lock(assignment.site, submission.student) is not None:
            outcome, detail = "locked_in_srms", "Sent to the SRMS and locked; correct it through the SRMS."
        else:
            current = getattr(submission, "mark", None)
            if current is None:
                outcome, detail = "new", "Will be saved as a draft."
            elif current.mark == value and current.feedback == row["feedback"]:
                outcome, detail = "unchanged", "Already this mark and feedback."
            else:
                outcome, detail = "changed", f"Was {current.mark}."
        seen.add(key)
        row.update(outcome=outcome, detail=detail, submission=submission, value=value)
    return parsed


@extend_schema(
    request={"multipart/form-data": UploadMarksSerializer},
    responses={200: UploadResultSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
    summary="Upload marks from a CSV: check first (every line's outcome), then apply what was checked",
    description="Columns: student number (or the pseudonym while marking is anonymous), mark, feedback. "
    "Marks are saved as drafts. Apply refuses (rows_refused) while any line is refused, and refuses "
    "(not_checked) a file that differs from the one checked.",
)
@api_view(["POST"])
@permission_classes([RolePermission])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def upload_marks(request, pk: int):
    assignment = _staff_assignment(request, pk)
    data = UploadMarksSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    upload = data.validated_data["file"]
    if upload.size > MAX_CSV_BYTES:
        raise serializers.ValidationError({"file": ["The file is larger than 2 MB."]})
    raw = upload.read()
    token = hashlib.sha256(f"{assignment.id}:".encode() + raw).hexdigest()
    rows = _check_rows(assignment, _read_csv(raw))
    refused_rows = [r for r in rows if r["outcome"] not in ("new", "changed", "unchanged")]
    to_save = [r for r in rows if r["outcome"] in ("new", "changed")]
    applied = False
    if data.validated_data["apply"]:
        if data.validated_data.get("token") != token:
            return Response(
                {
                    "code": "not_checked",
                    "detail": "Check this file first, then apply it without changing it.",
                },
                status=409,
            )
        if refused_rows:
            return Response(
                {"code": "rows_refused", "detail": f"Correct the {len(refused_rows)} refused line(s) first."},
                status=409,
            )
        try:
            with transaction.atomic():
                for row in to_save:
                    rules.save_mark(
                        request,
                        row["submission"],
                        mark=row["value"],
                        feedback=row["feedback"],
                        is_released=False,
                        source=Mark.Source.UPLOAD,
                    )
                record(request, "marks_uploaded", assignment, after={"saved": len(to_save), "token": token})
        except rules.Refusal as refusal:  # pragma: no cover - every refusal is found by the check above
            return refused(refusal)
        applied = True
    result = {
        "applied": applied,
        "token": token,
        "refused": len(refused_rows),
        "to_save": len(to_save),
        "rows": [
            {
                "line": r["line"],
                "student_no": r["student_no"],
                "mark": r["mark"] or None,
                "feedback": r["feedback"],
                "outcome": r["outcome"],
                "detail": r["detail"],
            }
            for r in rows
        ],
    }
    return Response(UploadResultSerializer(result).data)


# ---------------------------------------------------------------------------------------------------------
# Moderation (item 3.17)


class SampleSerializer(serializers.Serializer):
    percent = serializers.IntegerField(
        min_value=1, max_value=100, help_text="Share of the marked work to check"
    )


class SampledSerializer(serializers.Serializer):
    sampled = serializers.ListField(
        child=serializers.IntegerField(), help_text="Submission ids now in the sample"
    )


@extend_schema(
    request=SampleSerializer,
    responses={200: SampledSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
    summary="Choose at random a share of the marked work for a second marker to check",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def moderation_sample(request, pk: int):
    assignment = _staff_assignment(request, pk)
    if assignment.moderation != Assignment.Moderation.SAMPLE:
        return Response(
            {"code": "not_sampled", "detail": "This assignment is not moderated by sample."}, status=409
        )
    data = SampleSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    marked = list(
        assignment.submissions.filter(mark__isnull=False, moderation__isnull=True).select_related("mark")
    )
    size = max(1, round(len(marked) * data.validated_data["percent"] / 100)) if marked else 0
    chosen = random.SystemRandom().sample(marked, size)
    with transaction.atomic():
        for submission in chosen:
            Moderation.objects.create(
                submission=submission,
                first_mark=submission.mark.mark,
                first_marker=submission.mark.marked_by,
                created_by=request.user,
                updated_by=request.user,
            )
        record(request, "moderation_sampled", assignment, after={"sampled": [s.id for s in chosen]})
    return Response({"sampled": sorted(s.id for s in chosen)})


class SecondMarkSerializer(serializers.Serializer):
    mark = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
    note = serializers.CharField(required=False, allow_blank=True)


@extend_schema(
    request=SecondMarkSerializer,
    responses={200: ModerationSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
    summary="Second marking: another marker's mark, kept beside the first",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def second_mark(request, pk: int):
    submission = _staff_submission(request, pk)
    assignment = submission.assignment
    data = SecondMarkSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    first = Mark.objects.filter(submission=submission).first()
    moderation = Moderation.objects.filter(submission=submission).first()
    if first is None:
        return Response({"code": "not_marked", "detail": "The first marking comes first."}, status=409)
    if moderation is None and assignment.moderation != Assignment.Moderation.DOUBLE:
        return Response(
            {"code": "not_sampled", "detail": "This submission is not in the sample."}, status=409
        )
    marker = person_of(request.user)
    if marker is not None and first.marked_by_id == marker.id:
        return Response(
            {"code": "same_marker", "detail": "The second marker must be someone else."}, status=409
        )
    if data.validated_data["mark"] > assignment.max_mark:
        return Response({"code": "above_max", "detail": f"The maximum is {assignment.max_mark}."}, status=400)
    if moderation is not None and moderation.agreed_mark is not None:
        return Response({"code": "agreed", "detail": "The mark has already been agreed."}, status=409)
    with transaction.atomic():
        moderation, _ = Moderation.objects.update_or_create(
            submission=submission,
            defaults={
                "first_mark": first.mark,
                "first_marker": first.marked_by,
                "second_mark": data.validated_data["mark"],
                "second_marker": marker,
                "second_note": data.validated_data.get("note", ""),
                "updated_by": request.user,
            },
        )
        record(
            request,
            "second_marked",
            submission,
            after={"first": str(first.mark), "second": str(moderation.second_mark)},
        )
    return Response(ModerationSerializer(_moderation_row(moderation)).data)


@extend_schema(
    request=SecondMarkSerializer,
    responses={200: SubmissionSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
    summary="Record the agreed mark: it becomes the mark; both originals are kept",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def agree_mark(request, pk: int):
    submission = _staff_submission(request, pk)
    moderation = Moderation.objects.filter(submission=submission).first()
    if moderation is None or moderation.second_mark is None:
        return Response(
            {"code": "no_second_mark", "detail": "There is no second mark to agree with."}, status=409
        )
    data = SecondMarkSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    try:
        with transaction.atomic():
            moderation.agreed_mark = data.validated_data["mark"]
            moderation.agreed_by = person_of(request.user)
            moderation.agreed_at = timezone.now()
            moderation.agreed_note = data.validated_data.get("note", "")
            mark = rules.save_mark(
                request, submission, mark=moderation.agreed_mark, source=Mark.Source.AGREED
            )
            moderation.save()
            record(
                request,
                "mark_agreed",
                submission,
                after={
                    "first": str(moderation.first_mark),
                    "second": str(moderation.second_mark),
                    "agreed": str(moderation.agreed_mark),
                },
            )
    except rules.Refusal as refusal:
        return refused(refusal)
    if mark.is_released:
        rules.notify_released(mark)
    submission.refresh_from_db()
    return Response(SubmissionSerializer(submission).data)


urlpatterns = [
    path("submissions/<int:pk>/history/", submission_history, name="submission-history"),
    path("submissions/<int:pk>/neighbours/", neighbours, name="submission-neighbours"),
    path("submissions/<int:pk>/rubric-mark/", rubric_mark, name="submission-rubric-mark"),
    path("submissions/<int:pk>/feedback-files/", add_feedback_file, name="submission-feedback-files"),
    path("submissions/<int:pk>/second-mark/", second_mark, name="submission-second-mark"),
    path("submissions/<int:pk>/agree/", agree_mark, name="submission-agree"),
    path("submission-files/<int:pk>/download/", download_file, name="submission-file-download"),
    path("feedback-files/<int:pk>/", feedback_file, name="feedback-file"),
    path("receipts/<str:code>/", receipt, name="submission-receipt"),
    path("assignments/<int:pk>/release/", release_all, name="assignment-release"),
    path("assignments/<int:pk>/download-all/", download_all, name="assignment-download-all"),
    path("assignments/<int:pk>/marks-upload/", upload_marks, name="assignment-marks-upload"),
    path("assignments/<int:pk>/group-mark/", group_mark, name="assignment-group-mark"),
    path("assignments/<int:pk>/moderation-sample/", moderation_sample, name="assignment-moderation-sample"),
]
