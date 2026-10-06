"""Coursework totals, their working, and the gradebook (items 2.28 to 2.30).

The coursework total is worked out item by item. Each assignment, quiz and practical task that counts is
"graded" (it counts with its result), "zero" (overdue or closed with nothing handed in: it counts as 0),
"pending" (handed in but not yet marked, or, for the student's own view, not yet released) or "not_due"
(nothing handed in yet and still open); only graded and zero items count.

For teaching staff, an anonymously marked assignment whose marks are not yet released is pending for every
student who handed it in, whatever its marks: counting them would reveal them (item 3.16).

With no gradebook categories the total is the weighted mean of the counted items, exactly as before
categories existed. With categories, each category's percentage is the weighted mean of its counted items
less the lowest it drops, and the total is the weighted mean of the categories that have something
counted, by the categories' weights. Items in no category count together as one more category whose
weight is the sum of their counted items' own weights, which is how Moodle treats items left at the top
of a course.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from assessments.models import GradeCategory, SrmsTransfer, Submission
from assessments.rules import due_for, penalised
from courses.models import Membership

TWO_PLACES = Decimal("0.01")
COUNTED = ("graded", "zero")


def _marks_by_assignment(site, person) -> dict[int, Submission]:
    submissions = Submission.objects.filter(assignment__site=site, student=person).select_related(
        "mark", "assignment"
    )
    return {s.assignment_id: s for s in submissions}


def _counting_quizzes(site):
    """Quizzes that count towards coursework: published, not practice, weighted (feature 10, item 3.03)."""
    return site.quizzes.filter(is_published=True, is_practice=False, weight__gt=0)


def _pct(fraction) -> str | None:
    return None if fraction is None else str((fraction * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


@dataclass
class Item:
    kind: str  # assignment, quiz, practical or forum
    id: int
    title: str
    category_id: int | None
    weight: Decimal
    fraction: Decimal | None
    state: str
    detail: dict = field(default_factory=dict)
    dropped: bool = False
    exact: Decimal | None = None  # weight * mark / maximum, worked in that order as it always was

    @property
    def earned(self) -> Decimal:
        return self.exact if self.exact is not None else self.weight * self.fraction

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "id": self.id,
            "title": self.title,
            "category": self.category_id,
            "weight": str(self.weight),
            "state": "dropped" if self.dropped else self.state,
            "percent": _pct(self.fraction),
            **self.detail,
        }


def _assignment_items(site, person, released_only, now) -> list[Item]:
    submissions = _marks_by_assignment(site, person)
    items = []
    for assignment in site.assignments.filter(is_published=True):
        exact = None
        submission = submissions.get(assignment.id)
        mark = getattr(submission, "mark", None) if submission else None
        due = due_for(assignment, person)
        detail = {
            "max_mark": str(assignment.max_mark),
            "due_at": due.at.isoformat(),
            "extended": due.extended,
            "late": bool(submission and submission.is_late),
            "raw_mark": None,
            "penalty": None,
            "final_mark": None,
            "anonymous": False,
        }
        if not released_only and assignment.names_hidden and submission is not None:
            # Anonymous marking (3.16): until the marks are released, a staff total that counted them would
            # tell markers who earned which mark. The item waits, as "pending (anonymous marking)".
            fraction, state = None, "pending"
            detail["anonymous"] = True
        elif mark is not None and (mark.is_released or not released_only):
            shown = penalised(submission, mark.mark, due)
            detail.update(raw_mark=str(shown.raw), penalty=str(shown.penalty), final_mark=str(shown.final))
            fraction, state = shown.final / assignment.max_mark, "graded"
            exact = assignment.weight * shown.final / assignment.max_mark
        elif submission is None and due.at < now:
            fraction, state = Decimal(0), "zero"
        else:
            fraction, state = None, "pending" if submission is not None else "not_due"
        item = Item(
            "assignment",
            assignment.id,
            assignment.title,
            assignment.category_id,
            assignment.weight,
            fraction,
            state,
        )
        item.detail, item.exact = detail, exact
        items.append(item)
    return items


def _quiz_items(site, person, released_only, now) -> list[Item]:
    from quizzes.services import is_closed, quiz_grade

    items = []
    for quiz in _counting_quizzes(site):
        grade = quiz_grade(quiz, person, released_only=released_only, now=now)
        if grade.state == "graded":
            fraction, state = grade.fraction, "graded"
        elif grade.state == "none" and is_closed(quiz, person, now):
            fraction, state = Decimal(0), "zero"
        else:
            fraction, state = None, "pending" if grade.state == "pending" else "not_due"
        items.append(Item("quiz", quiz.id, quiz.title, quiz.grade_category_id, quiz.weight, fraction, state))
    return items


def _practical_items(site, person, released_only, now) -> list[Item]:
    from practicals.services import coursework_tasks

    return [
        Item("practical", task.id, task.title, task.grade_category_id, task.weight, fraction, state)
        for task, fraction, state in coursework_tasks(site, person, released_only=released_only, now=now)
    ]


def _forum_items(site, person, released_only) -> list[Item]:
    from forums.services import coursework_forums

    return [
        Item("forum", forum.id, forum.title, forum.grade_category_id, forum.weight, fraction, state)
        for forum, fraction, state in coursework_forums(site, person, released_only=released_only)
    ]


def _package_items(site, person) -> list[Item]:
    from packages.services import coursework_packages

    return [
        Item(
            "package",
            package.id,
            package.item.title,
            package.grade_category_id,
            package.weight,
            fraction,
            state,
        )
        for package, fraction, state in coursework_packages(site, person)
    ]


def coursework_working(site, person, *, released_only: bool = False, now=None) -> dict:
    """The coursework total and how it was worked out: every item with its state, and every category."""
    now = now or timezone.now()
    items = (
        _assignment_items(site, person, released_only, now)
        + _quiz_items(site, person, released_only, now)
        + _practical_items(site, person, released_only, now)
        + _forum_items(site, person, released_only)
        + _package_items(site, person)
    )
    categories = list(GradeCategory.objects.filter(site=site))
    known = {c.id for c in categories}
    for item in items:
        if item.category_id not in known:
            item.category_id = None  # a category of another site, which cannot happen through the API
    rows, weighted, weight_total = [], Decimal(0), Decimal(0)
    for category in [*categories, None]:
        members = [i for i in items if i.category_id == (category.id if category else None)]
        if category is None and not members:
            continue
        counted = [i for i in members if i.state in COUNTED]
        drop = category.drop_lowest if category else 0
        if drop and len(counted) > 1:
            for item in sorted(counted, key=lambda i: (i.fraction, i.weight))[: min(drop, len(counted) - 1)]:
                item.dropped = True
            counted = [i for i in counted if not i.dropped]
        item_weight = sum((i.weight for i in counted), Decimal(0))
        earned = sum((i.earned for i in counted), Decimal(0))
        fraction = earned / item_weight if item_weight else None
        cat_weight = category.weight if category else item_weight
        if fraction is not None:
            weighted += cat_weight * fraction if category else earned
            weight_total += cat_weight
        rows.append(
            {
                "id": category.id if category else None,
                "name": category.name if category else "Not in a category",
                "weight": str(cat_weight) if category else str(item_weight),
                "drop_lowest": drop,
                "percent": _pct(fraction),
                "counted": fraction is not None,
            }
        )
    total = None
    if weight_total:
        total = (weighted / weight_total * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return {
        "coursework_percent": str(total) if total is not None else None,
        "uses_categories": bool(categories),
        "categories": rows,
        "items": [i.as_dict() for i in items],
        "_total": total,
    }


def coursework_percent(site, person, *, released_only: bool = False, now=None) -> Decimal | None:
    """Weighted coursework percentage for one student, or None when nothing counts yet.

    A marked assignment counts with its mark, less any late penalty. An assignment past the student's due
    date (extensions and accommodations included) with no submission counts as zero. A submitted but
    unmarked assignment is pending and does not count.
    A quiz counts like an assignment: its grade (by the quiz's grading method) as a share of its maximum.
    A closed quiz with no attempt counts as zero. An attempt awaiting marking (or, for the student's own
    view, awaiting release) is pending and does not count.
    A practical task with a weight counts by its latest observation; a closed task never observed counts
    as zero; a task not yet observed (or not released, for the student's own view) is pending.
    A graded forum with a weight counts by the participation mark; with none given (or released) it is
    pending.
    A SCORM or H5P package with a weight counts by the learner's best scored attempt (packages.services).
    Categories, when the site has them, weight the parts (module docstring).
    """
    return coursework_working(site, person, released_only=released_only, now=now)["_total"]


def public_working(site, person, *, released_only: bool) -> dict:
    working = coursework_working(site, person, released_only=released_only)
    working.pop("_total")
    return working


def gradebook(site, *, only_person=None, released_only: bool = False) -> dict:
    from assessments.rules import label_for
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
            # While names are hidden, the class list does not show an anonymous assignment's marks (3.16).
            hidden = assignment.names_hidden and not released_only
            shown = penalised(submission, mark.mark) if visible and not hidden else None
            marks[str(assignment.id)] = {
                "submitted": submission is not None,
                "late": bool(submission and submission.is_late),
                "mark": str(shown.final) if shown else None,
                "raw_mark": str(shown.raw) if shown else None,
                "penalty": str(shown.penalty) if shown else None,
                "feedback": mark.feedback if shown else "",
                "anonymous": hidden,
            }
            if hidden and submission is not None:
                marks[str(assignment.id)]["label"] = label_for(submission)
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
        working = coursework_working(site, person, released_only=released_only)
        others = {
            kind: {
                str(i["id"]): {"state": i["state"], "percent": i["percent"]}
                for i in working["items"]
                if i["kind"] == kind
            }
            for kind in ("practical", "forum", "package")
        }
        rows.append(
            {
                "person_id": person.id,
                "student_no": person.external_id,
                "name": person.full_name,
                "marks": marks,
                "quizzes": quiz_marks,
                "practicals": others["practical"],
                "forums": others["forum"],
                "packages": others["package"],
                "categories": {str(c["id"]): c["percent"] for c in working["categories"] if c["id"]},
                "coursework_percent": working["coursework_percent"],
                "srms": _srms_state(site, person),
            }
        )
    return {
        "site": site.code,
        "categories": [
            {"id": c.id, "name": c.name, "weight": str(c.weight), "drop_lowest": c.drop_lowest}
            for c in GradeCategory.objects.filter(site=site)
        ],
        "assignments": [
            {
                "id": a.id,
                "title": a.title,
                "max_mark": str(a.max_mark),
                "weight": str(a.weight),
                "category": a.category_id,
            }
            for a in assignments
        ],
        "quizzes": [
            {
                "id": q.id,
                "title": q.title,
                "weight": str(q.weight),
                "counts": q.counts,
                "grading_method": q.grading_method,
                "category": q.grade_category_id,
            }
            for q in quizzes
        ],
        "practicals": [
            {"id": t.id, "title": t.title, "weight": str(t.weight), "category": t.grade_category_id}
            for t in site.practical_tasks.filter(is_published=True, weight__gt=0)
        ],
        "forums": [
            {"id": f.id, "title": f.title, "weight": str(f.weight), "category": f.grade_category_id}
            for f in site.forums.filter(is_published=True, forum_type="graded", weight__gt=0)
        ],
        "packages": _package_columns(site),
        "rows": rows,
    }


def _package_columns(site) -> list[dict]:
    from packages.models import ContentPackage

    packages = ContentPackage.objects.filter(item__module__site=site, item__is_published=True, weight__gt=0)
    return [
        {"id": p.id, "title": p.item.title, "weight": str(p.weight), "category": p.grade_category_id}
        for p in packages.select_related("item").order_by("item__module__position", "item__position", "id")
    ]


def _srms_state(site, person) -> dict | None:
    """What the SRMS last answered for the student's coursework on the site; marks it holds are locked
    (item 3.18), shown on the gradebook and the marks."""
    from assessments.rules import srms_lock

    latest = SrmsTransfer.objects.filter(site=site, student=person).order_by("-sent_at", "-id").first()
    if latest is None:
        return None
    lock = srms_lock(site, person)
    return {
        "outcome": latest.outcome,
        "percent": str(latest.percent),
        "sent_at": latest.sent_at.isoformat(),
        "locked_since": lock.sent_at.isoformat() if lock else None,
    }
