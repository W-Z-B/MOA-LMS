"""The rules of peer review (item 4.13): who reviews whose work, when, how a peer mark is made, and how it
becomes a share of the mark."""

import secrets
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from assessments import rules
from assessments.models import Mark, Submission
from audit.services import record
from peerreview.models import PeerOutcome, PeerReview, PeerReviewSetup

TWO_PLACES = Decimal("0.01")


class Refusal(Exception):
    def __init__(self, code: str, detail: str, status: int = 409):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


def handed_in(assignment) -> list[Submission]:
    """The work that is reviewed: every submission with a hand-in of its own."""
    return list(
        assignment.submissions.filter(attempts__isnull=False)
        .distinct()
        .select_related("student")
        .order_by("id")
    )


def allocate(setup: PeerReviewSetup, *, request=None, now=None) -> int:
    """Give each student who handed in reviews_each other pieces of work, chosen at random so that every
    piece is reviewed the same number of times and nobody reviews their own (except a self-assessment).
    Only after the due date, and once. Returns how many reviews were made."""
    now = now or timezone.now()
    assignment = setup.assignment
    if now < assignment.due_at:
        raise Refusal("not_due", "Peer review starts after the due date.")
    with transaction.atomic():
        setup = PeerReviewSetup.objects.select_for_update().get(pk=setup.pk)
        if setup.allocated_at is not None:
            raise Refusal("already_allocated", "The work has already been given out for review.")
        work = handed_in(assignment)
        if len(work) < 2 and not setup.self_assessment:
            raise Refusal("too_few", "At least two students must hand in work for peer review.")
        secrets.SystemRandom().shuffle(work)
        each = min(setup.reviews_each, len(work) - 1)
        rows = []
        for index, submission in enumerate(work):
            reviewer = submission.student
            for step in range(1, each + 1):
                rows.append(
                    PeerReview(
                        setup=setup,
                        reviewer=reviewer,
                        submission=work[(index + step) % len(work)],
                        position=step,
                    )
                )
            if setup.self_assessment:
                rows.append(
                    PeerReview(
                        setup=setup, reviewer=reviewer, submission=submission, position=0, is_self=True
                    )
                )
        PeerReview.objects.bulk_create(rows)
        setup.allocated_at = now
        setup.save(update_fields=["allocated_at", "updated_at"])
        record(
            request,
            "peer_review_allocated",
            setup,
            after={"assignment": assignment.id, "students": len(work), "each": each, "reviews": len(rows)},
        )
    _tell_reviewers(setup, work)
    return len(rows)


def _tell_reviewers(setup: PeerReviewSetup, work: list[Submission]) -> None:
    from notifications.services import notify

    assignment = setup.assignment
    when = timezone.localtime(setup.reviews_due_at).strftime("%d/%m/%Y %H:%M")
    users = [s.student.user for s in work if s.student.user_id and s.student.user.is_active]
    if users:
        notify(
            users,
            title=f"Peer review: {assignment.title}",
            body=f"{assignment.site.code}: review the work you have been given by {when}. Names are hidden.",
            link=f"/sites/{assignment.site_id}/assignments/{assignment.id}/peer-review",
            dedupe_key=f"peer-allocated:{setup.id}",
        )


def allocate_due(now=None) -> int:
    """Allocate every peer review whose assignment is now past its due date (the hourly job)."""
    now = now or timezone.now()
    made = 0
    for setup in PeerReviewSetup.objects.filter(
        allocated_at__isnull=True, assignment__due_at__lte=now, assignment__is_published=True
    ).select_related("assignment__site"):
        try:
            made += allocate(setup, now=now)
        except Refusal:
            continue  # too few hand-ins: the lecturer sees why when they allocate by hand
    return made


