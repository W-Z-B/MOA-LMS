"""Peer review endpoints (item 4.13).

Teaching staff set peer review up on an assignment, give the work out (or the hourly job does, after the due
date), moderate the reviews, release them and, when peer marks count, fold them into the marks. A student
sees only the work given to them, without names, and, once released, the reviews of their own work, without
the reviewers' names.
"""

from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from assessments import rules
from assessments.models import Assignment, Submission
from audit.services import record, snapshot
from core.serializers import ErrorSerializer
from courses.access import can_teach, person_of, site_role, visible_sites
from courses.models import Membership
from iam.permissions import RolePermission
from peerreview import services
from peerreview.models import PeerOutcome, PeerReview, PeerReviewSetup


def _refused(error: services.Refusal) -> Response:
    return Response({"code": error.code, "detail": error.detail}, status=error.status)


class PeerSetupSerializer(serializers.ModelSerializer):
    class Meta:
        model = PeerReviewSetup
        fields = (
            "reviews_each",
            "reviews_due_at",
            "self_assessment",
            "peer_weight",
            "allocated_at",
            "released_at",
        )
        read_only_fields = ("allocated_at", "released_at")
        extra_kwargs = {"peer_weight": {"min_value": 0, "max_value": 100}}


class PeerReviewRowSerializer(serializers.Serializer):
    """A review as the lecturer reads it."""

    id = serializers.IntegerField()
    reviewer = serializers.CharField(help_text="The reviewer's student number, or pseudonym while hidden")
    is_self = serializers.BooleanField()
    submitted_at = serializers.DateTimeField(allow_null=True)
    mark = serializers.CharField(allow_null=True)
    scores = serializers.JSONField()
    comment = serializers.CharField()
    moderation = serializers.CharField(help_text="counts or left_out")
    moderation_note = serializers.CharField()


class PeerWorkRowSerializer(serializers.Serializer):
    submission = serializers.IntegerField()
    label = serializers.CharField(help_text="Student number, or the pseudonym while marking is anonymous")
    peer_mark = serializers.CharField(allow_null=True, help_text="Override, else mean of reviews that count")
    override = serializers.CharField(allow_null=True)
    self_mark = serializers.CharField(allow_null=True)
    staff_mark = serializers.CharField(allow_null=True, help_text="The marker's mark kept when folded in")
    mark = serializers.CharField(allow_null=True, help_text="The submission's mark now")
    reviews = PeerReviewRowSerializer(many=True)


class PeerStaffViewSerializer(serializers.Serializer):
    setup = PeerSetupSerializer(allow_null=True)
    rubric = serializers.BooleanField(help_text="The assignment has a rubric to review against")
    work = PeerWorkRowSerializer(many=True)


class PeerTaskSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    label = serializers.CharField(help_text="'Work 1', 'Work 2' ... or 'Your own work'")
    is_self = serializers.BooleanField()
    submitted_at = serializers.DateTimeField(allow_null=True)
    mark = serializers.CharField(allow_null=True)


class PeerReceivedSerializer(serializers.Serializer):
    label = serializers.CharField(help_text="'Reviewer 1' ... or 'Your own assessment'")
    is_self = serializers.BooleanField()
    mark = serializers.CharField(allow_null=True)
    scores = serializers.JSONField()
    comment = serializers.CharField()


class PeerStudentViewSerializer(serializers.Serializer):
    setup = PeerSetupSerializer(allow_null=True)
    to_do = PeerTaskSerializer(many=True)
    received = PeerReceivedSerializer(
        many=True, allow_null=True, help_text="null until the lecturer releases"
    )


class PeerReviewWorkSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    label = serializers.CharField()
    is_self = serializers.BooleanField()
    assignment = serializers.CharField()
    max_mark = serializers.CharField()
    reviews_due_at = serializers.DateTimeField()
    open = serializers.BooleanField(help_text="Reviews are still taken")
    text = serializers.CharField(help_text="The typed part of the work")
    files = serializers.ListField(child=serializers.DictField(), help_text="{id, filename, download_url}")
    rubric = serializers.JSONField(allow_null=True, help_text="null when the assignment has no rubric")
    scores = serializers.JSONField()
    mark = serializers.CharField(allow_null=True)
    comment = serializers.CharField()
    submitted_at = serializers.DateTimeField(allow_null=True)


