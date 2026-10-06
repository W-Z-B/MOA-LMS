"""Group work on a site (item 4.12): groupings, random allocation and self-sign-up.

A site's groups (courses.models.SiteGroup) are lab groups, field groups or campus groups. This module adds,
without changing SiteGroup itself:

- Groupings: a named set of groups ("Lab groups", "Field groups"), so that a forum, a class session or a
  piece of content can follow one way of dividing the class while another exists beside it.
- Random allocation: the site's active students shared at random into N groups, or into groups of at most
  K, as evenly as possible. The groups are new; existing groups are never changed by it.
- Self-sign-up: teaching staff open a group for students to join themselves, with an optional largest
  size and closing time. A student may hold only one self-sign-up group in each grouping (groups in no
  grouping count as one set), so that "pick your lab group" cannot be answered twice.

Groups made by hand are made and filled through the existing /groups/ endpoint.
"""

import math
import random

from django.db import models, transaction
from django.utils import timezone

from core.models import TimeStampedModel
from courses.models import CourseSite, Membership, SiteGroup


class Grouping(TimeStampedModel):
    site = models.ForeignKey(CourseSite, on_delete=models.CASCADE, related_name="groupings")
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True)
    groups = models.ManyToManyField(SiteGroup, blank=True, related_name="groupings")

    class Meta:
        ordering = ["name", "id"]
        unique_together = [("site", "name")]

    def __str__(self) -> str:
        return f"{self.site.code}: {self.name}"


class GroupSignUp(TimeStampedModel):
    """A group that students may join themselves."""

    group = models.OneToOneField(SiteGroup, on_delete=models.CASCADE, related_name="sign_up")
    is_open = models.BooleanField(default=True, help_text="Students may join or leave while it is open")
    max_size = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Most members it may have; empty means no limit"
    )
    closes_at = models.DateTimeField(null=True, blank=True, help_text="Sign-up closes then by itself")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_size__isnull=True) | models.Q(max_size__gte=1),
                name="group_sign_up_size_positive",
            )
        ]

    def __str__(self) -> str:
        return f"Sign-up for {self.group}"

    def accepting(self, now=None) -> bool:
        now = now or timezone.now()
        return self.is_open and (self.closes_at is None or self.closes_at > now)


class GroupRefused(Exception):
    """A join, leave or allocation that cannot be done; code and sentence for the {code, detail} shape."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def member_group_ids(person, site) -> set[int]:
    """The ids of the site's groups the person belongs to."""
    if person is None:
        return set()
    return set(
        SiteGroup.objects.filter(site=site, members__person=person, members__is_active=True).values_list(
            "id", flat=True
        )
    )


def _sign_up_sets(group: SiteGroup) -> list[set[int]]:
    """The sets of self-sign-up groups the group competes with: one per grouping, or the ungrouped set."""
    signup_groups = SiteGroup.objects.filter(site=group.site, sign_up__isnull=False)
    groupings = list(group.groupings.all())
    if not groupings:
        return [set(signup_groups.filter(groupings__isnull=True).values_list("id", flat=True))]
    return [set(signup_groups.filter(groupings=g).values_list("id", flat=True)) for g in groupings]


def student_membership(person, site) -> Membership | None:
    if person is None:
        return None
    return Membership.objects.filter(
        site=site, person=person, is_active=True, role=Membership.SiteRole.STUDENT
    ).first()


@transaction.atomic
def join(group: SiteGroup, person) -> None:
    membership = student_membership(person, group.site)
    if membership is None:
        raise GroupRefused("not_a_student", "Only students of this course can join its groups.")
    # The row lock makes two students racing for the last place take turns.
    sign_up = GroupSignUp.objects.select_for_update().filter(group=group).first()
    if sign_up is None:
        raise GroupRefused("not_self_sign_up", "Students cannot join this group themselves.")
    if not sign_up.accepting():
        raise GroupRefused("sign_up_closed", "Sign-up for this group has closed.")
    if group.members.filter(pk=membership.pk).exists():
        raise GroupRefused("already_member", "You are already in this group.")
    if sign_up.max_size is not None and group.members.count() >= sign_up.max_size:
        raise GroupRefused("group_full", "This group is full. Choose another group.")
    mine = set(membership.groups.values_list("id", flat=True))
    for others in _sign_up_sets(group):
        if mine & (others - {group.id}):
            raise GroupRefused(
                "already_in_set",
                "You are already in another group of this set. Leave it first to change groups.",
            )
    group.members.add(membership)


@transaction.atomic
def leave(group: SiteGroup, person) -> None:
    membership = student_membership(person, group.site)
    if membership is None:  # refused as joining is: teaching staff and the auditor are never in a set
        raise GroupRefused("not_a_student", "Only students of this course can leave its groups.")
    if not group.members.filter(pk=membership.pk).exists():
        raise GroupRefused("not_member", "You are not in this group.")
    sign_up = GroupSignUp.objects.filter(group=group).first()
    if sign_up is None:
        raise GroupRefused("not_self_sign_up", "Only teaching staff can take you out of this group.")
    if not sign_up.accepting():
        raise GroupRefused("sign_up_closed", "Sign-up for this group has closed; ask the lecturer.")
    group.members.remove(membership)


def split(count: int, *, groups: int | None = None, size: int | None = None) -> list[int]:
    """How many go in each group: `groups` groups, or as few groups of at most `size` as will hold them,
    with sizes differing by at most one."""
    if groups is None:
        groups = max(1, math.ceil(count / size)) if size else 1
    base, extra = divmod(count, groups)
    return [base + (1 if i < extra else 0) for i in range(groups)]


@transaction.atomic
def allocate(
    site: CourseSite,
    *,
    groups: int | None = None,
    size: int | None = None,
    prefix: str = "Group",
    grouping_name: str = "",
    user=None,
    rng: random.Random | None = None,
) -> tuple[list[SiteGroup], Grouping | None]:
    """Share the site's active students at random into new groups named "<prefix> 1", "<prefix> 2"...

    Refused when a name it would use is taken, so nothing already made is changed. With a grouping name the
    new groups are put in a new grouping of that name.
    """
    students = list(
        Membership.objects.filter(site=site, is_active=True, role=Membership.SiteRole.STUDENT).order_by("id")
    )
    if not students:
        raise GroupRefused("no_students", "The course has no students to put in groups.")
    sizes = split(len(students), groups=groups, size=size)
    if len(sizes) > len(students):
        raise GroupRefused(
            "too_many_groups", f"There are only {len(students)} students for {len(sizes)} groups."
        )
    names = [f"{prefix} {n}" for n in range(1, len(sizes) + 1)]
    taken = set(SiteGroup.objects.filter(site=site, name__in=names).values_list("name", flat=True))
    if taken:
        raise GroupRefused(
            "name_taken", f"The course already has a group called “{sorted(taken)[0]}”. Choose another name."
        )
    grouping = None
    if grouping_name:
        if Grouping.objects.filter(site=site, name=grouping_name).exists():
            raise GroupRefused("name_taken", f"The course already has a grouping called “{grouping_name}”.")
        grouping = Grouping.objects.create(site=site, name=grouping_name, created_by=user, updated_by=user)
    (rng or random.SystemRandom()).shuffle(students)
    made, start = [], 0
    for name, count in zip(names, sizes, strict=True):
        group = SiteGroup.objects.create(site=site, name=name, created_by=user, updated_by=user)
        group.members.set(students[start : start + count])
        start += count
        made.append(group)
    if grouping is not None:
        grouping.groups.set(made)
    return made, grouping
