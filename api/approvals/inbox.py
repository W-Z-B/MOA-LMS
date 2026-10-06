"""Everything waiting for one person's decision, oldest first (ported from the HRMS approvals/inbox.py).

Each source asks only what that person may decide, by the same rules the engine uses; the list links to where
it is decided. A request that has waited past its time limit is marked overdue. Staff-development enrolment
requests are the first source in the LMS; others join as they use the engine.
"""

from datetime import datetime

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from approvals.delegation import delegator_ids
from approvals.time_limits import waited
from iam.models import Role
from iam.services import has_role


def _item(kind: str, kind_name: str, title: str, since: datetime, link: str, *, for_whom: str = "") -> dict:
    days = waited(since, timezone.localdate())
    return {
        "kind": kind,
        "kind_name": kind_name,
        "title": title,
        "since": since,
        "waited_days": days,
        "overdue": days >= settings.DECISION_DAYS,
        "link": link,
        "for_whom": for_whom,
    }


def _enrolments(user, person) -> list[dict]:
    from staffdev.models import EnrolmentRequest

    qs = EnrolmentRequest.objects.filter(state=EnrolmentRequest.State.SUBMITTED).select_related(
        "person", "site", "approver"
    )
    if person is not None:
        qs = qs.exclude(person=person)
    stands_in_for = delegator_ids(person)
    mine = Q(approver_id__in=stands_in_for)
    if person is not None:
        mine |= Q(approver=person)
    if has_role(user, Role.COURSE_ADMIN):
        mine |= Q(approver__isnull=True)
    items = []
    for r in qs.filter(mine):
        standing_in = r.approver is not None and r.approver_id != getattr(person, "pk", None)
        items.append(
            _item(
                "enrolment",
                "Enrolment to decide",
                f"{r.person.full_name}: {r.site.title}",
                r.waiting_since or r.updated_at,
                f"/staff-development/requests/{r.id}",
                for_whom=f"standing in for {r.approver.full_name}" if standing_in else "",
            )
        )
    return items


def waiting_for(user) -> list[dict]:
    person = getattr(user, "person", None)
    items = [*_enrolments(user, person)]
    return sorted(items, key=lambda item: item["since"])
