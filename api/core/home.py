"""Home (items 2.07 to 2.09): what each person's Home shows first, worked out in one request.

Which Home a person gets follows what they do: a system administrator, a course administrator, someone
who teaches, a student, or an office role (auditor, Data Protection Officer) with nothing to teach or
study. Each block counts only what the person may open, by the same rules as the page it leads to, so a
figure on Home never promises more than its page shows.

A student sees the work due this week, work overdue, feedback released lately and their progress on each
course. Someone who teaches sees what is waiting to be marked on the sites they teach, the sites that are
quiet this week and the students who have not been seen for a while. Course administrators and system
administrators also see figures for every site.
"""

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Exists, F, Min, OuterRef, Q, Subquery
from django.db.models.functions import Greatest
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from assessments.models import Assignment, Mark, Submission
from audit.models import AuditLog
from core.serializers import ErrorSerializer
from courses.access import person_of
from courses.models import ContentItem, CourseSite, Membership, TakedownRequest
from courses.release import item_open, student_state
from iam.models import Role, UserSession
from iam.permissions import RolePermission
from iam.services import TEACHING_SITE_ROLES, has_role, teaches
from people.models import PersonRef

DUE_DAYS = 7  # work due within this many days is "due this week"
OVERDUE_DAYS = 30  # overdue work older than this is no longer listed
FEEDBACK_DAYS = 14  # feedback released within this many days is listed
QUIET_DAYS = 7  # a site with nothing new or opening within this many days is quiet
NOT_SEEN_DAYS = 14  # students not seen for this many days are listed
NOT_SEEN_SHOWN = 10

# The roles as people say them, widest first.
TITLES = (
    (Role.ADMINISTRATOR, "System administrator"),
    (Role.COURSE_ADMIN, "Course administrator"),
    (Role.LECTURER, "Lecturer"),
    (Role.STUDENT, "Student"),
    (Role.DPO, "Data Protection Officer"),
    (Role.AUDITOR, "Auditor"),
)


# ---------------------------------------------------------------------------------------------------------
# Who the person is


def student_sites(person):
    """Published sites on which the person is an active student, by title."""
    if person is None:
        return CourseSite.objects.none()
    return CourseSite.objects.filter(
        is_published=True,
        memberships__person=person,
        memberships__is_active=True,
        memberships__role=Membership.SiteRole.STUDENT,
    ).order_by("title", "id")


def teaching_sites(person):
    """Sites on which the person is an active lecturer or teaching assistant (not every site for a course
    administrator: their own teaching only)."""
    if person is None:
        return CourseSite.objects.none()
    return (
        CourseSite.objects.filter(
            memberships__person=person,
            memberships__is_active=True,
            memberships__role__in=TEACHING_SITE_ROLES,
        )
        .distinct()
        .order_by("code")
    )


def persona(user) -> str:
    """Which Home a person sees. A person with several roles gets the one with the widest view."""
    if has_role(user, Role.ADMINISTRATOR):
        return "admin"
    if has_role(user, Role.COURSE_ADMIN):
        return "course_admin"
    if has_role(user, Role.LECTURER) or teaches(user):
        return "lecturer"
    if has_role(user, Role.STUDENT) or student_sites(person_of(user)).exists():
        return "student"
    return "office"


def title(user) -> str:
    """The person's role as people say it, for example "Lecturer, AGR101"; empty when they hold none."""
    person = person_of(user)
    for code, words in TITLES:
        held = has_role(user, code)
        if code == Role.LECTURER:
            held = held or teaches(user)
        elif code == Role.STUDENT:
            held = held or student_sites(person).exists()
        if held:
            if code == Role.LECTURER:
                first = teaching_sites(person).first()
                if first is not None:
                    return f"{words}, {first.code.split('-')[0]}"
            return words
    return ""


# ---------------------------------------------------------------------------------------------------------
# A student's Home


