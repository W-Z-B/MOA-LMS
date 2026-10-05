"""Who stands in for whom on a day (ported from the HRMS approvals/delegation.py)."""

from datetime import date

from django.utils import timezone

from approvals.models import Delegation


def active(on: date | None = None):
    on = on or timezone.localdate()
    return Delegation.objects.filter(cancelled=False, starts__lte=on, ends__gte=on)


def delegates_of(person, on: date | None = None) -> list:
    """The colleagues standing in for someone today, so they are told what is sent to them."""
    if person is None:
        return []
    held = active(on).filter(delegator=person).select_related("delegate", "delegate__user")
    return [delegation.delegate for delegation in held]


def delegator_ids(person, on: date | None = None) -> list[int]:
    """Everyone the person stands in for today."""
    if person is None:
        return []
    return list(active(on).filter(delegate=person).values_list("delegator_id", flat=True))


def acts_for(person, approver_id: int | None, on: date | None = None) -> bool:
    """Whether the person may decide, today, what was sent to the approver."""
    if person is None or approver_id is None:
        return False
    return active(on).filter(delegate=person, delegator_id=approver_id).exists()


def users_of(people) -> list:
    """The accounts of those who can sign in, to tell them."""
    return [p.user for p in people if p is not None and p.user is not None and p.user.is_active]
