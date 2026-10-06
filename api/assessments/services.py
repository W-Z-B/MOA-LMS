"""Coursework totals and the gradebook."""

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from assessments.models import Submission
from courses.models import Membership

TWO_PLACES = Decimal("0.01")


def _marks_by_assignment(site, person) -> dict[int, Submission]:
    submissions = Submission.objects.filter(assignment__site=site, student=person).select_related("mark")
    return {s.assignment_id: s for s in submissions}


def _counting_quizzes(site):
    """Quizzes that count towards coursework: published, not practice, weighted (feature 10, item 3.03)."""
    return site.quizzes.filter(is_published=True, is_practice=False, weight__gt=0)


def coursework_percent(site, person, *, released_only: bool = False, now=None) -> Decimal | None:
    """Weighted coursework percentage for one student, or None when nothing counts yet.

    A marked assignment counts with its mark. An overdue assignment with no submission counts as zero.
    A submitted but unmarked assignment is pending and does not count.
    A quiz counts like an assignment: its grade (by the quiz's grading method) as a share of its maximum.
    A closed quiz with no attempt counts as zero. An attempt awaiting marking (or, for the student's own
    view, awaiting release) is pending and does not count.
    """
    from quizzes.services import is_closed, quiz_grade

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
    for quiz in _counting_quizzes(site):
        grade = quiz_grade(quiz, person, released_only=released_only, now=now)
        if grade.state == "graded":
            earned += quiz.weight * grade.fraction
            weight_total += quiz.weight
        elif grade.state == "none" and is_closed(quiz, person, now):
            weight_total += quiz.weight
    if weight_total == 0:
        return None
    return (earned / weight_total * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def gradebook(site, *, only_person=None, released_only: bool = False) -> dict:
    from quizzes.services import finish_expired_attempts, quiz_grade

    assignments = list(site.assignments.filter(is_published=True))
    quizzes = list(site.quizzes.filter(is_published=True))
    finish_expired_attempts(quizzes)  # timed-out attempts are submitted before anything is totalled
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
        quiz_marks = {}
        for quiz in quizzes:
            grade = quiz_grade(quiz, person, released_only=released_only)
            quiz_marks[str(quiz.id)] = {
                "attempts": grade.attempts,
                "state": grade.state,
                "percent": str((grade.fraction * 100).quantize(TWO_PLACES))
                if grade.fraction is not None
                else None,
            }
        total = coursework_percent(site, person, released_only=released_only)
        rows.append(
            {
                "person_id": person.id,
                "student_no": person.external_id,
                "name": person.full_name,
                "marks": marks,
                "quizzes": quiz_marks,
                "coursework_percent": str(total) if total is not None else None,
            }
        )
    return {
        "site": site.code,
        "assignments": [
            {"id": a.id, "title": a.title, "max_mark": str(a.max_mark), "weight": str(a.weight)}
            for a in assignments
        ],
        "quizzes": [
            {
                "id": q.id,
                "title": q.title,
                "weight": str(q.weight),
                "counts": q.counts,
                "grading_method": q.grading_method,
            }
            for q in quizzes
        ],
        "rows": rows,
    }