def _number(value) -> str:
    """A mark as people write it: 38, 38.5, never 38.00."""
    text = f"{Decimal(value):f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _work(kind: str, record, due_at: datetime, can_still_submit: bool) -> dict:
    site = record.site
    return {
        "kind": kind,
        "id": record.id,
        "title": record.title,
        "site_id": site.id,
        "site_code": site.code,
        "site_title": site.title,
        "due_at": due_at,
        "link": f"/sites/{site.id}/{'assignments' if kind == 'assignment' else 'quizzes'}",
        "can_still_submit": can_still_submit,
    }


def student_work(person, now: datetime) -> tuple[list[dict], list[dict]]:
    """(due, overdue): work not handed in on the person's courses.

    Due: assignments and quizzes due between now and DUE_DAYS ahead, soonest first. A quiz counts by its
    closing time for this student (an override can move it) and only while it has no finished attempt;
    a quiz that never closes is not listed. Overdue: assignments due in the last OVERDUE_DAYS and not
    handed in, oldest first; whether they can still be handed in follows the assignment's late rule.
    Work that has not opened yet is not listed.
    """
    from quizzes.models import Attempt, Quiz
    from quizzes.services import effective

    sites = student_sites(person)
    horizon = now + timedelta(days=DUE_DAYS)
    handed_in = Submission.objects.filter(assignment=OuterRef("pk"), student=person)
    assignments = (
        Assignment.objects.filter(
            site__in=sites, is_published=True, due_at__gte=now - timedelta(days=OVERDUE_DAYS)
        )
        .filter(Q(opens_at__isnull=True) | Q(opens_at__lte=now), due_at__lte=horizon)
        .exclude(Exists(handed_in))
        .select_related("site")
    )
    due, overdue = [], []
    for assignment in assignments:
        if assignment.due_at >= now:
            due.append(_work("assignment", assignment, assignment.due_at, True))
        else:
            overdue.append(_work("assignment", assignment, assignment.due_at, assignment.allow_late))
    finished = Attempt.objects.filter(quiz=OuterRef("pk"), student=person, state=Attempt.State.FINISHED)
    quizzes = (
        Quiz.objects.filter(site__in=sites, is_published=True)
        .filter(Q(opens_at__isnull=True) | Q(opens_at__lte=now))
        .exclude(Exists(finished))
        .select_related("site")
    )
    for quiz in quizzes:
        closes_at = effective(quiz, person).closes_at
        if closes_at is not None and now <= closes_at <= horizon:
            due.append(_work("quiz", quiz, closes_at, True))
    due.sort(key=lambda work: work["due_at"])
    overdue.sort(key=lambda work: work["due_at"])
    return due, overdue


