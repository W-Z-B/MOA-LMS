"""Release conditions and completion of items (item 2.16).

A module or an item can be held back from students until a date, until the student has completed another
item, or shown only to some groups of the class. A student sees an item only when it is published, is not
hidden for a takedown review, and both it and its module are released to them. Teaching staff, course
administrators and auditors see everything; teaching staff are told the conditions in words.

An item is completed when a student opens a page, downloads a file, or marks it complete themselves.
"""

from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone

from courses.access import person_of
from courses.models import ContentItem, ItemCompletion, Membership, Module, SiteGroup, TakedownRequest
from iam.services import SITE_ADMIN_ROLES, has_role


@dataclass
class StudentState:
    """What release conditions are judged against for one student, read once per request."""

    completed: set[int] = field(default_factory=set)
    groups: set[int] = field(default_factory=set)
    now: datetime | None = None


def student_state(person) -> StudentState:
    return StudentState(
        completed=set(ItemCompletion.objects.filter(person=person).values_list("item_id", flat=True)),
        groups=set(
            SiteGroup.objects.filter(members__person=person, members__is_active=True).values_list(
                "id", flat=True
            )
        ),
        now=timezone.now(),
    )


def state_for(request) -> StudentState | None:
    """The request's student state, worked out once; None for a user who is not a person."""
    if not hasattr(request, "_release_state"):
        person = person_of(request.user)
        request._release_state = student_state(person) if person is not None else None
    return request._release_state


def released(obj: Module | ContentItem, state: StudentState) -> bool:
    """Whether the object's own conditions are met for the student (not its module's)."""
    if obj.available_from and obj.available_from > state.now:
        return False
    if obj.requires_item_id and obj.requires_item_id not in state.completed:
        return False
    group_ids = {g.id for g in obj.groups.all()}
    return not group_ids or bool(group_ids & state.groups)


def item_open(item: ContentItem, state: StudentState) -> bool:
    """Whether a student sees the item: published, not under review, and released with its module."""
    return (
        item.is_published and not item.under_review and released(item.module, state) and released(item, state)
    )


def _student_sites(user):
    """Ids of the sites on which conditions apply to the user: those they are a student on."""
    person = person_of(user)
    if person is None or has_role(user, *SITE_ADMIN_ROLES):
        return []
    return list(
        Membership.objects.filter(
            person=person, is_active=True, role=Membership.SiteRole.STUDENT
        ).values_list("site_id", flat=True)
    )


def hidden_items(request, items) -> set[int]:
    """Ids among `items` that the user may not see because of release conditions or a review."""
    sites = _student_sites(request.user)
    if not sites:
        return set()
    state = state_for(request)
    rows = (
        items.filter(module__site_id__in=sites)
        .select_related("module")
        .prefetch_related("groups", "module__groups")
    )
    return {item.id for item in rows if not item_open(item, state)}


def hidden_modules(request, modules) -> set[int]:
    sites = _student_sites(request.user)
    if not sites:
        return set()
    state = state_for(request)
    rows = modules.filter(site_id__in=sites).prefetch_related("groups")
    return {module.id for module in rows if not released(module, state)}


def describe(obj: Module | ContentItem) -> str | None:
    """The conditions in words, for teaching staff: "Shown from 12/01/2027 09:00; once ... is complete"."""
    parts = []
    if obj.available_from:
        parts.append(f"shown from {timezone.localtime(obj.available_from):%d/%m/%Y %H:%M}")
    if obj.requires_item_id:
        title = obj.requires_item.title if obj.requires_item else "another item"
        parts.append(f"once “{title}” is complete")
    names = [g.name for g in obj.groups.all()]
    if names:
        parts.append(f"to {', '.join(names)} only")
    if isinstance(obj, ContentItem) and obj.under_review:
        parts.append("hidden from students while a takedown request is reviewed")
    if not parts:
        return None
    text = "; ".join(parts)
    return text[0].upper() + text[1:] + "."


def complete(person, item: ContentItem, how: str) -> tuple[ItemCompletion, bool]:
    """Record that the person completed the item, once: later views change nothing."""
    return ItemCompletion.objects.get_or_create(
        person=person, item=item, defaults={"completed_at": timezone.now(), "how": how}
    )


def would_loop(item: ContentItem | None, requires: ContentItem) -> bool:
    """Whether making `item` wait for `requires` would make a chain that never opens."""
    if item is None or item.pk is None:
        return False
    seen, step = set(), requires
    while step is not None and step.pk not in seen:
        if step.pk == item.pk:
            return True
        seen.add(step.pk)
        step = step.requires_item
    return False


def taken_down(item: ContentItem) -> bool:
    """Under review for takedown, or withdrawn after one: only a course administrator may bring it back."""
    if item.pk is None:
        return False
    return item.under_review or item.takedowns.filter(status=TakedownRequest.Status.WITHDRAWN).exists()