def submit_review(review: PeerReview, *, scores: list, comment: str, request, now=None) -> PeerReview:
    """Save a review: every criterion of the rubric scored, as a marker would. It can be changed until the
    reviews are due."""
    from rubrics.services import score

    now = now or timezone.now()
    setup = review.setup
    if now > setup.reviews_due_at:
        raise Refusal(
            "closed",
            "Reviews were due by "
            + timezone.localtime(setup.reviews_due_at).strftime("%d/%m/%Y %H:%M")
            + ".",
        )
    assignment = setup.assignment
    mark, kept = score(assignment.rubric, scores, assignment.max_mark)
    before = {
        "mark": str(review.mark) if review.mark is not None else None,
        "submitted": bool(review.submitted_at),
    }
    review.scores, review.mark, review.comment = kept, mark, comment.strip()[:5000]
    review.submitted_at = now
    review.updated_by = request.user
    review.save()
    record(
        request,
        "peer_review_submitted",
        review,
        before=before,
        after={"mark": str(mark) if mark is not None else None},
    )
    return review


def counted(submission: Submission) -> list[PeerReview]:
    return [
        r
        for r in submission.peer_reviews.all()
        if not r.is_self and r.submitted_at and r.moderation == PeerReview.Moderation.COUNTS
    ]


def peer_mark(submission: Submission) -> Decimal | None:
    """The lecturer's override, else the mean of the peer marks that count. None when there are none."""
    outcome = PeerOutcome.objects.filter(submission=submission).first()
    if outcome is not None and outcome.override is not None:
        return outcome.override
    marks = [r.mark for r in counted(submission) if r.mark is not None]
    if not marks:
        return None
    return (sum(marks, Decimal(0)) / len(marks)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def apply_component(setup: PeerReviewSetup, *, request) -> dict:
    """Fold the peer mark into each draft mark as its share: (100 - w)% the marker's mark and w% the peer
    mark. The marker's own mark is kept; folding in again after it changes uses the new one. Released or
    locked marks, and work with no peer mark or no marker's mark yet, are left and counted."""
    weight = setup.peer_weight
    if not weight:
        raise Refusal("feedback_only", "Peer marks do not count on this assignment.", 400)
    applied = skipped = 0
    with transaction.atomic():
        for submission in handed_in(setup.assignment):
            mark = Mark.objects.filter(submission=submission).first()
            peer = peer_mark(submission)
            if mark is None or peer is None or mark.is_released:
                skipped += 1
                continue
            outcome, _ = PeerOutcome.objects.get_or_create(submission=submission)
            staff = (
                outcome.staff_mark
                if outcome.combined is not None
                and outcome.combined == mark.mark
                and outcome.staff_mark is not None
                else mark.mark
            )
            combined = (staff * (100 - weight) / 100 + peer * weight / 100).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
            try:
                rules.save_mark(
                    request,
                    submission,
                    mark=combined,
                    feedback=mark.feedback,
                    is_released=False,
                    rubric_scores=mark.rubric_scores,
                    source=mark.source,
                )
            except rules.Refusal:
                skipped += 1
                continue
            outcome.staff_mark, outcome.combined, outcome.applied_at = staff, combined, timezone.now()
            outcome.save()
            record(
                request,
                "peer_component_applied",
                submission,
                after={"staff": str(staff), "peer": str(peer), "weight": str(weight), "mark": str(combined)},
            )
            applied += 1
    return {"applied": applied, "skipped": skipped}


def release(setup: PeerReviewSetup, *, request, now=None) -> int:
    """Show the students the reviews of their work that count. Returns how many students were told."""
    from notifications.services import notify

    if setup.allocated_at is None:
        raise Refusal("not_allocated", "No work has been given out for review yet.")
    setup.released_at = now or timezone.now()
    setup.save(update_fields=["released_at", "updated_at"])
    record(request, "peer_review_released", setup, after={"assignment": setup.assignment_id})
    assignment = setup.assignment
    users = [s.student.user for s in handed_in(assignment) if s.student.user_id and s.student.user.is_active]
    if users:
        notify(
            users,
            title=f"Peer reviews of your work: {assignment.title}",
            body=f"{assignment.site.code}: the reviews of your work can be read now.",
            link=f"/sites/{assignment.site_id}/assignments/{assignment.id}/peer-review",
            dedupe_key=f"peer-released:{setup.id}",
        )
    return len(users)