def _feedback(person, sites, now: datetime) -> list[dict]:
    """Marks, quiz results and practical observations released to the student lately, newest first."""
    from practicals.models import Observation
    from quizzes.models import Attempt
    from quizzes.services import student_sees_marks

    since = now - timedelta(days=FEEDBACK_DAYS)
    rows = []
    marks = Mark.objects.filter(
        submission__student=person,
        submission__assignment__site__in=sites,
        is_released=True,
        updated_at__gte=since,
    ).select_related("submission__assignment__site")
    for mark in marks:
        assignment = mark.submission.assignment
        rows.append(
            {
                "kind": "assignment",
                "id": assignment.id,
                "title": assignment.title,
                "site_id": assignment.site_id,
                "site_title": assignment.site.title,
                "released_at": mark.updated_at,
                "result": f"{_number(mark.mark)} out of {_number(assignment.max_mark)}",
                "link": f"/sites/{assignment.site_id}/assignments",
            }
        )
    attempts = Attempt.objects.filter(
        student=person,
        quiz__site__in=sites,
        state=Attempt.State.FINISHED,
        is_released=True,
        released_at__gte=since,
    ).select_related("quiz__site", "student")
    for attempt in attempts:
        if not student_sees_marks(attempt, now) or attempt.percent is None:
            continue  # released, but the quiz's review options keep the mark back for now
        quiz = attempt.quiz
        percent = Decimal(attempt.percent).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        rows.append(
            {
                "kind": "quiz",
                "id": quiz.id,
                "title": quiz.title,
                "site_id": quiz.site_id,
                "site_title": quiz.site.title,
                "released_at": attempt.released_at,
                "result": f"{percent}%",
                "link": f"/sites/{quiz.site_id}/quizzes",
            }
        )
    observations = (
        Observation.objects.filter(
            student=person, task__site__in=sites, is_released=True, released_at__gte=since
        )
        .select_related("task__site")
        .prefetch_related("results__criterion")
    )
    for observation in observations:
        task = observation.task
        earned, possible = observation.score()
        result = f"{earned} out of {possible}"
        if not observation.critical_passed():
            result += ", a critical point not yet met"
        rows.append(
            {
                "kind": "practical",
                "id": task.id,
                "title": task.title,
                "site_id": task.site_id,
                "site_title": task.site.title,
                "released_at": observation.released_at,
                "result": result,
                "link": f"/sites/{task.site_id}/practicals",
            }
        )
    return sorted(rows, key=lambda row: row["released_at"], reverse=True)


def _progress(person, sites) -> list[dict]:
    """Per course: how many of the items released to the student they have completed, and coursework."""
    from assessments.services import coursework_percent

    state = student_state(person)
    items = (
        ContentItem.objects.filter(module__site__in=sites)
        .select_related("module")
        .prefetch_related("groups", "module__groups")
    )
    released: dict[int, list[int]] = {}
    for item in items:
        if item_open(item, state):
            released.setdefault(item.module.site_id, []).append(item.id)
    rows = []
    for site in sites:
        ids = released.get(site.id, [])
        completed = sum(1 for item_id in ids if item_id in state.completed)
        total = coursework_percent(site, person, released_only=True)
        rows.append(
            {
                "site_id": site.id,
                "code": site.code,
                "title": site.title,
                "completed": completed,
                "released": len(ids),
                "share": completed / len(ids) if ids else 0.0,
                "coursework_percent": str(total) if total is not None else None,
            }
        )
    return rows


def _student(person, now: datetime) -> dict | None:
    sites = list(student_sites(person))
    if not sites:
        return None
    due, overdue = student_work(person, now)
    return {
        "due": due,
        "overdue": overdue,
        "feedback": _feedback(person, sites, now),
        "progress": _progress(person, sites),
    }


# ---------------------------------------------------------------------------------------------------------
# A teacher's Home


def _marking(kind: str, site_id: int, site_title: str, what: str, count: int, oldest, link: str) -> dict:
    return {
        "kind": kind,
        "site_id": site_id,
        "site_title": site_title,
        "title": what,
        "count": count,
        "oldest": oldest,
        "link": link,
    }


