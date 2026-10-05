"""Who is expected at a class, who sees which session, and attendance totals.

Totals per student count the sessions that take attendance and have started. Present and late count as
attended; excused sessions are left out of the percentage; a session with no record for the student counts
as "not recorded" (the lecturer closes the register to make those absent). The percentage is
attended / (attended + absent), or None while nothing counts.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q
from django.utils import timezone

from attendance.models import AttendanceRecord, ClassSession
from courses.access import TEACHING, person_of, site_role
from courses.groups import member_group_ids
from courses.models import Membership


def expected(session: ClassSession):
    """The memberships of the students expected at the session: the class, or the session's group."""
    qs = Membership.objects.filter(site=session.site, is_active=True, role=Membership.SiteRole.STUDENT)
    if session.group_id:
        qs = qs.filter(groups=session.group_id)
    return qs.select_related("person")


def sessions_for(user, sites):
    """The class sessions of `sites` the user sees: every one for teaching staff, administrators and
    auditors; a student's whole-class sessions and those of their groups."""
    out = ClassSession.objects.none()
    person = person_of(user)
    for site in sites:
        role = site_role(user, site)
        if role in (*TEACHING, "auditor"):
            out = out | ClassSession.objects.filter(site=site)
        elif role == Membership.SiteRole.STUDENT:
            groups = member_group_ids(person, site)
            out = out | ClassSession.objects.filter(site=site).filter(
                Q(group__isnull=True) | Q(group__in=groups)
            )
    return out


def session_visible(user, session: ClassSession) -> bool:
    role = site_role(user, session.site)
    if role in (*TEACHING, "auditor"):
        return True
    if role != Membership.SiteRole.STUDENT:
        return False
    return session.group_id is None or session.group_id in member_group_ids(person_of(user), session.site)


def totals(site, *, only_person=None, now=None) -> list[dict]:
    now = now or timezone.now()
    sessions = list(ClassSession.objects.filter(site=site, takes_attendance=True, starts_at__lte=now))
    members = Membership.objects.filter(
        site=site, is_active=True, role=Membership.SiteRole.STUDENT
    ).select_related("person")
    if only_person is not None:
        members = members.filter(person=only_person)
    group_members: dict[int, set[int]] = {}
    for session in sessions:
        if session.group_id and session.group_id not in group_members:
            group_members[session.group_id] = set(
                Membership.objects.filter(groups=session.group_id).values_list("person_id", flat=True)
            )
    records: dict[tuple[int, int], str] = {
        (r.session_id, r.student_id): r.status for r in AttendanceRecord.objects.filter(session__in=sessions)
    }
    rows = []
    for membership in members.order_by("person__last_name", "person__first_name"):
        person = membership.person
        counts = {s: 0 for s in AttendanceRecord.Status.values} | {"not_recorded": 0}
        held = 0
        for session in sessions:
            if session.group_id and person.id not in group_members[session.group_id]:
                continue
            held += 1
            counts[records.get((session.id, person.id), "not_recorded")] += 1
        attended = counts["present"] + counts["late"]
        counted = attended + counts["absent"]
        percent = (
            (Decimal(attended) * 100 / counted).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if counted
            else None
        )
        rows.append(
            {
                "person_id": person.id,
                "student_no": person.external_id,
                "name": person.full_name,
                "sessions": held,
                **counts,
                "percent": str(percent) if percent is not None else None,
            }
        )
    return rows
