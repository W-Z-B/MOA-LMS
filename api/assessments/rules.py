"""The rules of handing in and marking: due dates for each student, late penalties, locks, receipts,
pseudonyms and the one way a mark is changed. The views and the coursework total both use these, so a rule
is decided in one place.
"""

import hashlib
import hmac
import math
import secrets
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from assessments import preload
from assessments.models import (
    Accommodation,
    Assignment,
    Extension,
    Mark,
    MarkVersion,
    SrmsTransfer,
    Submission,
)

TWO_PLACES = Decimal("0.01")
RECEIPT_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, so a receipt can be read out

# Accepted with each hand-in when the assignment asks for it (item 3.22; decision D4, ADR 0006).
INTEGRITY_STATEMENT = (
    "I confirm that this work is my own, or my group's, except where I have said otherwise and named my "
    "sources. I have not copied another person's work, let anyone copy mine, or had anyone do it for me. "
    "Where I used a tool such as AI, I have said which and how, as the course allows."
)
LOCKED_DETAIL = (
    "This mark was sent to the SRMS on {date} and is locked. A change now goes through the SRMS correction "
    "process: ask the registry to correct the result there."
)


class Refusal(Exception):
    """A rule refuses the request. Rendered as {code, detail} with the given HTTP status."""

    def __init__(self, code: str, detail: str, status: int = 409):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


# ---------------------------------------------------------------------------------------------------------
# Accommodations (item 3.23)


def accommodation_of(person) -> Accommodation | None:
    if person is None:
        return None
    cached = preload.accommodations()
    if cached is not None and person.pk in cached:
        return cached[person.pk]
    return Accommodation.objects.filter(person=person, is_active=True).first()


def extra_time_percent(person) -> int:
    accommodation = accommodation_of(person)
    return accommodation.extra_time_percent if accommodation else 0


def accommodation_applies(person) -> bool:
    """What teaching staff may know: that an accommodation applies, never why."""
    accommodation = accommodation_of(person)
    return bool(
        accommodation
        and (accommodation.extra_days or accommodation.extra_time_percent or accommodation.other_format)
    )


# ---------------------------------------------------------------------------------------------------------
# Due dates for each student (items 2.26, 3.23)


@dataclass(frozen=True)
class Due:
    at: object  # the student's due date
    extended: bool  # an extension or an accommodation moved it


def group_of(assignment: Assignment, person):
    """The student's group for a group assignment: one of the assignment's groups (all the site's when it
    names none) that the student belongs to. None when not a group assignment or the student has none."""
    from courses.models import SiteGroup

    if not assignment.is_group or person is None:
        return None
    groups = SiteGroup.objects.filter(
        site=assignment.site, members__person=person, members__is_active=True
    ).distinct()
    chosen = assignment.groups.all()
    if chosen.exists():
        groups = groups.filter(id__in=chosen.values("id"))
    found = list(groups[:2])
    return found[0] if len(found) == 1 else None


def due_for(assignment: Assignment, person) -> Due:
    """The latest of: the assignment's due date, an extension for the student or their group, and the due
    date moved on by the student's accommodation."""
    due = assignment.due_at
    extended = False
    loaded = preload.current(assignment.site_id)
    if person is not None and loaded is not None:
        group_ids = loaded.groups.get(person.pk, [])
        extensions = [
            e
            for e in loaded.extensions.get(assignment.id, [])
            if e.student_id == person.pk or e.group_id in group_ids
        ]
    elif person is not None:
        group_ids = list(
            person.memberships.filter(site=assignment.site, is_active=True).values_list("groups", flat=True)
        )
        extensions = Extension.objects.filter(assignment=assignment).filter(
            Q(student=person) | Q(group_id__in=[g for g in group_ids if g])
        )
    if person is not None:
        for extension in extensions:
            if extension.due_at > due:
                due, extended = extension.due_at, True
        accommodation = accommodation_of(person)
        if accommodation and accommodation.extra_days:
            moved = assignment.due_at + timedelta(days=accommodation.extra_days)
            if moved > due:
                due, extended = moved, True
    return Due(due, extended)


