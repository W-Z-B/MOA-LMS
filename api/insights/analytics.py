"""Course analytics for teaching staff (item 6.01) and each student's progress (item 6.02).

Everything is worked out from what the LMS already records (item 1.20): item completions (the first time a
student opens a page, downloads a file or marks an item complete), downloads in the audit log, hand-ins,
marks and quiz attempts. Time on a page is not recorded, so it is never shown.

Inside a course nothing is hidden for small groups: teaching staff already see each student's work. The
reports that leave the course (insights.reports) hide them (item 6.06).
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count
from django.utils import timezone

from assessments.models import Submission
from assessments.services import coursework_working
from audit.models import AuditLog
from courses.models import ContentItem, ItemCompletion, Membership
from courses.release import item_open, student_state
from insights.activity import last_seen, last_signed_in
from quizzes.models import Attempt

ONE_PLACE = Decimal("0.1")
DONE = ("graded", "pending")  # handed in (or attempted, or observed), whether or not marked yet


def percent(part, whole) -> str | None:
    if not whole:
        return None
    return str((Decimal(part) * 100 / Decimal(whole)).quantize(ONE_PLACE, rounding=ROUND_HALF_UP))


def _mean(values: list[Decimal]) -> str | None:
    if not values:
        return None
    return str((sum(values) / len(values)).quantize(ONE_PLACE, rounding=ROUND_HALF_UP))


def students_of(site):
    """The site's active students, as people."""
    memberships = Membership.objects.filter(
        site=site, role=Membership.SiteRole.STUDENT, is_active=True
    ).select_related("person")
    return [m.person for m in memberships.order_by("person__last_name", "person__first_name")]


def _items(site):
    return (
        ContentItem.objects.filter(module__site=site)
        .select_related("module")
        .prefetch_related("groups", "module__groups")
        .order_by("module__position", "module_id", "position", "id")
    )


def _item_rows(site, students) -> list[dict]:
    ids = [s.id for s in students]
    items = list(_items(site))
    opened = dict(
        ItemCompletion.objects.filter(item__in=items, person_id__in=ids)
        .values("item_id")
        .annotate(n=Count("person_id", distinct=True))
        .values_list("item_id", "n")
    )
    users = [s.user_id for s in students if s.user_id]
    downloads = dict(
        AuditLog.objects.filter(
            action="download",
            entity="courses.contentitem",
            entity_id__in=[i.id for i in items],
            actor_id__in=users,
        )
        .values("entity_id")
        .annotate(n=Count("id"))
        .values_list("entity_id", "n")
    )
    return [
        {
            "id": item.id,
            "title": item.title,
            "module": item.module.title,
            "kind": item.kind,
            "is_published": item.is_published,
            "opened": opened.get(item.id, 0),
            "opened_percent": percent(opened.get(item.id, 0), len(students)),
            "downloads": downloads.get(item.id, 0) if item.kind == ContentItem.Kind.FILE else None,
        }
        for item in items
    ]


def _assignment_rows(site, students, now) -> list[dict]:
    from assessments.rules import due_for

    ids = {s.id for s in students}
    rows = []
    for assignment in site.assignments.filter(is_published=True).order_by("due_at", "id"):
        submissions = [
            s
            for s in Submission.objects.filter(assignment=assignment, student_id__in=ids).select_related(
                "mark"
            )
        ]
        handed = {s.student_id for s in submissions}
        missing = sum(
            1 for student in students if student.id not in handed and due_for(assignment, student).at < now
        )
        marks = [s.mark for s in submissions if hasattr(s, "mark")]
        percents = [m.mark * 100 / assignment.max_mark for m in marks]
        rows.append(
            {
                "id": assignment.id,
                "title": assignment.title,
                "due_at": assignment.due_at,
                "handed_in": len(submissions),
                "handed_in_percent": percent(len(submissions), len(students)),
                "late": sum(1 for s in submissions if s.is_late),
                "missing": missing,
                "marked": len(marks),
                "released": sum(1 for m in marks if m.is_released),
                "average_percent": _mean(percents),
                "lowest_percent": _mean([min(percents)]) if percents else None,
                "highest_percent": _mean([max(percents)]) if percents else None,
            }
        )
    return rows


def _quiz_rows(site, students) -> list[dict]:
    ids = {s.id for s in students}
    rows = []
    for quiz in site.quizzes.filter(is_published=True).order_by("closes_at", "id"):
        finished = list(
            Attempt.objects.filter(
                quiz=quiz, student_id__in=ids, state=Attempt.State.FINISHED, max_score__gt=0
            ).exclude(score__isnull=True)
        )
        takers = {a.student_id for a in finished}
        rows.append(
            {
                "id": quiz.id,
                "title": quiz.title,
                "closes_at": quiz.closes_at,
                "is_practice": quiz.is_practice,
                "students_attempted": len(takers),
                "attempted_percent": percent(len(takers), len(students)),
                "attempts": len(finished),
                "average_percent": _mean([a.score * 100 / a.max_score for a in finished]),
                "statistics": f"/sites/{site.id}/quizzes/{quiz.id}/statistics",
            }
        )
    return rows


def course_analytics(site, *, now=None) -> dict:
    """What the class has opened, handed in and scored, item by item (item 6.01)."""
    now = now or timezone.now()
    students = students_of(site)
    return {
        "site": site.id,
        "students": len(students),
        "items": _item_rows(site, students),
        "assignments": _assignment_rows(site, students, now),
        "quizzes": _quiz_rows(site, students),
        "not_recorded": "Time spent on a page is not recorded. An item counts as opened the first time a "
        "student opens a page, downloads a file or marks it complete.",
    }


def _open_items(site, person) -> tuple[int, int]:
    """(items the student can see, those they have completed)."""
    state = student_state(person)
    visible = [item for item in _items(site) if item_open(item, state)]
    return len(visible), sum(1 for item in visible if item.id in state.completed)


def progress_of(site, person, *, released_only: bool, seen=None, signed_in=None, now=None) -> dict:
    """One student's progress on the site (item 6.02). released_only for the student's own view: marks not
    yet released are pending, as in their gradebook."""
    working = coursework_working(site, person, released_only=released_only, now=now)
    total, done = _open_items(site, person)
    states = [item["state"] for item in working["items"]]
    seen = last_seen(site, [person]) if seen is None else seen
    signed_in = last_signed_in([person]) if signed_in is None else signed_in
    return {
        "person_id": person.id,
        "student_no": person.external_id,
        "name": person.full_name,
        "items_total": total,
        "items_done": done,
        "items_percent": percent(done, total),
        "work_done": sum(1 for s in states if s in DONE),
        "work_missed": states.count("zero"),
        "work_to_come": states.count("not_due"),
        "work_marked": states.count("graded"),
        "coursework_percent": working["coursework_percent"],
        "last_seen": seen.get(person.id),
        "last_signed_in": signed_in.get(person.id),
        "work": working["items"],
    }


def class_progress(site, *, now=None) -> list[dict]:
    """Every student's progress, for teaching staff: one row each, without the item-by-item working."""
    students = students_of(site)
    seen = last_seen(site, students)
    signed_in = last_signed_in(students)
    rows = []
    for person in students:
        row = progress_of(site, person, released_only=False, seen=seen, signed_in=signed_in, now=now)
        row.pop("work")
        rows.append(row)
    return rows
