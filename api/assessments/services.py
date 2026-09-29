"""Coursework totals and the gradebook."""

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from assessments.models import Submission
from courses.models import Membership

TWO_PLACES = Decimal("0.01")


def _marks_by_assignment(site, person) -> dict[int, Submission]:
    submissions = Submission.objects.filter(assignment__site=site, student=person).select_related("mark")
    return {s.assignment_id: s for s in submissions}


def coursework_percent(site, person, *, released_only: bool = False, now=None) -> Decimal | None:
    """Weighted coursework percentage for one student, or None when nothing counts yet.

    A marked assignment counts with its mark. An overdue assignment with no submission counts as zero.
    A submitted but unmarked assignment is pending and does not count.
    """
    now = now or timezone.now()
    submissions = _marks_by_assignment(site, person)
    weight_total = Decimal(0)
    earned = Decimal(0)
    for assignment in site.assignments.filter(is_published=True):
        submission = submissions.get(assignment.id)
        mark = getattr(submission, "mark", None) if submission else None
        if mark is not None and (mark.is_released or not released_only):
            earned += assignment.weight * min(mark.mark, assignment.max_mark) / assignment.max_mark
            weight_total += assignment.weight
        elif submission is None and assignment.due_at < now:
            weight_total += assignment.weight
    if weight_total == 0:
        return None
    return (earned / weight_total * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def gradebook(site, *, only_person=None, released_only: bool = False) -> dict:
    assignments = list(site.assignments.filter(is_published=True))
    members = Membership.objects.filter(
        site=site, is_active=True, role=Membership.SiteRole.STUDENT
    ).select_related("person")
    if only_person is not None:
        members = members.filter(person=only_person)
    rows = []
    for membership in members.order_by("person__last_name", "person__first_name"):
        person = membership.person
        submissions = _marks_by_assignment(site, person)
        marks = {}
        for assignment in assignments:
            submission = submissions.get(assignment.id)
            mark = getattr(submission, "mark", None) if submission else None
            visible = mark is not None and (mark.is_released or not released_only)
            marks[str(assignment.id)] = {
                "submitted": submission is not None,
                "late": bool(submission and submission.is_late),
                "mark": str(mark.mark) if visible else None,
                "feedback": mark.feedback if visible else "",
            }
        total = coursework_percent(site, person, released_only=released_only)
        rows.append(
            {
                "person_id": person.id,
                "student_no": person.external_id,
                "name": person.full_name,
                "marks": marks,
                "coursework_percent": str(total) if total is not None else None,
            }
        )
    return {
        "site": site.code,
        "assignments": [
            {"id": a.id, "title": a.title, "max_mark": str(a.max_mark), "weight": str(a.weight)}
            for a in assignments
        ],
        "rows": rows,
    }