def to_mark(person) -> list[dict]:
    """What waits for the teaching staff on the sites the person teaches, one row per piece of work,
    oldest first: submissions with no mark, quiz answers to mark by hand, practical observations not yet
    released, and logbook entries waiting for sign-off."""
    from practicals.models import LogbookEntry, Observation
    from quizzes.models import Attempt

    sites = teaching_sites(person)
    rows = []
    submissions = (
        Submission.objects.filter(assignment__site__in=sites, mark__isnull=True)
        .values("assignment_id", "assignment__title", "assignment__site_id", "assignment__site__title")
        .annotate(n=Count("id"), oldest=Min("submitted_at"))
    )
    for row in submissions:
        site_id = row["assignment__site_id"]
        rows.append(
            _marking(
                "submission",
                site_id,
                row["assignment__site__title"],
                f"{row['assignment__title']}: {row['n']} to mark",
                row["n"],
                row["oldest"],
                f"/sites/{site_id}/assignments",
            )
        )
    answers = (
        Attempt.objects.filter(quiz__site__in=sites, state=Attempt.State.FINISHED, needs_grading=True)
        .values("quiz_id", "quiz__title", "quiz__site_id", "quiz__site__title")
        .annotate(n=Count("id"), oldest=Min("submitted_at"))
    )
    for row in answers:
        site_id = row["quiz__site_id"]
        rows.append(
            _marking(
                "quiz_answer",
                site_id,
                row["quiz__site__title"],
                f"{row['quiz__title']}: {row['n']} to mark",
                row["n"],
                row["oldest"],
                f"/sites/{site_id}/quizzes",
            )
        )
    observations = (
        Observation.objects.filter(task__site__in=sites, is_released=False)
        .values("task_id", "task__title", "task__site_id", "task__site__title")
        .annotate(n=Count("id"), oldest=Min("observed_at"))
    )
    for row in observations:
        site_id = row["task__site_id"]
        rows.append(
            _marking(
                "observation",
                site_id,
                row["task__site__title"],
                f"{row['task__title']}: {row['n']} to release",
                row["n"],
                row["oldest"],
                f"/sites/{site_id}/practicals",
            )
        )
    entries = (
        LogbookEntry.objects.filter(site__in=sites, status=LogbookEntry.Status.PENDING)
        .values("site_id", "site__title")
        .annotate(n=Count("id"), oldest=Min("created_at"))
    )
    for row in entries:
        site_id = row["site_id"]
        rows.append(
            _marking(
                "logbook",
                site_id,
                row["site__title"],
                f"Logbook: {row['n']} to sign off",
                row["n"],
                row["oldest"],
                f"/sites/{site_id}/logbook",
            )
        )
    return sorted(rows, key=lambda row: row["oldest"])


def _opens(item: ContentItem) -> datetime | None:
    """When the item is shown to students by date: the later of its own date and its module's."""
    dates = [d for d in (item.available_from, item.module.available_from) if d is not None]
    return max(dates) if dates else None


def _quiet_sites(person, now: datetime) -> list[dict]:
    """Published sites the person teaches with nothing new for students this week and nothing due to open
    in the next QUIET_DAYS days. "New" is a published item, not under review, put up in the last
    QUIET_DAYS days; "due to open" is one whose date (its own or its module's) falls within the next
    QUIET_DAYS days. Each quiet site says when its next dated item opens, if any does."""
    sites = list(teaching_sites(person).filter(is_published=True))
    if not sites:
        return []
    week_ago, horizon = now - timedelta(days=QUIET_DAYS), now + timedelta(days=QUIET_DAYS)
    items = ContentItem.objects.filter(
        module__site__in=sites, is_published=True, under_review=False
    ).select_related("module")
    items = items.filter(
        Q(created_at__gte=week_ago) | Q(available_from__gt=now) | Q(module__available_from__gt=now)
    )
    busy: set[int] = set()
    next_at: dict[int, datetime] = {}
    for item in items:
        site_id = item.module.site_id
        opens = _opens(item)
        if opens is not None and opens > now:
            next_at[site_id] = min(next_at.get(site_id, opens), opens)
            if opens <= horizon:
                busy.add(site_id)
        elif item.created_at >= week_ago:
            busy.add(site_id)
    return [
        {"site_id": site.id, "code": site.code, "title": site.title, "next_item_at": next_at.get(site.id)}
        for site in sites
        if site.id not in busy
    ]


def last_seen(people):
    """The people, each with `seen`: the latest of their sessions' last activity and their sign-ins."""
    sessions = UserSession.objects.filter(user=OuterRef("user")).order_by("-last_seen_at")
    logins = AuditLog.objects.filter(actor=OuterRef("user"), action="login").order_by("-at")
    return people.annotate(
        seen=Greatest(
            Subquery(sessions.values("last_seen_at")[:1]),
            Subquery(logins.values("at")[:1]),
        )
    )


