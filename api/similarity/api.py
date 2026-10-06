"""The similarity report (item 3.20): for the teaching staff of the submission's site, never for students.

A student can open their own submission, but its report reads as refused to them: the report is evidence
for staff to weigh, and the student hears about it from a person, with the chance to answer.
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from assessments import rules
from assessments.api import visible_submissions
from assessments.models import Assignment
from audit.services import record
from core.serializers import ErrorSerializer
from courses.access import can_teach, visible_sites
from iam.permissions import RolePermission
from similarity import services
from similarity.models import SimilarityDocument


class SimilarOtherSerializer(serializers.Serializer):
    known = serializers.BooleanField(help_text="True when the caller teaches on the other site too")
    label = serializers.CharField(help_text="Who and what, or 'Another GSA submission, 2025'")
    year = serializers.IntegerField()
    site = serializers.CharField(allow_null=True)
    assignment = serializers.CharField(allow_null=True)
    student = serializers.CharField(allow_null=True, help_text="Name and number, or the pseudonym")
    submission = serializers.IntegerField(allow_null=True)


class SimilarPassageSerializer(serializers.Serializer):
    mine = serializers.CharField(help_text="The passage in this submission")
    theirs = serializers.CharField(help_text="The same passage in the other submission")
    words = serializers.IntegerField()


class SimilarityMatchSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    percent = serializers.CharField(help_text="Share of this submission's words found in the other")
    shared_words = serializers.IntegerField()
    other = SimilarOtherSerializer()
    passages = SimilarPassageSerializer(many=True)


class SimilarityReportSerializer(serializers.Serializer):
    status = serializers.CharField(help_text="not_checked, waiting, done, no_text or failed")
    statement = serializers.CharField(help_text="Overlap is evidence for a person to judge, not a verdict")
    overall_percent = serializers.CharField(
        allow_null=True, help_text="Share of the words found in any other GSA submission"
    )
    word_count = serializers.IntegerField()
    attempt_number = serializers.IntegerField(allow_null=True, help_text="The hand-in that was read")
    checked_at = serializers.DateTimeField(allow_null=True)
    notes = serializers.ListField(child=serializers.CharField(), help_text="Files that could not be read")
    matches = SimilarityMatchSerializer(many=True)


class SimilaritySummarySerializer(serializers.Serializer):
    submission = serializers.IntegerField()
    label = serializers.CharField(help_text="Student number, or the pseudonym while marking is anonymous")
    status = serializers.CharField()
    overall_percent = serializers.CharField(allow_null=True)
    matches = serializers.IntegerField()


def _staff_submission(request, pk: int):
    """The submission whose work is checked: in a group, the member's who handed the work in."""
    submission = get_object_or_404(
        visible_submissions(request.user).select_related("assignment__site", "student"), pk=pk
    )
    if not can_teach(request.user, submission.assignment.site):
        raise PermissionDenied("Similarity reports are for the course's teaching staff.")
    latest = rules.attempts_of(submission).select_related("submission").last()
    return latest.submission if latest else submission


@extend_schema(
    methods=["GET"],
    responses={200: SimilarityReportSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="The similarity report of a submission (teaching staff only)",
    description="The overall overlap with other GSA submissions, past and present, and the matching passages "
    "side by side. The other submission is named only to staff who teach on its site as well; otherwise it "
    "is 'Another GSA submission' and its year. Quotations and the assignment's instructions are left out. "
    "The statement says what overlap is: evidence for a person to judge, not a verdict.",
)
@extend_schema(
    methods=["POST"],
    request=None,
    responses={
        200: SimilarityReportSerializer,
        403: ErrorSerializer,
        404: ErrorSerializer,
        409: ErrorSerializer,
    },
    summary="Check the latest hand-in again now (teaching staff only)",
    description="Every hand-in is checked in the background; this runs the check at once, for example after "
    "the check failed. Refused with nothing_handed_in when there is no hand-in, and checks_off when the "
    "similarity check is switched off (SIMILARITY_CHECKS).",
)
@api_view(["GET", "POST"])
@permission_classes([RolePermission])
def submission_similarity(request, pk: int):
    submission = _staff_submission(request, pk)
    if request.method == "POST":
        if not services.enabled():
            return Response(
                {"code": "checks_off", "detail": "The similarity check is switched off."}, status=409
            )
        attempt = submission.attempts.order_by("number", "id").last()
        if attempt is None:
            return Response(
                {"code": "nothing_handed_in", "detail": "Nothing has been handed in to check."}, status=409
            )
        document = services.check_safely(attempt)
        record(
            request,
            "similarity_checked",
            submission,
            after={"attempt": attempt.number, "status": document.status if document else "failed"},
        )
        submission.refresh_from_db()
    else:
        record(request, "similarity_viewed", submission)
    return Response(services.report(request.user, submission))


@extend_schema(
    responses={200: SimilaritySummarySerializer(many=True), 403: ErrorSerializer, 404: ErrorSerializer},
    summary="The overall overlap of every submission of an assignment (teaching staff only)",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def assignment_similarity(request, pk: int):
    assignment = get_object_or_404(
        Assignment.objects.filter(site__in=visible_sites(request.user)).select_related("site"), pk=pk
    )
    if not can_teach(request.user, assignment.site):
        raise PermissionDenied("Similarity reports are for the course's teaching staff.")
    documents = {
        d.submission_id: d
        for d in SimilarityDocument.objects.filter(submission__assignment=assignment).prefetch_related(
            "matches"
        )
    }
    rows = []
    for submission in (
        assignment.submissions.select_related("student", "assignment")
        .filter(Q(attempts__isnull=False) | Q(similarity__isnull=False))
        .distinct()
    ):
        document = documents.get(submission.id)
        rows.append(
            {
                "submission": submission.id,
                "label": rules.label_for(submission),
                "status": document.status if document else "not_checked",
                "overall_percent": str(document.overall_percent)
                if document and document.overall_percent is not None
                else None,
                "matches": len(document.matches.all()) if document else 0,
            }
        )
    rows.sort(key=lambda r: (-(float(r["overall_percent"]) if r["overall_percent"] else -1), r["label"]))
    return Response(rows)


urlpatterns = [
    path("submissions/<int:pk>/similarity/", submission_similarity, name="submission-similarity"),
    path("assignments/<int:pk>/similarity/", assignment_similarity, name="assignment-similarity"),
]
