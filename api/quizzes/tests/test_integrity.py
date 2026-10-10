"""Secure exam mode and the integrity log (item 3.25).

The LMS has no lockdown browser, no webcam proctoring and no AI-writing detector (ADR 0006): these tests
check what a web page actually can do -- a single enforced attempt, server-side timing (already covered in
test_api.py) and a plain, descriptive timeline of focus changes and copy/paste/right-click attempts, visible
to the site's teaching staff only.
"""

import pytest

from audit.models import AuditLog
from quizzes import services
from quizzes.models import Attempt, AttemptEvent, Quiz


@pytest.mark.django_db
def test_secure_exam_forces_one_attempt_and_refuses_to_be_a_practice_quiz(site, lecturer, client_for):
    teacher = client_for(lecturer.user)
    made = teacher.post(
        "/api/v1/quizzes/",
        {"site": site.id, "title": "Final exam", "is_secure_exam": True, "attempts_allowed": 5},
        format="json",
    )
    assert made.status_code == 201
    assert made.json()["is_secure_exam"] is True and made.json()["attempts_allowed"] == 1
    assert AuditLog.objects.filter(entity="quizzes.quiz", action="create").exists()

    both = teacher.post(
        "/api/v1/quizzes/",
        {"site": site.id, "title": "Bad", "is_secure_exam": True, "is_practice": True},
        format="json",
    )
    assert both.status_code == 400 and "is_secure_exam" in both.json()

    # Turning secure exam mode on for an existing quiz with several attempts also forces it back to one.
    quiz_id = made.json()["id"]
    changed = teacher.patch(f"/api/v1/quizzes/{quiz_id}/", {"attempts_allowed": 3}, format="json")
    assert changed.status_code == 200 and changed.json()["attempts_allowed"] == 1


@pytest.mark.django_db
def test_integrity_events_are_kept_only_for_an_in_progress_secure_exam_with_a_recognised_kind(
    site, student, make_question, make_quiz
):
    secure = make_quiz([make_question()], is_secure_exam=True, attempts_allowed=1)
    ordinary = make_quiz([make_question()], title="Weekly quiz")
    attempt, _ = services.start_attempt(secure, student, student.user)
    other_attempt, _ = services.start_attempt(ordinary, student, student.user)

    # Not a secure exam: nothing is kept, but nothing is refused either (the caller gets on with the quiz).
    assert services.record_integrity_event(other_attempt, AttemptEvent.Kind.FOCUS_LOST, student.user) is None
    assert other_attempt.events.filter(kind__in=AttemptEvent.INTEGRITY_KINDS).count() == 0

    # A kind the server does not recognise as an integrity event is dropped.
    assert services.record_integrity_event(attempt, "marked", student.user) is None

    kept = services.record_integrity_event(attempt, AttemptEvent.Kind.FOCUS_LOST, student.user)
    assert kept is not None and kept.kind == "focus_lost"

    # Once the attempt is finished, nothing more is kept.
    attempt = services.submit_attempt(attempt, user=student.user)
    assert services.record_integrity_event(attempt, AttemptEvent.Kind.FOCUS_RESUMED, student.user) is None
    assert attempt.events.filter(kind__in=AttemptEvent.INTEGRITY_KINDS).count() == 1


@pytest.mark.django_db
def test_the_integrity_event_cap_stops_a_runaway_page_script(settings, student, make_question, make_quiz):
    settings.QUIZ_INTEGRITY_EVENT_CAP = 3
    quiz = make_quiz([make_question()], is_secure_exam=True, attempts_allowed=1)
    attempt, _ = services.start_attempt(quiz, student, student.user)
    for _ in range(5):
        services.record_integrity_event(attempt, AttemptEvent.Kind.FOCUS_LOST, student.user)
    assert attempt.events.filter(kind__in=AttemptEvent.INTEGRITY_KINDS).count() == 3


@pytest.mark.django_db
def test_only_the_sitting_student_may_report_an_integrity_event(
    site, lecturer, student, other_student, client_for, make_question, make_quiz
):
    quiz = make_quiz([make_question()], is_secure_exam=True, attempts_allowed=1)
    learner, intruder, teacher = (
        client_for(student.user),
        client_for(other_student.user),
        client_for(lecturer.user),
    )
    aid = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()["id"]
    url = f"/api/v1/quiz-attempts/{aid}/integrity-event/"

    assert intruder.post(url, {"kind": "focus_lost"}, format="json").status_code == 403
    assert teacher.post(url, {"kind": "focus_lost"}, format="json").status_code == 403
    assert learner.post(url, {"kind": "not_a_real_kind"}, format="json").status_code == 400

    mine = learner.post(url, {"kind": "focus_lost"}, format="json")
    assert mine.status_code == 204
    assert AttemptEvent.objects.filter(attempt_id=aid, kind="focus_lost").count() == 1

    for kind in ("focus_resumed", "copy_attempted", "paste_attempted", "context_menu_blocked"):
        assert learner.post(url, {"kind": kind}, format="json").status_code == 204
    assert AttemptEvent.objects.filter(attempt_id=aid, kind__in=AttemptEvent.INTEGRITY_KINDS).count() == 5


@pytest.mark.django_db
def test_the_integrity_log_is_descriptive_and_for_teaching_staff_only(
    site, lecturer, student, client_for, make_question, make_quiz
):
    quiz = make_quiz([make_question()], is_secure_exam=True, attempts_allowed=1)
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    aid = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()["id"]
    url = f"/api/v1/quiz-attempts/{aid}/integrity-event/"
    learner.post(url, {"kind": "focus_lost"}, format="json")
    learner.post(url, {"kind": "focus_resumed"}, format="json")
    # A mark or a release is never shown in the integrity log: it is a different timeline (events/).
    Attempt.objects.filter(pk=aid).update(state=Attempt.State.FINISHED)

    assert learner.get(f"/api/v1/quiz-attempts/{aid}/integrity-log/").status_code == 403
    log = teacher.get(f"/api/v1/quiz-attempts/{aid}/integrity-log/")
    assert log.status_code == 200
    kinds = [e["kind"] for e in log.json()]
    assert kinds == ["focus_lost", "focus_resumed"]
    assert log.json()[0]["label"] == "Left the quiz window or tab"
    assert all(set(e) == {"kind", "label", "at"} for e in log.json())


@pytest.mark.django_db
def test_an_ordinary_quiz_has_no_secure_exam_notice_in_its_attempt_payload(
    site, student, client_for, make_question, make_quiz
):
    """The deterrent and the reporting both key off the attempt payload's is_secure_exam flag."""
    quiz = make_quiz([make_question()])
    learner = client_for(student.user)
    started = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()
    assert started["is_secure_exam"] is False


@pytest.mark.django_db
def test_a_secure_exam_quiz_cannot_be_made_with_more_than_one_attempt_at_the_database(
    student, make_question, make_quiz
):
    """Defence in depth: the database constraint refuses what a careless caller of the model might allow,
    even if a future change to the serializer's validate() forgets to force attempts_allowed back to 1."""
    from django.db import IntegrityError, transaction

    quiz = make_quiz([make_question()], is_secure_exam=True, attempts_allowed=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Quiz.objects.filter(pk=quiz.pk).update(attempts_allowed=2)
