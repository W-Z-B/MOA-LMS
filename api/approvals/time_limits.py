"""Time limits on decisions (ported from the HRMS approvals/time_limits.py): a reminder when a request has
waited too long, then escalation.

The staff-development enrolment request is the first workflow with them in the LMS. A request waiting for its
approver is chased after DECISION_DAYS working days; after ESCALATE_AFTER_DAYS more it goes on to the
approver's own supervisor (with nobody above, to the course administrators), and the person, the approver
passed over and the new one are all told. A request already with the course administrators is chased with
them.
"""

from datetime import date, datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from approvals.delegation import delegates_of, users_of
from audit.services import record
from iam.models import Role
from notifications.services import notify, users_with_role


def working_days(start: date, end: date) -> int:
    """Weekdays from start to end, both counted. GSA's public holidays are not known to the LMS yet."""
    if end < start:
        return 0
    days = (end - start).days + 1
    weeks, rest = divmod(days, 7)
    count = weeks * 5
    for offset in range(rest):
        if (start + timedelta(days=weeks * 7 + offset)).weekday() < 5:
            count += 1
    return count


def waited(since: datetime, today: date) -> int:
    """Working days a request has waited, not counting the day it began waiting."""
    start = timezone.localtime(since).date()
    return working_days(start + timedelta(days=1), today) if start < today else 0


def deciders(request) -> list:
    """Who decides it now: the approver and their stand-ins, or the course administrators."""
    if request.approver_id is not None:
        return users_of([request.approver, *delegates_of(request.approver)])
    return list(users_with_role(Role.COURSE_ADMIN).exclude(person=request.person))


def _what(request) -> str:
    return f"{request.person.full_name} asks to join {request.site.title}"


def _mark(request) -> str:
    return f"{request.id}:{request.waiting_since:%Y%m%d%H%M%S}"


def _remind(request, days: int) -> int:
    return len(
        notify(
            deciders(request),
            title=f"Waiting {days} working days for your decision: {request.person.full_name}",
            body=f"{_what(request)}. If it is not decided soon it goes on up the line.",
            link="/to-do",
            kind="approval",
            dedupe_key=f"enrolment:remind:{_mark(request)}",
        )
    )


def _escalate(request, days: int) -> bool:
    """Send the request on to the next person up. False when it is already with the course administrators,
    who are reminded instead."""
    passed_over = request.approver
    if passed_over is None:
        _remind(request, days)
        return False
    above = passed_over.supervisor
    if above is not None and (above.pk == request.person_id or not above.is_active):
        above = None  # never sent to the person who asked, nor to someone who has left
    with transaction.atomic():
        request.approver = above
        request.waiting_since = timezone.now()
        request.save(update_fields=["approver", "waiting_since", "updated_at"])
        record(
            None,
            "escalated",
            request,
            before={"approver": passed_over.pk},
            after={"approver": above.pk if above else None},
            reason=f"Not decided in {days} working days",
        )
    to = above.full_name if above else "the course administrators"
    notify(
        deciders(request),
        title=f"Enrolment request sent on to you: {request.person.full_name}",
        body=f"{_what(request)}. {passed_over.full_name} had not decided in {days} working days.",
        link="/to-do",
        kind="approval",
        dedupe_key=f"enrolment:escalated:{_mark(request)}",
    )
    notify(
        users_of([request.person]),
        title=f"Your request to join {request.site.title} was sent on to {to}",
        body=f"{passed_over.full_name} had not decided it in {days} working days.",
        link="/staff-development",
        dedupe_key=f"enrolment:escalated-owner:{_mark(request)}",
    )
    notify(
        users_of([passed_over]),
        title=f"An enrolment request was sent on to {to}",
        body=f"{_what(request)}. It had waited {days} working days for your decision.",
        link="/to-do",
        dedupe_key=f"enrolment:escalated-passed:{_mark(request)}",
    )
    return True


def chase(today: date | None = None) -> dict[str, int]:
    """The daily run: remind, then escalate, every enrolment request that has waited too long."""
    from staffdev.models import EnrolmentRequest

    today = today or timezone.localdate()
    limit, more = settings.DECISION_DAYS, settings.ESCALATE_AFTER_DAYS
    counts = {"reminded": 0, "escalated": 0}
    waiting = EnrolmentRequest.objects.filter(
        state=EnrolmentRequest.State.SUBMITTED, waiting_since__isnull=False
    ).select_related("person", "person__user", "approver", "approver__user", "approver__supervisor", "site")
    for request in waiting.order_by("waiting_since"):
        days = waited(request.waiting_since, today)
        if days < limit:
            continue
        if days >= limit + more:
            if _escalate(request, days):
                counts["escalated"] += 1
            else:
                counts["reminded"] += 1
        elif _remind(request, days):
            counts["reminded"] += 1
    return counts