# ---------------------------------------------------------------------------------------------------------
# Late penalties (item 2.35)


@dataclass(frozen=True)
class Penalised:
    raw: Decimal
    penalty: Decimal  # in marks
    final: Decimal
    percent: Decimal  # of the maximum mark


def penalty_percent(assignment: Assignment, submitted_at, due_at) -> Decimal:
    """The share of the maximum mark taken for lateness: the rate for each day (or hour) or part of one
    late, up to the cap. 0 when on time or when the assignment has no penalty."""
    if (
        assignment.late_penalty == Assignment.LatePenalty.NONE
        or submitted_at is None
        or submitted_at <= due_at
    ):
        return Decimal(0)
    period = (
        timedelta(days=1) if assignment.late_penalty == Assignment.LatePenalty.PER_DAY else timedelta(hours=1)
    )
    periods = math.ceil((submitted_at - due_at) / period)
    percent = assignment.late_penalty_percent * periods
    cap = assignment.late_penalty_cap if assignment.late_penalty_cap is not None else Decimal(100)
    return min(percent, cap, Decimal(100))


def penalised(submission: Submission, mark: Decimal, due: Due | None = None) -> Penalised:
    """The raw mark, the penalty and the mark that counts. The mark never goes below zero."""
    assignment = submission.assignment
    due = due or due_for(assignment, submission.student)
    percent = penalty_percent(assignment, submission.submitted_at, due.at)
    raw = min(mark, assignment.max_mark)
    penalty = (assignment.max_mark * percent / 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    penalty = min(penalty, raw)
    return Penalised(raw, penalty, raw - penalty, percent)


# ---------------------------------------------------------------------------------------------------------
# Marks locked in the SRMS (item 3.18)


def srms_lock(site, person) -> SrmsTransfer | None:
    """The transfer that locked the student's marks on the site, if the SRMS holds them."""
    loaded = preload.current(site)
    if loaded is not None:
        held = (SrmsTransfer.Outcome.ACCEPTED, SrmsTransfer.Outcome.LOCKED)
        return next((t for t in loaded.transfers.get(person.pk, []) if t.outcome in held), None)
    return (
        SrmsTransfer.objects.filter(
            site=site,
            student=person,
            outcome__in=[SrmsTransfer.Outcome.ACCEPTED, SrmsTransfer.Outcome.LOCKED],
        )
        .order_by("sent_at")
        .first()
    )


def refuse_if_locked(submission: Submission) -> None:
    lock = srms_lock(submission.assignment.site, submission.student)
    if lock is not None:
        when = timezone.localtime(lock.sent_at).strftime("%d/%m/%Y")
        raise Refusal("locked_in_srms", LOCKED_DETAIL.format(date=when))


# ---------------------------------------------------------------------------------------------------------
# Anonymous marking (item 3.16)


def pseudonym(assignment: Assignment, person) -> str:
    """A name for the student that is fixed for this assignment and tells nothing about who they are."""
    digest = hmac.new(
        settings.SECRET_KEY.encode(), f"pseudonym:{assignment.id}:{person.id}".encode(), hashlib.sha256
    ).hexdigest()
    return f"Candidate {int(digest[:10], 16) % 900000 + 100000}"


def label_for(submission: Submission) -> str:
    """How markers know a submission: the student number, or the pseudonym while names are hidden."""
    if submission.assignment.names_hidden:
        return pseudonym(submission.assignment, submission.student)
    return submission.student.external_id


# ---------------------------------------------------------------------------------------------------------
# Receipts (item 2.21)


def new_receipt() -> str:
    body = "".join(secrets.choice(RECEIPT_ALPHABET) for _ in range(10))
    return f"GSA-{body[:5]}-{body[5:]}"


def content_hash(text: str, file_hashes: list[tuple[str, str]]) -> str:
    """SHA-256 over the text and each file's name and own SHA-256, in the order handed in."""
    digest = hashlib.sha256()
    digest.update(b"text\0" + text.encode("utf-8") + b"\0")
    for name, sha in file_hashes:
        digest.update(b"file\0" + name.encode("utf-8") + b"\0" + sha.encode("ascii") + b"\0")
    return digest.hexdigest()


def file_sha256(upload) -> str:
    digest = hashlib.sha256()
    upload.seek(0)
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


def attempts_of(submission: Submission):
    """Every hand-in for this submission: the student's own, or the group's for a group assignment."""
    from assessments.models import SubmissionAttempt

    if submission.group_id:
        return SubmissionAttempt.objects.filter(
            submission__assignment_id=submission.assignment_id, submission__group_id=submission.group_id
        ).order_by("number", "id")
    return submission.attempts.order_by("number", "id")


# ---------------------------------------------------------------------------------------------------------
# The one way a mark changes (items 3.18, 3.19)


def moderation_outstanding(submission: Submission) -> bool:
    """A second marking that is not yet agreed holds the release of the mark (item 3.17)."""
    moderation = getattr(submission, "moderation", None)
    if submission.assignment.moderation == Assignment.Moderation.DOUBLE:
        return moderation is None or moderation.agreed_mark is None
    return moderation is not None and moderation.agreed_mark is None


def save_mark(
    request,
    submission: Submission,
    *,
    mark: Decimal,
    feedback: str | None = None,
    is_released: bool | None = None,
    source: str = Mark.Source.MANUAL,
    group_mark: Decimal | None = None,
    adjustment: Decimal = Decimal(0),
    rubric_scores: list | None = None,
) -> Mark:
    """Create or change a submission's mark: refused above the maximum, below zero or once the SRMS holds
    it; a release waits for moderation. Every change is kept (MarkVersion) and audited. Call inside a
    transaction."""
    from audit.services import record
    from courses.access import person_of

    assignment = submission.assignment
    if mark < 0:
        raise Refusal("negative", "A mark cannot be below zero.", 400)
    if mark > assignment.max_mark:
        raise Refusal("above_max", f"The maximum is {assignment.max_mark}.", 400)
    refuse_if_locked(submission)
    existing = Mark.objects.filter(submission=submission).first()
    before = (
        {"mark": str(existing.mark), "released": existing.is_released, "feedback": existing.feedback}
        if existing
        else None
    )
    values = {
        "mark": mark,
        "source": source,
        "group_mark": group_mark,
        "adjustment": adjustment,
        "marked_by": person_of(request.user),
        "updated_by": request.user,
    }
    if feedback is not None:
        values["feedback"] = feedback
    if is_released is not None:
        values["is_released"] = is_released
    if rubric_scores is not None:
        values["rubric_scores"] = rubric_scores
    elif source != Mark.Source.AGREED:
        values["rubric_scores"] = []
    if values.get("is_released") and moderation_outstanding(submission):
        raise Refusal(
            "moderation_outstanding", "The second marking must be agreed before the mark is released."
        )
    saved, _ = Mark.objects.update_or_create(submission=submission, defaults=values)
    MarkVersion.objects.create(
        submission=submission,
        mark=saved.mark,
        feedback=saved.feedback,
        is_released=saved.is_released,
        source=saved.source,
        rubric_scores=saved.rubric_scores,
        changed_by=request.user,
    )
    record(
        request,
        "mark",
        submission,
        before=before,
        after={"mark": str(saved.mark), "released": saved.is_released, "source": saved.source},
    )
    return saved


def notify_released(mark: Mark) -> None:
    submission = mark.submission
    if not submission.student.user:
        return
    from notifications.models import Notification
    from notifications.services import notify

    site = submission.assignment.site
    shown = penalised(submission, mark.mark)
    notify(
        [submission.student.user],
        title=f"Marked: {submission.assignment.title}",
        body=f"{site.code}: {shown.final} out of {submission.assignment.max_mark}.",
        link=f"/sites/{site.id}",
        kind=Notification.Kind.MARK,
        dedupe_key=f"mark:{mark.id}:released",
    )