def _not_seen(person, now: datetime) -> tuple[list[dict], int]:
    """Active students on the sites the person teaches not seen for NOT_SEEN_DAYS days, or never, never
    seen first and then the longest ago. A student with no account has never been seen."""
    sites = teaching_sites(person)
    members = Membership.objects.filter(site__in=sites, is_active=True, role=Membership.SiteRole.STUDENT)
    students = last_seen(PersonRef.objects.filter(pk__in=members.values("person_id")))
    cutoff = now - timedelta(days=NOT_SEEN_DAYS)
    absent = students.filter(Q(seen__isnull=True) | Q(seen__lt=cutoff))
    count = absent.count()
    never_first = F("seen").asc(nulls_first=True)
    shown = list(absent.order_by(never_first, "last_name", "first_name")[:NOT_SEEN_SHOWN])
    titles: dict[int, list[str]] = {}
    for person_id, site_title in (
        members.filter(person__in=[p.id for p in shown])
        .order_by("site__title")
        .values_list("person_id", "site__title")
    ):
        titles.setdefault(person_id, []).append(site_title)
    rows = [
        {
            "person_id": p.id,
            "name": p.full_name,
            "student_no": p.external_id,
            "sites": titles.get(p.id, []),
            "last_seen": p.seen,
        }
        for p in shown
    ]
    return rows, count


def _teaching(person, now: datetime) -> dict | None:
    if person is None or not teaching_sites(person).exists():
        return None
    absent, count = _not_seen(person, now)
    return {
        "to_mark": to_mark(person),
        "quiet_sites": _quiet_sites(person, now),
        "not_seen": absent,
        "not_seen_count": count,
        "not_seen_days": NOT_SEEN_DAYS,
    }


# ---------------------------------------------------------------------------------------------------------
# Figures for administrators


def _sites() -> dict:
    """Figures for every site: how many, published or draft, without a lecturer, students, takedowns."""
    lecturer = Membership.objects.filter(
        site=OuterRef("pk"), is_active=True, role=Membership.SiteRole.LECTURER
    )
    figures = CourseSite.objects.aggregate(
        total=Count("id"),
        published=Count("id", filter=Q(is_published=True)),
    )
    return {
        "total": figures["total"],
        "published": figures["published"],
        "drafts": figures["total"] - figures["published"],
        "without_teacher": CourseSite.objects.exclude(Exists(lecturer)).count(),
        "students": Membership.objects.filter(is_active=True, role=Membership.SiteRole.STUDENT)
        .values("person_id")
        .distinct()
        .count(),
        "open_takedowns": TakedownRequest.objects.filter(status=TakedownRequest.Status.OPEN).count(),
    }


def summary(user) -> dict:
    from core.todo import to_do_for

    now = timezone.now()
    kind = persona(user)
    person = person_of(user)
    return {
        "persona": kind,
        "as_at": timezone.localdate(),
        "waiting": len(to_do_for(user)),
        "student": _student(person, now) if person is not None else None,
        "teaching": _teaching(person, now),
        "sites": _sites() if kind in ("admin", "course_admin") else None,
    }


# ---------------------------------------------------------------------------------------------------------
# The response, documented


class WorkSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["assignment", "quiz"])
    id = serializers.IntegerField()
    title = serializers.CharField()
    site_id = serializers.IntegerField()
    site_code = serializers.CharField()
    site_title = serializers.CharField()
    due_at = serializers.DateTimeField(help_text="For a quiz, when it closes for this student")
    link = serializers.CharField(help_text="Where it is handed in, in the web app")
    can_still_submit = serializers.BooleanField(help_text="False when overdue and late work is refused")


class FeedbackSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["assignment", "quiz", "practical"])
    id = serializers.IntegerField(help_text="The assignment, quiz or practical task")
    title = serializers.CharField()
    site_id = serializers.IntegerField()
    site_title = serializers.CharField()
    released_at = serializers.DateTimeField()
    result = serializers.CharField(help_text="In words: '38 out of 50', '76%' or '7 out of 9'")
    link = serializers.CharField()