class PeerSubmitSerializer(serializers.Serializer):
    scores = serializers.ListField(child=serializers.DictField(), help_text="As a marker gives them")
    comment = serializers.CharField(allow_blank=True, max_length=5000)


class PeerModerateSerializer(serializers.Serializer):
    moderation = serializers.ChoiceField(choices=PeerReview.Moderation.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")


class PeerOverrideSerializer(serializers.Serializer):
    override = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")


def _s(value):
    return None if value is None else str(value)


def _assignment(request, pk: int) -> Assignment:
    return get_object_or_404(
        Assignment.objects.filter(site__in=visible_sites(request.user)).select_related("site", "rubric"),
        pk=pk,
    )


def _staff(request, assignment: Assignment) -> None:
    if not can_teach(request.user, assignment.site):
        raise PermissionDenied("Only the course's teaching staff can do this.")


def _setup(assignment: Assignment) -> PeerReviewSetup:
    setup = PeerReviewSetup.objects.filter(assignment=assignment).first()
    if setup is None:
        raise services.Refusal("no_peer_review", "This assignment has no peer review.", 404)
    return setup


def _reviewer_label(review: PeerReview) -> str:
    """How staff know the reviewer: the student number, or the pseudonym while marking is anonymous."""
    assignment = review.setup.assignment
    if assignment.names_hidden:
        return rules.pseudonym(assignment, review.reviewer)
    return review.reviewer.external_id


def staff_view(assignment: Assignment) -> dict:
    setup = PeerReviewSetup.objects.filter(assignment=assignment).first()
    rows = []
    if setup is not None:
        for submission in services.handed_in(assignment):
            reviews = list(
                submission.peer_reviews.select_related("reviewer", "setup__assignment").order_by(
                    "is_self", "id"
                )
            )
            outcome = PeerOutcome.objects.filter(submission=submission).first()
            mark = getattr(submission, "mark", None)
            own = next((r for r in reviews if r.is_self), None)
            rows.append(
                {
                    "submission": submission.id,
                    "label": rules.label_for(submission),
                    "peer_mark": _s(services.peer_mark(submission)),
                    "override": _s(outcome.override) if outcome else None,
                    "self_mark": _s(own.mark) if own and own.submitted_at else None,
                    "staff_mark": _s(outcome.staff_mark) if outcome else None,
                    "mark": _s(mark.mark) if mark else None,
                    "reviews": [
                        {
                            "id": r.id,
                            "reviewer": _reviewer_label(r),
                            "is_self": r.is_self,
                            "submitted_at": r.submitted_at,
                            "mark": _s(r.mark),
                            "scores": r.scores,
                            "comment": r.comment,
                            "moderation": r.moderation,
                            "moderation_note": r.moderation_note,
                        }
                        for r in reviews
                    ],
                }
            )
        rows.sort(key=lambda r: r["label"])
    return {
        "setup": PeerSetupSerializer(setup).data if setup else None,
        "rubric": assignment.rubric_id is not None,
        "work": rows,
    }


def student_view(assignment: Assignment, person) -> dict:
    setup = PeerReviewSetup.objects.filter(assignment=assignment).first()
    if setup is None:
        return {"setup": None, "to_do": [], "received": None}
    mine = PeerReview.objects.filter(setup=setup, reviewer=person).order_by("is_self", "position")
    received = None
    if setup.released_at is not None:
        own = Submission.objects.filter(assignment=assignment, student=person).first()
        reviews = [
            r
            for r in (own.peer_reviews.order_by("is_self", "id") if own else [])
            if r.submitted_at and r.moderation == PeerReview.Moderation.COUNTS
        ]
        received, number = [], 0
        for review in reviews:
            if not review.is_self:
                number += 1
            received.append(
                {
                    "label": "Your own assessment" if review.is_self else f"Reviewer {number}",
                    "is_self": review.is_self,
                    "mark": _s(review.mark),
                    "scores": review.scores,
                    "comment": review.comment,
                }
            )
    return {
        "setup": PeerSetupSerializer(setup).data,
        "to_do": [
            {
                "id": r.id,
                "label": "Your own work" if r.is_self else f"Work {r.position}",
                "is_self": r.is_self,
                "submitted_at": r.submitted_at,
                "mark": _s(r.mark),
            }
            for r in mine
        ],
        "received": received,
    }


@extend_schema(
    methods=["GET"],
    responses={200: OpenApiTypes.OBJECT, 404: ErrorSerializer},
    summary="Peer review of an assignment: the overview for staff, or the reviews to do and received",
    description="Teaching staff receive StaffView (every piece of work, its reviews with the reviewers, the "
    "peer mark and the marks); a student receives StudentView (the work given to them, without names, and, "
    "once released, the reviews of their own work without the reviewers' names).",
)
@extend_schema(
    methods=["PUT"],
    request=PeerSetupSerializer,
    responses={
        200: PeerStaffViewSerializer,
        400: ErrorSerializer,
        403: ErrorSerializer,
        409: ErrorSerializer,
    },
    summary="Set peer review up on an assignment (teaching staff)",
    description="Needs a rubric on the assignment (rubric_required) and individual work (not_for_groups). "
    "Once the work is given out only the review due date and the peer weight can change (allocated).",
)
@extend_schema(
    methods=["DELETE"],
    responses={204: None, 403: ErrorSerializer, 409: ErrorSerializer},
    summary="Take peer review off an assignment before the work is given out (teaching staff)",
)
@api_view(["GET", "PUT", "DELETE"])
@permission_classes([RolePermission])
def peer_review(request, pk: int):
    assignment = _assignment(request, pk)
    if request.method == "GET":
        if can_teach(request.user, assignment.site):
            return Response(staff_view(assignment))
        person = person_of(request.user)
        if person is None or site_role(request.user, assignment.site) != Membership.SiteRole.STUDENT:
            raise PermissionDenied("Peer review is for the course's students and teaching staff.")
        if not assignment.is_published:
            return Response({"code": "not_found", "detail": "Not found."}, status=404)
        return Response(student_view(assignment, person))
    _staff(request, assignment)
    setup = PeerReviewSetup.objects.filter(assignment=assignment).first()
    if request.method == "DELETE":
        if setup is None:
            return Response(status=204)
        if setup.allocated_at is not None:
            return _refused(services.Refusal("allocated", "The work has been given out; peer review stays."))
        with transaction.atomic():
            before = snapshot(setup)
            setup.delete()
            record(request, "delete", setup, before=before, entity_id=before["id"])
        return Response(status=204)
    if assignment.rubric_id is None:
        return _refused(services.Refusal("rubric_required", "Add a rubric to the assignment first.", 400))
    if assignment.is_group:
        return _refused(services.Refusal("not_for_groups", "Peer review is for individual work.", 400))
    data = PeerSetupSerializer(setup, data=request.data, partial=setup is not None)
    data.is_valid(raise_exception=True)
    if setup is not None and setup.allocated_at is not None:
        fixed = {"reviews_each", "self_assessment"} & {
            k for k, v in data.validated_data.items() if getattr(setup, k) != v
        }
        if fixed:
            return _refused(
                services.Refusal(
                    "allocated", "The work has been given out; only the dates and weight can change."
                )
            )
    due = data.validated_data.get("reviews_due_at", getattr(setup, "reviews_due_at", None))
    if due is not None and due <= assignment.due_at:
        raise serializers.ValidationError({"reviews_due_at": ["Reviews are due after the work is due."]})
    with transaction.atomic():
        before = snapshot(setup) if setup else None
        saved = data.save(
            assignment=assignment, updated_by=request.user, **({} if setup else {"created_by": request.user})
        )
        record(request, "update" if before else "create", saved, before=before, after=snapshot(saved))
    return Response(staff_view(assignment))


@extend_schema(
    request=None,
    responses={200: OpenApiTypes.OBJECT, 403: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
    summary="Give the work out for review now (teaching staff); otherwise done hourly after the due date",
    description="Refusals: not_due, already_allocated, too_few. Returns {reviews: n}.",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def allocate(request, pk: int):
    assignment = _assignment(request, pk)
    _staff(request, assignment)
    try:
        made = services.allocate(_setup(assignment), request=request)
    except services.Refusal as error:
        return _refused(error)
    return Response({"reviews": made})


@extend_schema(
    request=None,
    responses={200: OpenApiTypes.OBJECT, 403: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
    summary="Show students the reviews of their work that count (teaching staff)",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def release(request, pk: int):
    assignment = _assignment(request, pk)
    _staff(request, assignment)
    try:
        told = services.release(_setup(assignment), request=request)
    except services.Refusal as error:
        return _refused(error)
    return Response({"students": told})


@extend_schema(
    request=None,
    responses={200: OpenApiTypes.OBJECT, 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Fold the peer marks into the draft marks as their share (teaching staff)",
    description="Each draft mark becomes (100 - peer_weight)% the marker's mark plus peer_weight% the peer "
    "mark; the marker's mark is kept beside it. Released marks are left. Returns {applied, skipped}.",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def apply(request, pk: int):
    assignment = _assignment(request, pk)
    _staff(request, assignment)
    try:
        return Response(services.apply_component(_setup(assignment), request=request))
    except services.Refusal as error:
        return _refused(error)


def _my_review(request, pk: int) -> PeerReview:
    person = person_of(request.user)
    review = get_object_or_404(
        PeerReview.objects.select_related("setup__assignment__rubric", "submission"),
        pk=pk,
        reviewer=person,
    )
    return review


def _work(review: PeerReview, now=None) -> dict:
    from django.utils import timezone

    from rubrics.api import rubric_for_students

    setup = review.setup
    assignment = setup.assignment
    attempt = rules.attempts_of(review.submission).prefetch_related("files").last()
    files = []
    for number, stored in enumerate(attempt.files.all() if attempt else [], start=1):
        extension = stored.original_name.rsplit(".", 1)[-1].lower() if "." in stored.original_name else "bin"
        files.append(
            {
                "id": stored.id,
                "filename": f"work-{review.position or 'own'}-{number}.{extension}",
                "download_url": f"/api/v1/peer-reviews/{review.id}/files/{stored.id}/",
            }
        )
    return {
        "id": review.id,
        "label": "Your own work" if review.is_self else f"Work {review.position}",
        "is_self": review.is_self,
        "assignment": assignment.title,
        "max_mark": str(assignment.max_mark),
        "reviews_due_at": setup.reviews_due_at,
        "open": (now or timezone.now()) <= setup.reviews_due_at,
        "text": attempt.text if attempt else "",
        "files": files,
        # A rubric taken off the assignment after peer review was set up leaves nothing to score by.
        "rubric": rubric_for_students(assignment.rubric) if assignment.rubric_id else None,
        "scores": review.scores,
        "mark": _s(review.mark),
        "comment": review.comment,
        "submitted_at": review.submitted_at,
    }


@extend_schema(
    methods=["GET"],
    responses={200: PeerReviewWorkSerializer, 404: ErrorSerializer},
    summary="The work given to the reviewer, without the author's name, with the rubric",
)
@extend_schema(
    methods=["POST"],
    request=PeerSubmitSerializer,
    responses={
        200: PeerReviewWorkSerializer,
        400: ErrorSerializer,
        404: ErrorSerializer,
        409: ErrorSerializer,
    },
    summary="Send or change a review: every criterion scored and a comment, until the reviews are due",
)
@api_view(["GET", "POST"])
@permission_classes([RolePermission])
def review_work(request, pk: int):
    review = _my_review(request, pk)
    if request.method == "POST":
        data = PeerSubmitSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                services.submit_review(
                    review,
                    scores=data.validated_data["scores"],
                    comment=data.validated_data["comment"],
                    request=request,
                )
        except services.Refusal as error:
            return _refused(error)
    return Response(_work(review))


@extend_schema(
    responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 404: ErrorSerializer},
    summary="Download a file of the work under a plain name that does not carry the author's",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def review_file(request, pk: int, file_id: int):
    review = _my_review(request, pk)
    work = _work(review)
    chosen = next((f for f in work["files"] if f["id"] == file_id), None)
    if chosen is None:
        return Response({"code": "not_found", "detail": "Not found."}, status=404)
    from assessments.models import SubmissionFile

    stored = SubmissionFile.objects.get(pk=file_id)
    return FileResponse(stored.file.open("rb"), as_attachment=True, filename=chosen["filename"])


@extend_schema(
    request=PeerModerateSerializer,
    responses={200: PeerReviewRowSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Let a review count, or leave it out, with a note (teaching staff)",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def moderate(request, pk: int):
    review = get_object_or_404(
        PeerReview.objects.filter(setup__assignment__site__in=visible_sites(request.user)).select_related(
            "setup__assignment__site", "reviewer", "submission"
        ),
        pk=pk,
    )
    _staff(request, review.setup.assignment)
    data = PeerModerateSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    with transaction.atomic():
        before = {"moderation": review.moderation, "note": review.moderation_note}
        review.moderation = data.validated_data["moderation"]
        review.moderation_note = data.validated_data["note"]
        review.moderated_by = person_of(request.user)
        review.save()
        record(
            request, "peer_review_moderated", review, before=before, after={"moderation": review.moderation}
        )
    return Response(
        {
            "id": review.id,
            "reviewer": _reviewer_label(review),
            "is_self": review.is_self,
            "submitted_at": review.submitted_at,
            "mark": _s(review.mark),
            "scores": review.scores,
            "comment": review.comment,
            "moderation": review.moderation,
            "moderation_note": review.moderation_note,
        }
    )


@extend_schema(
    request=PeerOverrideSerializer,
    responses={200: PeerWorkRowSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer},
    summary="Set the peer mark of a piece of work by hand, or clear it (teaching staff)",
)
@api_view(["POST"])
@permission_classes([RolePermission])
def override(request, pk: int):
    from assessments.api import visible_submissions

    submission = get_object_or_404(visible_submissions(request.user), pk=pk)
    assignment = submission.assignment
    _staff(request, assignment)
    if not PeerReviewSetup.objects.filter(assignment=assignment).exists():
        return Response(
            {"code": "no_peer_review", "detail": "This assignment has no peer review."}, status=404
        )
    data = PeerOverrideSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    value = data.validated_data["override"]
    if value is not None and value > assignment.max_mark:
        return Response({"code": "above_max", "detail": f"The maximum is {assignment.max_mark}."}, status=400)
    with transaction.atomic():
        outcome, _ = PeerOutcome.objects.get_or_create(submission=submission)
        before = {"override": _s(outcome.override)}
        outcome.override, outcome.override_note = value, data.validated_data["note"]
        outcome.save()
        record(request, "peer_mark_override", submission, before=before, after={"override": _s(value)})
    row = next(r for r in staff_view(assignment)["work"] if r["submission"] == submission.id)
    return Response(row)


urlpatterns = [
    path("assignments/<int:pk>/peer-review/", peer_review, name="assignment-peer-review"),
    path("assignments/<int:pk>/peer-review/allocate/", allocate, name="peer-review-allocate"),
    path("assignments/<int:pk>/peer-review/release/", release, name="peer-review-release"),
    path("assignments/<int:pk>/peer-review/apply/", apply, name="peer-review-apply"),
    path("peer-reviews/<int:pk>/", review_work, name="peer-review"),
    path("peer-reviews/<int:pk>/files/<int:file_id>/", review_file, name="peer-review-file"),
    path("peer-reviews/<int:pk>/moderate/", moderate, name="peer-review-moderate"),
    path("submissions/<int:pk>/peer-mark/", override, name="submission-peer-mark"),
]
