"""Items 6.01 and 6.02: course analytics for teaching staff and each student's progress, from what the LMS
already records."""

from datetime import timedelta

import pytest
from django.utils import timezone

from audit.models import AuditLog
from courses.models import CourseSite, ItemCompletion, Membership
from insights.tests.conftest import hand_in
from quizzes.models import Attempt, Quiz

pytestmark = pytest.mark.django_db


def test_lecturer_sees_what_the_class_opened_handed_in_and_scored(
    site, lecturer, student, other_student, pages, make_assignment, client_for
):
    page, handout = pages
    ItemCompletion.objects.create(person=student, item=page, completed_at=timezone.now(), how="viewed")
    AuditLog.objects.create(
        actor=student.user, action="download", entity="courses.contentitem", entity_id=handout.id
    )
    AuditLog.objects.create(  # the lecturer's own download is not the class's use
        actor=lecturer.user, action="download", entity="courses.contentitem", entity_id=handout.id
    )
    report = make_assignment("Soil report", days=-2)
    hand_in(report, student, mark=40, late=True)
    quiz = Quiz.objects.create(site=site, title="Soils quiz", is_published=True)
    Attempt.objects.create(
        quiz=quiz,
        student=other_student,
        started_at=timezone.now(),
        state="finished",
        score=3,
        max_score=4,
    )

    data = client_for(lecturer.user).get(f"/api/v1/sites/{site.id}/insights/").json()

    assert data["students"] == 2
    items = {row["title"]: row for row in data["items"]}
    assert items["Soils"]["opened"] == 1 and items["Soils"]["opened_percent"] == "50.0"
    assert items["Soils"]["downloads"] is None and items["Handout"]["downloads"] == 1
    row = data["assignments"][0]
    assert (row["handed_in"], row["late"], row["missing"], row["marked"], row["released"]) == (1, 1, 1, 1, 0)
    assert row["average_percent"] == "80.0" and row["lowest_percent"] == row["highest_percent"] == "80.0"
    quiz_row = data["quizzes"][0]
    assert quiz_row["students_attempted"] == 1 and quiz_row["average_percent"] == "75.0"
    assert quiz_row["statistics"] == f"/sites/{site.id}/quizzes/{quiz.id}/statistics"
    assert "not recorded" in data["not_recorded"]


def test_analytics_and_class_progress_are_refused_to_students_and_strangers(
    site, student, auditor, make_person, client_for
):
    stranger = make_person("staff", "E0999", "Other", "Lecturer", "lecturer")
    other = CourseSite.objects.create(code="AGR999", title="Another course", is_published=True)
    Membership.objects.create(site=other, person=stranger, role="lecturer")
    for path in ("insights", "progress", f"progress/{student.id}", "outcome-standings", "alerts", "outcomes"):
        answer = client_for(student.user).get(f"/api/v1/sites/{site.id}/{path}/")
        assert answer.status_code == 403, path
        assert client_for(auditor).get(f"/api/v1/sites/{site.id}/{path}/").status_code == 403, path
        assert client_for(stranger.user).get(f"/api/v1/sites/{site.id}/{path}/").status_code == 404, path


def test_class_progress_counts_items_work_marks_and_last_seen(
    site, lecturer, student, other_student, pages, make_assignment, client_for
):
    page, _ = pages
    opened = timezone.now() - timedelta(days=2)
    ItemCompletion.objects.create(person=student, item=page, completed_at=opened, how="viewed")
    hand_in(
        make_assignment("Soil report", days=-5), student, mark=25, when=timezone.now() - timedelta(days=6)
    )
    make_assignment("Field notes", days=-1)  # missed by both
    make_assignment("Crop plan", days=10)  # still to come
    AuditLog.objects.create(actor=student.user, action="login", entity="auth.user", subject=student.id)

    rows = client_for(lecturer.user).get(f"/api/v1/sites/{site.id}/progress/").json()

    ravi = next(r for r in rows if r["person_id"] == student.id)
    assert (ravi["items_done"], ravi["items_total"], ravi["items_percent"]) == (1, 2, "50.0")
    assert (ravi["work_done"], ravi["work_missed"], ravi["work_to_come"], ravi["work_marked"]) == (1, 1, 1, 1)
    assert ravi["coursework_percent"] is not None
    assert ravi["last_seen"] is not None and ravi["last_signed_in"] is not None
    assert ravi["open_alerts"] == 0
    devi = next(r for r in rows if r["person_id"] == other_student.id)
    assert devi["last_seen"] is None and devi["items_done"] == 0 and devi["work_missed"] == 2


def test_a_student_sees_only_their_own_progress_from_released_marks(
    site, lecturer, student, other_student, make_assignment, client_for
):
    hand_in(make_assignment("Released", days=-5), student, mark=50, released=True)
    hand_in(make_assignment("Not yet released", days=-4), student, mark=10)

    mine = client_for(student.user).get(f"/api/v1/sites/{site.id}/my-progress/").json()
    staff_view = client_for(lecturer.user).get(f"/api/v1/sites/{site.id}/progress/{student.id}/").json()

    assert mine["person_id"] == student.id
    assert mine["coursework_percent"] == "100.00"  # the unreleased mark is still pending for the student
    assert staff_view["coursework_percent"] == "60.00"
    assert "open_alerts" not in mine
    assert mine["outcomes"]["students"][0]["person_id"] == student.id
    # A student never reads another's progress, nor the class list of progress.
    answer = client_for(student.user).get(f"/api/v1/sites/{site.id}/progress/{other_student.id}/")
    assert answer.status_code == 403
    assert client_for(lecturer.user).get(f"/api/v1/sites/{site.id}/my-progress/").status_code == 403
    assert (
        client_for(lecturer.user).get(f"/api/v1/sites/{site.id}/progress/{lecturer.id}/").status_code == 404
    )


def test_last_seen_is_the_latest_of_the_students_own_recorded_actions(site, student, other_student, lecturer):
    from attendance.models import AttendanceRecord, ClassSession
    from forums.models import Forum, Post, Thread
    from insights.activity import last_seen
    from messaging.models import Conversation, Message

    now = timezone.now()
    quiz = Quiz.objects.create(site=site, title="Soils quiz", is_published=True)
    Attempt.objects.create(quiz=quiz, student=student, started_at=now - timedelta(days=9))
    session = ClassSession.objects.create(
        site=site, title="Lab", starts_at=now - timedelta(days=8), ends_at=now - timedelta(days=8, hours=-1)
    )
    AttendanceRecord.objects.create(
        session=session, student=student, status="present", how="check_in", acted_at=now - timedelta(days=8)
    )
    AttendanceRecord.objects.create(  # absent is not a visit
        session=session,
        student=other_student,
        status="absent",
        how="closed",
        acted_at=now - timedelta(days=1),
    )
    thread = Thread.objects.create(forum=Forum.objects.create(site=site, title="Talk"), title="Hello")
    Post.objects.create(thread=thread, author=student.user, body="<p>Hi</p>")
    Post.objects.filter(author=student.user).update(created_at=now - timedelta(days=7))
    conversation = Conversation.objects.create(site=site, subject="Question")
    Message.objects.create(conversation=conversation, sender=student.user, body="<p>?</p>")
    Message.objects.filter(sender=student.user).update(created_at=now - timedelta(days=6))
    Message.objects.create(conversation=conversation, sender=lecturer.user, body="<p>Yes</p>")

    seen = last_seen(site, [student, other_student])

    assert abs((seen[student.id] - (now - timedelta(days=6))).total_seconds()) < 5
    assert other_student.id not in seen