class ProgressSerializer(serializers.Serializer):
    site_id = serializers.IntegerField()
    code = serializers.CharField()
    title = serializers.CharField()
    completed = serializers.IntegerField(help_text="Items completed, of those released to the student")
    released = serializers.IntegerField(help_text="Items the student can see now")
    share = serializers.FloatField(help_text="completed / released, from 0 to 1; 0 when nothing is released")
    coursework_percent = serializers.CharField(
        allow_null=True, help_text="Released coursework so far, as a percentage; null when nothing counts yet"
    )


class StudentBlockSerializer(serializers.Serializer):
    due = WorkSerializer(
        many=True, help_text=f"Not handed in, due in the next {DUE_DAYS} days, soonest first"
    )
    overdue = WorkSerializer(
        many=True, help_text=f"Assignments not handed in, due in the last {OVERDUE_DAYS} days, oldest first"
    )
    feedback = FeedbackSerializer(many=True, help_text=f"Released in the last {FEEDBACK_DAYS} days")
    progress = ProgressSerializer(many=True, help_text="One per course, by title")


class MarkingSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["submission", "quiz_answer", "observation", "logbook"])
    site_id = serializers.IntegerField()
    site_title = serializers.CharField()
    title = serializers.CharField(help_text="For example 'Soil sampling report: 3 to mark'")
    count = serializers.IntegerField()
    oldest = serializers.DateTimeField(help_text="When the longest-waiting one came in")
    link = serializers.CharField()


class QuietSiteSerializer(serializers.Serializer):
    site_id = serializers.IntegerField()
    code = serializers.CharField()
    title = serializers.CharField()
    next_item_at = serializers.DateTimeField(allow_null=True, help_text="When the next dated item opens")


class AbsentSerializer(serializers.Serializer):
    person_id = serializers.IntegerField()
    name = serializers.CharField()
    student_no = serializers.CharField()
    sites = serializers.ListField(child=serializers.CharField(), help_text="Titles of the sites taught")
    last_seen = serializers.DateTimeField(allow_null=True, help_text="Null when never seen")


class TeachingBlockSerializer(serializers.Serializer):
    to_mark = MarkingSerializer(many=True, help_text="Oldest first")
    quiet_sites = QuietSiteSerializer(
        many=True,
        help_text=f"Nothing new for students this week and nothing due to open in {QUIET_DAYS} days",
    )
    not_seen = AbsentSerializer(many=True, help_text=f"At most {NOT_SEEN_SHOWN}, never seen first")
    not_seen_count = serializers.IntegerField()
    not_seen_days = serializers.IntegerField()


class SiteFiguresSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    published = serializers.IntegerField()
    drafts = serializers.IntegerField()
    without_teacher = serializers.IntegerField(help_text="Sites with no active lecturer")
    students = serializers.IntegerField(help_text="Different people who are students on some site")
    open_takedowns = serializers.IntegerField()


class HomeSerializer(serializers.Serializer):
    persona = serializers.ChoiceField(
        choices=["admin", "course_admin", "lecturer", "student", "office"], help_text="Which Home to show"
    )
    as_at = serializers.DateField()
    waiting = serializers.IntegerField(help_text="How many things are on my To do list")
    student = StudentBlockSerializer(allow_null=True, help_text="Null unless the person studies a course")
    teaching = TeachingBlockSerializer(allow_null=True, help_text="Null unless the person teaches a site")
    sites = SiteFiguresSerializer(allow_null=True, help_text="Administrators only: every site")


@extend_schema(
    responses={200: HomeSerializer, 403: ErrorSerializer},
    summary="What my Home shows: my work, my teaching, and figures for my role",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def home(request):
    return Response(HomeSerializer(summary(request.user)).data)
