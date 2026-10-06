"""A whole class's coursework read at once, for the gradebook and the coursework send (item 7.08).

Working out one student's coursework reads their submissions, quiz attempts, overrides, extensions, practical
observations and forum marks. Done student by student for a class of sixty that was some 1,400 queries and
five seconds for one gradebook. Inside `preloaded(site)`, each of those lookups is answered from a few
queries made once for the whole class; outside it (one student's own view), the lookups query as before.
The rules themselves are untouched: the same functions decide, only where they read from changes.
"""

from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

_current: ContextVar["Preload | None"] = ContextVar("coursework_preload", default=None)


@dataclass
class Preload:
    site_id: int
    assignments: list = field(default_factory=list)
    counting_quizzes: list = field(default_factory=list)
    categories: list = field(default_factory=list)
    practical_tasks: list = field(default_factory=list)
    graded_forums: list = field(default_factory=list)
    submissions: dict = field(default_factory=lambda: defaultdict(dict))  # person -> assignment -> submission
    attempts: dict = field(default_factory=lambda: defaultdict(list))  # (quiz, person) -> attempts by number
    overrides: dict = field(default_factory=dict)  # (quiz, person) -> override
    accommodations: dict = field(default_factory=dict)  # person -> active accommodation
    extensions: dict = field(default_factory=lambda: defaultdict(list))  # assignment -> extensions
    groups: dict = field(default_factory=lambda: defaultdict(list))  # person -> group ids on the site
    observations: dict = field(default_factory=lambda: defaultdict(list))  # (task, person) -> observations
    forum_marks: dict = field(default_factory=dict)  # (forum, person) -> participation mark
    transfers: dict = field(default_factory=lambda: defaultdict(list))  # person -> SRMS transfers by time


def current(site) -> Preload | None:
    """The class's preloaded records when they are for this site, else None (look the records up)."""
    loaded = _current.get()
    site_id = getattr(site, "pk", site)
    return loaded if loaded is not None and loaded.site_id == site_id else None


def accommodations() -> dict | None:
    """Active accommodations by person, whichever site is loaded (they belong to the person)."""
    loaded = _current.get()
    return loaded.accommodations if loaded is not None else None


@contextmanager
def preloaded(site, people=None):
    """Load every record the coursework of the site's students depends on, for the length of the block."""
    from assessments.models import (
        Accommodation,
        Assignment,
        Extension,
        GradeCategory,
        SrmsTransfer,
        Submission,
    )
    from courses.models import Membership
    from forums.models import Forum, ParticipationMark
    from practicals.models import Observation, PracticalTask
    from quizzes.models import Attempt, Quiz, QuizOverride

    if people is None:
        people = list(
            Membership.objects.filter(site=site, role=Membership.SiteRole.STUDENT).values_list(
                "person_id", flat=True
            )
        )
    loaded = Preload(site_id=site.pk)
    loaded.assignments = list(Assignment.objects.filter(site=site, is_published=True).select_related("site"))
    loaded.counting_quizzes = list(
        Quiz.objects.filter(site=site, is_published=True, is_practice=False, weight__gt=0)
    )
    loaded.categories = list(GradeCategory.objects.filter(site=site))
    loaded.practical_tasks = list(PracticalTask.objects.filter(site=site, is_published=True, weight__gt=0))
    loaded.graded_forums = list(
        Forum.objects.filter(site=site, is_published=True, forum_type=Forum.Type.GRADED, weight__gt=0)
    )
    for s in Submission.objects.filter(assignment__site=site, student_id__in=people).select_related(
        "mark", "assignment", "student"
    ):
        loaded.submissions[s.student_id][s.assignment_id] = s
    for a in Attempt.objects.filter(quiz__site=site, student_id__in=people).order_by("number"):
        loaded.attempts[(a.quiz_id, a.student_id)].append(a)
    for o in QuizOverride.objects.filter(quiz__site=site, student_id__in=people).order_by("id"):
        loaded.overrides.setdefault((o.quiz_id, o.student_id), o)
    loaded.accommodations = {person: None for person in people}
    for a in Accommodation.objects.filter(person_id__in=people, is_active=True).order_by("id"):
        if loaded.accommodations.get(a.person_id) is None:
            loaded.accommodations[a.person_id] = a
    for e in Extension.objects.filter(assignment__site=site):
        loaded.extensions[e.assignment_id].append(e)
    for person_id, group_id in Membership.objects.filter(
        site=site, person_id__in=people, is_active=True
    ).values_list("person_id", "groups"):
        if group_id:
            loaded.groups[person_id].append(group_id)
    for o in (
        Observation.objects.filter(task__site=site, student_id__in=people)
        .prefetch_related("results__criterion")
        .order_by("-attempt")
    ):
        loaded.observations[(o.task_id, o.student_id)].append(o)
    for m in ParticipationMark.objects.filter(forum__site=site, student_id__in=people):
        loaded.forum_marks[(m.forum_id, m.student_id)] = m
    for t in SrmsTransfer.objects.filter(site=site, student_id__in=people).order_by("sent_at", "id"):
        loaded.transfers[t.student_id].append(t)
    token = _current.set(loaded)
    try:
        yield loaded
    finally:
        _current.reset(token)
