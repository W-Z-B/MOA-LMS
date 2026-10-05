"""The retention schedule applied (item 1.19): which records each rule says are due, and their disposal.

Records are disposed of only through a run that one person proposes and a second approves, except logs that
no one needs to review (sign-in attempts, old notifications), which go every night. Each disposal is written
to the audit log with the rule that required it, so the record of what was destroyed outlives it; the entry
names the work and the student, never its content or the mark.

The LMS holds no term dates (the SRMS owns the calendar), so the end of a course's term is taken as the last
due date of its assignments. The audit log is chained (audit.chain) and is never purged by the system.
"""

import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime, time

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from audit.models import AuditLog
from audit.services import record

log = logging.getLogger(__name__)

TERM_END = "the end of the term of the course (the last due date of its assignments)"
TO_CONFIRM = "Proposal in the impact assessment; to be confirmed by GSA"
# code, name, months kept, counted from, action, automatic, note.
RULES = [
    (
        "submitted-work",
        "Submitted work: the files and text students hand in",
        72,
        TERM_END,
        "delete",
        False,
        TO_CONFIRM,
    ),
    (
        "marks-evidence",
        "Marks, feedback and the record of each submission",
        72,
        TERM_END,
        "delete",
        False,
        TO_CONFIRM + "; coursework totals are kept by the SRMS",
    ),
    (
        "forum-posts",
        "Forum posts",
        36,
        TERM_END,
        "delete",
        False,
        "The LMS has no forums yet; " + TO_CONFIRM,
    ),
    (
        "audit-log",
        "Audit log: changes, sign-ins, downloads and submissions recorded",
        84,
        "the entry",
        "review",
        False,
        "Chained against tampering, so the system removes nothing; GSA to decide. " + TO_CONFIRM,
    ),
    ("login-attempts", "Sign-in attempts", 12, "the attempt", "delete", True, TO_CONFIRM),
    ("notifications", "Notifications, read or not", 24, "when they were sent", "delete", True, TO_CONFIRM),
]
SUBMISSION_RULES = ("submitted-work", "marks-evidence")


@dataclass
class Due:
    entity: str
    entity_id: int
    person_id: int | None
    description: str
    due_since: date


def months_before(day: date, months: int) -> date:
    """The same day `months` months earlier, or the last day of that month when it is shorter."""
    month_index = day.year * 12 + day.month - 1 - months
    year, month = divmod(month_index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def months_after(day: date, months: int) -> date:
    return months_before(day, -months)


def seed_rules() -> None:
    """Create the rules the code knows, leaving any period GSA has already changed or confirmed alone."""
    from privacy.models import RetentionRule

    for code, name, months, counted_from, action, automatic, note in RULES:
        RetentionRule.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "keep_months": months,
                "counted_from": counted_from,
                "action": action,
                "automatic": automatic,
                "note": note,
            },
        )


def due(rule, today: date | None = None) -> list[Due]:
    """The records that the rule says should go, as of today."""
    from assessments.models import Submission
    from courses.models import CourseSite

    today = today or timezone.localdate()
    if rule.code not in SUBMISSION_RULES or rule.keep_months is None:
        return []  # forum posts: none yet; the audit log: reviewed by GSA, never removed by the system
    cut = timezone.make_aware(datetime.combine(months_before(today, rule.keep_months), time.min))
    ended = dict(
        CourseSite.objects.annotate(term_end=Max("assignments__due_at"))
        .filter(term_end__lt=cut)
        .values_list("id", "term_end")
    )
    submissions = Submission.objects.filter(assignment__site_id__in=ended).select_related(
        "assignment", "assignment__site", "student"
    )
    if rule.code == "submitted-work":  # work already removed is not listed again
        submissions = submissions.filter(Q(text__gt="") | ~Q(file=""))
    return [
        Due(
            "assessments.submission",
            s.id,
            s.student_id,
            f"{s.assignment.site.code}, {s.assignment.title} ({s.student.external_id} {s.student.full_name})",
            months_after(timezone.localdate(ended[s.assignment.site_id]), rule.keep_months),
        )
        for s in submissions.order_by("assignment__due_at", "id")
    ]


def still_due(item, rule, today: date) -> bool:
    return any(d.entity == item.entity and d.entity_id == item.entity_id for d in due(rule, today))


def _evidence(submission) -> dict:
    """What the audit log keeps of a destroyed submission: which work it was, never the work or the mark."""
    return {
        "assignment": submission.assignment_id,
        "student": submission.student_id,
        "submitted_at": submission.submitted_at.isoformat(),
        "file": submission.file.name or None,
        "text_length": len(submission.text),
    }


def dispose(request, item, rule) -> None:
    """Destroy one record named in an approved run, and record that it was, and why."""
    from assessments.models import Submission

    if item.entity != "assessments.submission":  # pragma: no cover - every reviewed rule names submissions
        raise ValueError(f"No way to dispose of {item.entity}")
    submission = Submission.objects.select_related("assignment").filter(pk=item.entity_id).first()
    if submission is not None:
        before = _evidence(submission)
        if submission.file:
            submission.file.delete(save=False)
        if (
            rule.code == "submitted-work"
        ):  # the work goes; the record that it was handed in, and its mark, stay
            Submission.objects.filter(pk=submission.pk).update(file="", text="", updated_at=timezone.now())
        else:
            submission.delete()  # the mark and feedback go with it
        record(
            request,
            "disposed",
            submission,
            before=before,
            entity_id=item.entity_id,
            reason=f"Retention schedule: {rule.name}",
        )
    item.disposed_at = timezone.now()
    item.save(update_fields=["disposed_at"])


def purge(today: date | None = None) -> dict[str, int]:
    """Every night: delete the logs that the automatic rules say are old enough. No review needed."""
    from certificates.models import CertificateCheck
    from iam.models import LoginAttempt, PasswordResetRequest
    from notifications.models import Notification
    from privacy.models import RetentionRule

    today = today or timezone.localdate()
    removed: dict[str, int] = {}
    for rule in RetentionRule.objects.filter(automatic=True, keep_months__isnull=False):
        cut = timezone.make_aware(datetime.combine(months_before(today, rule.keep_months), time.min))
        with transaction.atomic():
            if rule.code == "login-attempts":
                count = LoginAttempt.objects.filter(at__lt=cut).delete()[0]
                # Requests for a password link are kept as long as sign-in attempts (item 1.22).
                count += PasswordResetRequest.objects.filter(at__lt=cut).delete()[0]
                count += CertificateCheck.objects.filter(at__lt=cut).delete()[0]  # checks of certificates
            elif rule.code == "notifications":
                count = Notification.objects.filter(created_at__lt=cut).delete()[0]
            else:  # pragma: no cover - a rule the code does not know is left alone
                continue
            removed[rule.code] = count
            if count:
                AuditLog.objects.create(
                    action="purged",
                    entity="privacy.retentionrule",
                    entity_id=rule.pk,
                    after={"rule": rule.code, "rows": count, "older_than": cut.date().isoformat()},
                    reason=f"Retention schedule: {rule.name}",
                )
    log.info("retention purge removed %s", removed)
    return removed
