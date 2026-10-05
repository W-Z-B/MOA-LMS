"""Items 2.07 to 2.09: each person's Home, who they are, and only what they may open."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIClient

NOW = timezone.now


def _assignment(site, title, days, **extra):
    from assessments.models import Assignment

    fields = {"max_mark": 50, "weight": 1, "is_published": True} | extra
    return Assignment.objects.create(site=site, title=title, due_at=NOW() + timedelta(days=days), **fields)


def _submit(assignment, student, *, days_ago=0, mark=None, released=False):
    from assessments.models import Mark, Submission

    submission = Submission.objects.create(
        assignment=assignment, student=student, text="Done.", submitted_at=NOW() - timedelta(days=days_ago)
    )
    if mark is not None:
        Mark.objects.create(submission=submission, mark=mark, is_released=released)
    return submission


def _quiz(site, title, close_days=None, **extra):
    from quizzes.models import Quiz

    closes = NOW() + timedelta(days=close_days) if close_days is not None else None
    return Quiz.objects.create(site=site, title=title, closes_at=closes, is_published=True, **extra)


def _attempt(quiz, student, **extra):
    from quizzes.models import Attempt

    fields = {"state": "finished", "started_at": NOW(), "submitted_at": NOW()} | extra
    return Attempt.objects.create(quiz=quiz, student=student, **fields)


def _site(code, title, *members, published=True):
    from courses.models import CourseSite, Membership

    site = CourseSite.objects.create(code=code, title=title, is_published=published)
    for person, role in members:
        Membership.objects.create(site=site, person=person, role=role)
    return site


def _item(site, title, *, module_from=None, **extra):
    from courses.models import ContentItem, Module

    module, _ = Module.objects.get_or_create(
        site=site, title="Week 1", defaults={"available_from": module_from}
    )
    return ContentItem.objects.create(module=module, title=title, **extra)


# ---------------------------------------------------------------------------------------------------------
# Who may ask, and who they are


@pytest.mark.django_db
def test_home_refuses_anyone_not_signed_in_and_a_lecturer_without_a_code(lecturer, site):
    refused = APIClient().get("/api/v1/home/")
    assert refused.status_code == 403 and refused.json()["code"] == "not_authenticated"
    unverified = APIClient()
    unverified.force_login(lecturer.user)  # no authenticator code given in this session
    response = unverified.get("/api/v1/home/")
    assert response.status_code == 403 and response.json()["code"] == "mfa_required"


@pytest.mark.django_db
def test_persona_and_title_follow_the_widest_role(make_user, make_person, lecturer, student, site):
    from django.contrib.auth import get_user_model

    from core.home import persona, title
    from courses.models import Membership

    boss = get_user_model().objects.create_superuser("root", password="Str0ng-Passw0rd-123")
    cases = {
        boss: ("admin", "System administrator"),
        make_user("sys.admin", "administrator", "lecturer"): ("admin", "System administrator"),
        make_user("course.admin", "course_admin"): ("course_admin", "Course administrator"),
        lecturer.user: ("lecturer", "Lecturer, AGR101"),
        student.user: ("student", "Student"),
        make_user("dpo", "dpo"): ("office", "Data Protection Officer"),
        make_user("auditor", "auditor"): ("office", "Auditor"),
        make_user("nobody"): ("office", ""),
    }
    for user, expected in cases.items():
        assert (persona(user), title(user)) == expected, user.username
    # Teaching or studying a site counts even without the system role.
    helper = make_person("staff", "E0002", "Nadia", "Khan")
    Membership.objects.create(site=site, person=helper, role="assistant")
    learner = make_person("student", "26MRP0009", "Omar", "Ali")
    Membership.objects.create(site=site, person=learner, role="student")
    assert (persona(helper.user), title(helper.user)) == ("lecturer", "Lecturer, AGR101")
    assert (persona(learner.user), title(learner.user)) == ("student", "Student")


@pytest.mark.django_db
def test_me_says_which_home_and_the_role_in_words(client_for, lecturer, student, site):
    me = client_for(lecturer.user).get("/api/v1/auth/me/").json()
    assert (me["persona"], me["title"]) == ("lecturer", "Lecturer, AGR101")
    me = client_for(student.user).get("/api/v1/auth/me/").json()
    assert (me["persona"], me["title"]) == ("student", "Student")


# ---------------------------------------------------------------------------------------------------------
# A student's Home


@pytest.mark.django_db
def test_student_sees_work_due_this_week_and_overdue_work_on_their_own_courses(
    client_for, student, other_student, lecturer, site
):
    from quizzes.models import QuizOverride

    due = _assignment(site, "Plot diagram", 2)
    _submit(_assignment(site, "Handed in", 3), student)
    _assignment(site, "Draft", 2, is_published=False)
    _assignment(site, "Next month", 10)
    _assignment(site, "Not open yet", 5, opens_at=NOW() + timedelta(days=1))
    late_ok = _assignment(site, "Late allowed", -2)
    shut = _assignment(site, "Late refused", -1, allow_late=False)
    _assignment(site, "Long ago", -40)
    elsewhere = _site("HOR201-2026-27-S1-MRP", "Horticulture", (other_student, "student"))
    _assignment(elsewhere, "Not my course", 1)
    quiz = _quiz(site, "Week 2 quiz", 1)
    _attempt(_quiz(site, "Done quiz", 1), student)
    _quiz(site, "Never closes")
    moved = _quiz(site, "Moved for me", 20)
    QuizOverride.objects.create(quiz=moved, student=student, closes_at=NOW() + timedelta(days=3))
    _quiz(site, "Practice", 2, is_practice=True)

    body = client_for(student.user).get("/api/v1/home/").json()
    assert body["persona"] == "student" and body["teaching"] is None and body["sites"] is None
    block = body["student"]
    assert [(w["kind"], w["title"]) for w in block["due"]] == [
        ("quiz", "Week 2 quiz"),
        ("assignment", "Plot diagram"),
        ("quiz", "Practice"),
        ("quiz", "Moved for me"),
    ]
    first = block["due"][1]
    assert first["id"] == due.id and first["site_code"] == site.code and first["can_still_submit"] is True
    assert first["link"] == f"/sites/{site.id}/assignments"
    assert block["due"][0]["link"] == f"/sites/{site.id}/quizzes" and block["due"][0]["id"] == quiz.id
    assert [(w["id"], w["can_still_submit"]) for w in block["overdue"]] == [
        (late_ok.id, True),
        (shut.id, False),
    ]
    # Another student has handed nothing in either, but sees only their own courses.
    other = client_for(other_student.user).get("/api/v1/home/").json()["student"]
    assert "Not my course" in [w["title"] for w in other["due"]]
    assert "Not my course" not in [w["title"] for w in block["due"]]


@pytest.mark.django_db
def test_student_sees_feedback_released_to_them_lately_newest_first(
    client_for, student, other_student, lecturer, site, assignment
):
    from assessments.models import Mark
    from practicals.models import Observation, ObservationResult, PracticalCriterion, PracticalTask

    _submit(assignment, student, mark=Decimal("38.00"), released=True)
    _submit(assignment, other_student, mark=Decimal("45"), released=True)  # someone else's
    _submit(_assignment(site, "Held back", 2), student, mark=Decimal("10"), released=False)
    old = _submit(_assignment(site, "Old news", -30), student, mark=Decimal("20"), released=True)
    Mark.objects.filter(submission=old).update(updated_at=NOW() - timedelta(days=20))
    quiz = _quiz(site, "Week 1 quiz", -1)
    _attempt(quiz, student, score=19, max_score=25, is_released=True, released_at=NOW() - timedelta(days=1))
    hidden = _quiz(site, "Marks never shown", -1, review_marks="never")
    _attempt(hidden, student, score=5, max_score=5, is_released=True, released_at=NOW())
    task = PracticalTask.objects.create(site=site, title="Transplant seedlings", is_published=True)
    critical = PracticalCriterion.objects.create(task=task, text="Handles roots gently", is_critical=True)
    other = PracticalCriterion.objects.create(task=task, position=2, text="Waters in")
    seen = Observation.objects.create(
        task=task,
        student=student,
        attempt=1,
        assessor=lecturer,
        observed_at=NOW() - timedelta(days=3),
        is_released=True,
        released_at=NOW() - timedelta(days=2),
    )
    ObservationResult.objects.create(observation=seen, criterion=critical, passed=False)
    ObservationResult.objects.create(observation=seen, criterion=other, passed=True)

    feedback = client_for(student.user).get("/api/v1/home/").json()["student"]["feedback"]
    assert [(f["kind"], f["title"], f["result"]) for f in feedback] == [
        ("assignment", "Soil sampling report", "38 out of 50"),
        ("quiz", "Week 1 quiz", "76%"),
        ("practical", "Transplant seedlings", "1 out of 2, a critical point not yet met"),
    ]
    assert feedback[2]["link"] == f"/sites/{site.id}/practicals"


@pytest.mark.django_db
def test_student_progress_counts_only_items_released_to_them(client_for, student, site, assignment):
    from courses.models import ItemCompletion

    first = _item(site, "Course outline")
    _item(site, "Week 1 notes")
    _item(site, "Draft notes", is_published=False)
    _item(site, "Next week", available_from=NOW() + timedelta(days=5))
    _item(site, "Under review", under_review=True)
    ItemCompletion.objects.create(person=student, item=first, completed_at=NOW(), how="viewed")
    _submit(assignment, student, mark=Decimal("38"), released=True)

    progress = client_for(student.user).get("/api/v1/home/").json()["student"]["progress"]
    assert progress == [
        {
            "site_id": site.id,
            "code": site.code,
            "title": site.title,
            "completed": 1,
            "released": 2,
            "share": 0.5,
            "coursework_percent": "76.00",
        }
    ]


@pytest.mark.django_db
def test_a_student_on_no_published_course_has_no_student_block(client_for, make_person):
    from courses.models import Membership

    learner = make_person("student", "26MRP0010", "Lena", "Bovell", "student")
    draft = _site("DRAFT-1", "Draft course", published=False)
    Membership.objects.create(site=draft, person=learner, role="student")
    body = client_for(learner.user).get("/api/v1/home/").json()
    assert body["persona"] == "student" and body["student"] is None


# ---------------------------------------------------------------------------------------------------------
# A teacher's Home


@pytest.mark.django_db
def test_teaching_lists_what_waits_to_be_marked_on_their_own_sites_oldest_first(
    client_for, lecturer, student, other_student, site, assignment, course_admin
):
    from practicals.models import LogbookEntry, Observation, PracticalTask

    _submit(assignment, student, days_ago=3)
    _submit(assignment, other_student, days_ago=4, mark=Decimal("30"))  # already marked
    quiz = _quiz(site, "Essay quiz", -1)
    _attempt(quiz, student, needs_grading=True, submitted_at=NOW() - timedelta(days=5))
    task = PracticalTask.objects.create(site=site, title="Prune a hedge", is_published=True)
    Observation.objects.create(
        task=task, student=student, attempt=1, assessor=lecturer, observed_at=NOW() - timedelta(days=1)
    )
    LogbookEntry.objects.create(
        site=site,
        student=student,
        work_date=timezone.localdate(),
        unit_type="crop_plot",
        task="Weeded plot 7",
        hours=2,
        client_recorded_at=NOW(),
    )
    elsewhere = _site("HOR201-2026-27-S1-MRP", "Horticulture", (other_student, "student"))
    _submit(_assignment(elsewhere, "Not taught by me", 1), other_student, days_ago=9)

    teaching = client_for(lecturer.user).get("/api/v1/home/").json()["teaching"]
    assert [(m["kind"], m["title"], m["count"]) for m in teaching["to_mark"]] == [
        ("quiz_answer", "Essay quiz: 1 to mark", 1),
        ("submission", "Soil sampling report: 1 to mark", 1),
        ("observation", "Prune a hedge: 1 to release", 1),
        ("logbook", "Logbook: 1 to sign off", 1),
    ]
    assert teaching["to_mark"][1]["link"] == f"/sites/{site.id}/assignments"
    assert teaching["to_mark"][3]["link"] == f"/sites/{site.id}/logbook"
    # A course administrator who teaches nothing has no teaching block, but sees every site's figures.
    body = client_for(course_admin).get("/api/v1/home/").json()
    assert body["persona"] == "course_admin" and body["teaching"] is None and body["student"] is None


@pytest.mark.django_db
def test_quiet_sites_have_nothing_new_this_week_and_nothing_opening_soon(client_for, lecturer, site):
    from courses.models import ContentItem

    old = _item(site, "Outline")
    ContentItem.objects.filter(pk=old.pk).update(created_at=NOW() - timedelta(days=30))
    later = NOW() + timedelta(days=10)
    _item(site, "Week 6", available_from=later)
    _item(site, "Recent but under review", under_review=True)
    _item(site, "Recent draft", is_published=False)
    busy = _site("BUSY-1", "Busy course", (lecturer, "lecturer"))
    _item(busy, "Put up today")
    opening = _site("SOON-1", "Opening soon", (lecturer, "lecturer"))
    soon = _item(opening, "Week 2", module_from=NOW() + timedelta(days=3))
    ContentItem.objects.filter(pk=soon.pk).update(created_at=NOW() - timedelta(days=30))
    _site("DRAFT-2", "Unpublished course", (lecturer, "lecturer"), published=False)

    quiet = client_for(lecturer.user).get("/api/v1/home/").json()["teaching"]["quiet_sites"]
    assert [(q["code"], parse_datetime(q["next_item_at"])) for q in quiet] == [(site.code, later)]

    # Something put up for students today makes the site busy again; a site with nothing dated has no next.
    _item(site, "Put up today too")
    empty = _site("EMPTY-1", "Empty course", (lecturer, "lecturer"))
    quiet = client_for(lecturer.user).get("/api/v1/home/").json()["teaching"]["quiet_sites"]
    assert quiet == [{"site_id": empty.id, "code": "EMPTY-1", "title": "Empty course", "next_item_at": None}]


@pytest.mark.django_db
def test_not_seen_uses_sign_ins_and_sessions_never_seen_first(
    client_for, make_person, lecturer, student, site
):
    from audit.models import AuditLog
    from courses.models import Membership
    from iam.models import UserSession
    from people.models import PersonRef

    UserSession.objects.create(
        user=student.user, session_key="a" * 32, last_seen_at=NOW() - timedelta(days=2)
    )
    away = make_person("student", "26MRP0003", "Kim", "Adams")
    AuditLog.objects.create(
        actor=away.user, action="login", entity="auth.user", at=NOW() - timedelta(days=20)
    )
    both = make_person("student", "26MRP0004", "Lee", "Baptiste")
    UserSession.objects.create(user=both.user, session_key="b" * 32, last_seen_at=NOW() - timedelta(days=30))
    AuditLog.objects.create(actor=both.user, action="login", entity="auth.user", at=NOW() - timedelta(days=3))
    no_account = PersonRef.objects.create(
        kind="student", external_id="26MRP0005", first_name="Mia", last_name="Cole"
    )
    for person in (away, both, no_account):
        Membership.objects.create(site=site, person=person, role="student")
    # other_student (from the site fixture) has an account but has never signed in.

    teaching = client_for(lecturer.user).get("/api/v1/home/").json()["teaching"]
    assert [(row["name"], row["last_seen"] is None) for row in teaching["not_seen"]] == [
        ("Mia Cole", True),
        ("Devi Ramnarine", True),
        ("Kim Adams", False),
    ]
    assert teaching["not_seen_count"] == 3 and teaching["not_seen_days"] == 14
    assert teaching["not_seen"][2]["sites"] == [site.title]
    assert teaching["not_seen"][2]["student_no"] == "26MRP0003"


# ---------------------------------------------------------------------------------------------------------
# Figures for administrators


@pytest.mark.django_db
def test_administrators_see_figures_for_every_site(
    client_for, make_user, course_admin, lecturer, student, site
):
    from courses.models import TakedownRequest

    _site("DRAFT-3", "A draft with no lecturer", (student, "student"), published=False)
    TakedownRequest.objects.create(item=_item(site, "Copied chapter"), reason="Not ours to share")
    expected = {
        "total": 2,
        "published": 1,
        "drafts": 1,
        "without_teacher": 1,
        "students": 2,
        "open_takedowns": 1,
    }
    body = client_for(course_admin).get("/api/v1/home/").json()
    assert body["sites"] == expected and body["waiting"] == 1  # the takedown waits for a decision
    assert client_for(make_user("sys", "administrator")).get("/api/v1/home/").json()["sites"] == expected
    assert client_for(make_user("aud", "auditor")).get("/api/v1/home/").json()["sites"] is None
    assert client_for(lecturer.user).get("/api/v1/home/").json()["sites"] is None
