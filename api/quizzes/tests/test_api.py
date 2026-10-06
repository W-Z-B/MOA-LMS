"""Quizzes API: permissions and refusals, versions, timing, review options, marking and release."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from audit.models import AuditLog
from iam.models import Role, RoleScope
from notifications.models import Notification
from quizzes import services
from quizzes.models import Attempt, AttemptEvent, Question, QuestionBank, QuestionCategory, Quiz, QuizSlot

PDF = b"%PDF-1.4\n%test\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def put(client, attempt_id, position, response, **extra):
    return client.put(
        f"/api/v1/quiz-attempts/{attempt_id}/answers/{position}/",
        {"response": response, **extra},
        format="json",
    )


# --- banks and questions ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_only_teaching_staff_manage_a_site_bank(site, lecturer, student, make_person, client_for):
    teacher, learner = client_for(lecturer.user), client_for(student.user)
    made = teacher.post("/api/v1/question-banks/", {"name": "AGR101", "site": site.id}, format="json")
    assert made.status_code == 201 and made.json()["can_manage"] is True
    assert AuditLog.objects.filter(entity="quizzes.questionbank", action="create").exists()
    both = teacher.post(
        "/api/v1/question-banks/", {"name": "x", "site": site.id, "department_code": "CROPS"}, format="json"
    )
    assert both.status_code == 400
    assert (
        learner.post("/api/v1/question-banks/", {"name": "Mine", "site": site.id}, format="json").status_code
        == 403
    )
    assert learner.get("/api/v1/question-banks/").json()["count"] == 0
    stranger = make_person("staff", "E0099", "Other", "Lecturer", "lecturer")
    assert client_for(stranger.user).get(f"/api/v1/question-banks/{made.json()['id']}/").status_code == 404


@pytest.mark.django_db
def test_department_banks_are_shared_but_managed_by_the_department(
    site, lecturer, student, make_person, course_admin, client_for
):
    admin = client_for(course_admin)
    made = admin.post(
        "/api/v1/question-banks/", {"name": "Crops dept", "department_code": "CROPS"}, format="json"
    )
    assert made.status_code == 201
    bank_id = made.json()["id"]
    # Any lecturer can read and use it, but not change it ...
    teacher = client_for(lecturer.user)
    assert teacher.get(f"/api/v1/question-banks/{bank_id}/").json()["can_manage"] is False
    assert (
        teacher.patch(f"/api/v1/question-banks/{bank_id}/", {"name": "Mine"}, format="json").status_code
        == 403
    )
    # ... unless their lecturer role is scoped to the department.
    RoleScope.objects.create(user=lecturer.user, role=Role.objects.get(code="lecturer"), unit_code="CROPS")
    # A change of roles signs the person out everywhere (item 1.06), so they sign in again.
    assert teacher.get(f"/api/v1/question-banks/{bank_id}/").status_code in (401, 403)
    teacher = client_for(lecturer.user)
    assert (
        teacher.patch(f"/api/v1/question-banks/{bank_id}/", {"name": "Crops"}, format="json").status_code
        == 200
    )
    assert client_for(student.user).get(f"/api/v1/question-banks/{bank_id}/").status_code == 404
    owner_change = teacher.patch(
        f"/api/v1/question-banks/{bank_id}/", {"department_code": "LIV"}, format="json"
    )
    assert owner_change.status_code == 400


@pytest.mark.django_db
def test_questions_are_validated_versioned_and_kept_for_attempts(
    site, bank, category, lecturer, student, client_for, make_quiz
):
    teacher = client_for(lecturer.user)
    bad = teacher.post(
        "/api/v1/questions/",
        {
            "bank": bank.id,
            "qtype": "multichoice",
            "name": "Q",
            "text": "Pick",
            "data": {"choices": [{"text": "x"}]},
        },
        format="json",
    )
    assert bad.status_code == 400 and "data" in bad.json()
    made = teacher.post(
        "/api/v1/questions/",
        {
            "bank": bank.id,
            "category": category.id,
            "qtype": "truefalse",
            "name": "Clay",
            "text": "Clay holds water.",
            "data": {"correct": True},
            "tags": ["Soil", "soil ", "Water"],
        },
        format="json",
    )
    assert made.status_code == 201, made.content
    question_id = made.json()["id"]
    assert made.json()["tags"] == ["soil", "water"] and made.json()["latest"]["number"] == 1
    url = f"/api/v1/questions/{question_id}/"
    # Not used yet: edits change version 1 in place.
    edited = teacher.patch(url, {"text": "Clay soils hold water."}, format="json")
    assert edited.json()["new_version"] is False and edited.json()["versions_count"] == 1
    assert teacher.patch(url, {"qtype": "essay"}, format="json").status_code == 400

    quiz = make_quiz([Question.objects.get(pk=question_id)])
    learner = client_for(student.user)
    attempt = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()
    # Used by an attempt: an edit makes version 2, and the attempt keeps version 1.
    changed = teacher.patch(
        url, {"text": "Sandy soils hold water.", "data": {"correct": False}}, format="json"
    )
    assert changed.json()["new_version"] is True and changed.json()["versions_count"] == 2
    assert learner.get(f"/api/v1/quiz-attempts/{attempt['id']}/").json()["questions"][0]["text"] == (
        "<p>Clay soils hold water.</p>"
    )
    assert put(learner, attempt["id"], 1, {"answer": True}).status_code == 200
    finished = learner.post(f"/api/v1/quiz-attempts/{attempt['id']}/submit/").json()
    assert finished["score"] == "1.00"  # marked against version 1, where the statement was true
    versions = teacher.get(f"{url}versions/").json()
    assert [v["number"] for v in versions] == [1, 2] and versions[0]["in_use"] is True
    assert teacher.delete(url).status_code == 409
    assert AuditLog.objects.filter(entity="quizzes.question", action="update").count() == 2
    assert client_for(student.user).get("/api/v1/questions/").json()["count"] == 0


# --- quizzes and attempts ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_attempt_from_start_to_review(
    site, lecturer, student, other_student, client_for, make_question, make_quiz
):
    q1 = make_question()
    q2 = make_question(
        "shortanswer", {"answers": [{"text": "humus", "feedback": "Yes."}]}, "Dark organic matter?"
    )
    quiz = make_quiz(
        [q1, q2],
        closes_at=timezone.now() + timedelta(days=2),
        review_marks=Quiz.Review.IMMEDIATELY,
        review_feedback=Quiz.Review.IMMEDIATELY,
        review_correct=Quiz.Review.AFTER_CLOSE,
        pass_mark=50,
        feedback_bands=[
            {"min_percent": 50, "feedback": "Well done."},
            {"min_percent": 0, "feedback": "Revise."},
        ],
    )
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    assert teacher.post(f"/api/v1/quizzes/{quiz.id}/start/").status_code == 403
    started = learner.post(f"/api/v1/quizzes/{quiz.id}/start/")
    assert started.status_code == 201
    attempt = started.json()
    text = repr(attempt)
    assert "fraction" not in text and "Yes." not in text and "humus" not in text  # nothing gives answers away
    assert attempt["seconds_left"] is not None and attempt["state"] == "in_progress"
    # Reconnecting resumes the same attempt.
    again = learner.post(f"/api/v1/quizzes/{quiz.id}/start/")
    assert again.status_code == 200 and again.json()["id"] == attempt["id"]
    aid = attempt["id"]
    assert AttemptEvent.objects.filter(attempt_id=aid, kind="resumed").exists()

    first = put(learner, aid, 1, {"choice": "a"}, client_saved_at=timezone.now().isoformat())
    assert first.status_code == 200 and first.json()["saved"] is True
    assert put(learner, aid, 1, {"choice": "a"}).json()["saved"] is True  # repeating is harmless
    stale = put(
        learner, aid, 1, {"choice": "b"}, client_saved_at=(timezone.now() - timedelta(hours=1)).isoformat()
    )
    assert stale.json() == {**stale.json(), "saved": False, "stale": True}
    assert put(learner, aid, 1, {"choice": "zz"}).json()["code"] == "invalid_answer"
    assert put(learner, aid, 9, {"choice": "a"}).status_code == 404
    assert put(teacher, aid, 1, {"choice": "b"}).status_code == 403
    assert client_for(other_student.user).get(f"/api/v1/quiz-attempts/{aid}/").status_code == 404
    put(learner, aid, 2, {"text": "Humus"})
    assert learner.get(f"/api/v1/quiz-attempts/{aid}/").json()["questions"][0]["response"] == {"choice": "a"}

    done = learner.post(f"/api/v1/quiz-attempts/{aid}/submit/").json()
    assert done["state"] == "finished" and done["score"] == "2.00" and done["percent"] == "100.00"
    assert done["passed"] is True and done["overall_feedback"] == "Well done."
    assert done["questions"][0]["feedback"] == "Yes." and "right_answer" not in done["questions"][0]
    assert put(learner, aid, 1, {"choice": "b"}).json()["code"] == "finished"
    # Right answers only after the quiz closes.
    Quiz.objects.filter(pk=quiz.pk).update(closes_at=timezone.now() - timedelta(minutes=1))
    review = learner.get(f"/api/v1/quiz-attempts/{aid}/").json()
    assert review["questions"][0]["right_answer"] == {"choice": "a"}
    # Teaching staff see everything, including the event log; students do not get the log.
    full = teacher.get(f"/api/v1/quiz-attempts/{aid}/").json()
    assert full["questions"][0]["data"]["choices"][0]["fraction"] == 1.0
    kinds = [e["kind"] for e in teacher.get(f"/api/v1/quiz-attempts/{aid}/events/").json()]
    assert kinds[0] == "started" and "answer_saved" in kinds and kinds[-2:] == ["submitted", "released"]
    assert learner.get(f"/api/v1/quiz-attempts/{aid}/events/").status_code == 403
    assert len(teacher.get(f"/api/v1/quizzes/{quiz.id}/attempts/").json()) == 1


@pytest.mark.django_db
def test_review_options_never_and_marks_hidden(site, student, client_for, make_question, make_quiz):
    quiz = make_quiz(
        [make_question()],
        review_marks=Quiz.Review.NEVER,
        review_feedback=Quiz.Review.NEVER,
        review_correct=Quiz.Review.NEVER,
    )
    learner = client_for(student.user)
    aid = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()["id"]
    put(learner, aid, 1, {"choice": "a"})
    done = learner.post(f"/api/v1/quiz-attempts/{aid}/submit/").json()
    assert done["score"] is None and done["percent"] is None and "awarded" not in done["questions"][0]
    assert "feedback" not in done["questions"][0] and "right_answer" not in done["questions"][0]
    listed = learner.get(f"/api/v1/quizzes/{quiz.id}/attempts/").json()[0]
    assert listed["score"] is None and listed["percent"] is None


@pytest.mark.django_db
def test_unpublished_quizzes_are_hidden_from_students(
    site, student, lecturer, client_for, make_question, make_quiz
):
    quiz = make_quiz([make_question()], is_published=False)
    learner = client_for(student.user)
    assert learner.get(f"/api/v1/quizzes/{quiz.id}/").status_code == 404
    assert learner.get("/api/v1/quizzes/").json()["count"] == 0
    assert client_for(lecturer.user).get("/api/v1/quizzes/").json()["count"] == 1


@pytest.mark.django_db
def test_publishing_needs_questions(site, lecturer, client_for, category, make_question):
    teacher = client_for(lecturer.user)
    draft = teacher.post(
        "/api/v1/quizzes/", {"site": site.id, "title": "Quiz", "is_published": True}, format="json"
    )
    assert draft.status_code == 400
    quiz_id = teacher.post("/api/v1/quizzes/", {"site": site.id, "title": "Quiz"}, format="json").json()["id"]
    assert (
        teacher.patch(f"/api/v1/quizzes/{quiz_id}/", {"is_published": True}, format="json").status_code == 400
    )
    make_question()
    slot = teacher.post(
        "/api/v1/quiz-slots/", {"quiz": quiz_id, "category": category.id, "random_count": 2}, format="json"
    )
    assert slot.status_code == 201
    refused = teacher.patch(f"/api/v1/quizzes/{quiz_id}/", {"is_published": True}, format="json")
    assert refused.status_code == 400 and "fewer than 2" in str(refused.json())
    make_question(name="second")
    assert (
        teacher.patch(f"/api/v1/quizzes/{quiz_id}/", {"is_published": True}, format="json").status_code == 200
    )


@pytest.mark.django_db
def test_random_questions_are_drawn_per_attempt_and_slots_lock(
    site, lecturer, student, client_for, category, make_question, make_quiz
):
    sub = QuestionCategory.objects.create(bank=category.bank, parent=category, name="Horizons")
    for n in range(3):
        make_question(name=f"q{n}", cat=sub if n else category)
    quiz = make_quiz([])
    QuizSlot.objects.create(quiz=quiz, category=category, random_count=3, mark=2)
    learner = client_for(student.user)
    attempt = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()
    assert len(attempt["questions"]) == 3 and attempt["max_score"] == "6.00"
    teacher = client_for(lecturer.user)
    slot = QuizSlot.objects.get(quiz=quiz)
    assert (
        teacher.patch(f"/api/v1/quiz-slots/{slot.id}/", {"random_count": 1}, format="json").status_code == 409
    )
    assert teacher.delete(f"/api/v1/quiz-slots/{slot.id}/").status_code == 409
    other_bank = QuestionBank.objects.create(name="Elsewhere", department_code="LIV")
    stranger_q = Question.objects.create(bank=other_bank, qtype="essay", name="x")
    empty_quiz = make_quiz([], is_published=False)
    refused = teacher.post(
        "/api/v1/quiz-slots/", {"quiz": empty_quiz.id, "question": stranger_q.id}, format="json"
    )
    assert refused.status_code == 201  # lecturers may use department banks
    site_bank = QuestionBank.objects.create(name="Other site", site=_other_site())
    foreign = Question.objects.create(bank=site_bank, qtype="essay", name="y")
    assert (
        teacher.post(
            "/api/v1/quiz-slots/", {"quiz": empty_quiz.id, "question": foreign.id}, format="json"
        ).status_code
        == 400
    )


def _other_site():
    from courses.models import CourseSite

    return CourseSite.objects.create(code="LIV110-2026-27-S1-MRP", title="Poultry", is_published=True)


# --- timing -----------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_time_limit_is_enforced_on_the_server(site, student, client_for, make_question, make_quiz):
    quiz = make_quiz([make_question()], time_limit_minutes=10)
    learner = client_for(student.user)
    aid = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()["id"]
    attempt = Attempt.objects.get(pk=aid)
    assert 599 <= (attempt.deadline - attempt.started_at).total_seconds() <= 601
    # Inside the grace period an answer is still accepted.
    Attempt.objects.filter(pk=aid).update(
        deadline=timezone.now() - timedelta(seconds=services.grace_seconds() - 10)
    )
    assert put(learner, aid, 1, {"choice": "a"}).status_code == 200
    # After it, the answer is refused and the attempt is submitted with what was saved.
    Attempt.objects.filter(pk=aid).update(
        deadline=timezone.now() - timedelta(seconds=services.grace_seconds() + 5)
    )
    late = put(learner, aid, 1, {"choice": "b"})
    assert late.status_code == 409 and late.json()["code"] == "time_up"
    attempt.refresh_from_db()
    assert attempt.state == "finished" and attempt.auto_submitted and attempt.score == 1
    assert AttemptEvent.objects.filter(attempt=attempt, kind="answer_refused").exists()


@pytest.mark.django_db
def test_an_expired_attempt_is_submitted_when_fetched(site, student, client_for, make_question, make_quiz):
    quiz = make_quiz([make_question()], time_limit_minutes=5, attempts_allowed=2)
    learner = client_for(student.user)
    aid = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()["id"]
    Attempt.objects.filter(pk=aid).update(deadline=timezone.now() - timedelta(minutes=5))
    fetched = learner.get(f"/api/v1/quiz-attempts/{aid}/").json()
    assert fetched["state"] == "finished" and fetched["auto_submitted"] is True
    # Starting again after expiry gives a new attempt, not the expired one.
    second = learner.post(f"/api/v1/quizzes/{quiz.id}/start/")
    assert second.status_code == 201 and second.json()["number"] == 2


@pytest.mark.django_db
def test_window_attempt_limits_and_overrides(site, lecturer, student, client_for, make_question, make_quiz):
    quiz = make_quiz([make_question()], attempts_allowed=1, time_limit_minutes=20)
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    Quiz.objects.filter(pk=quiz.pk).update(opens_at=timezone.now() + timedelta(hours=1))
    assert learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()["code"] == "not_open"
    Quiz.objects.filter(pk=quiz.pk).update(opens_at=None, closes_at=timezone.now() - timedelta(minutes=1))
    assert learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()["code"] == "closed"

    override = {
        "quiz": quiz.id,
        "student": student.id,
        "extra_minutes": 15,
        "extra_attempts": 1,
        "closes_at": (timezone.now() + timedelta(days=1)).isoformat(),
        "reason": "Medical note",
    }
    assert learner.post("/api/v1/quiz-overrides/", override, format="json").status_code == 403
    made = teacher.post("/api/v1/quiz-overrides/", override, format="json")
    assert made.status_code == 201
    assert AuditLog.objects.filter(entity="quizzes.quizoverride", action="create").exists()
    assert learner.get("/api/v1/quiz-overrides/").json()["count"] == 0

    first = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()
    attempt = Attempt.objects.get(pk=first["id"])
    assert 2099 <= (attempt.deadline - attempt.started_at).total_seconds() <= 2101  # 20 + 15 minutes
    learner.post(f"/api/v1/quiz-attempts/{attempt.id}/submit/")
    assert learner.post(f"/api/v1/quizzes/{quiz.id}/start/").status_code == 201  # the extra attempt
    learner.post(f"/api/v1/quiz-attempts/{Attempt.objects.latest('id').id}/submit/")
    assert learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()["code"] == "no_attempts_left"
    status = learner.get(f"/api/v1/quizzes/{quiz.id}/").json()["my_status"]
    assert status["attempts_used"] == 2 and status["attempts_allowed"] == 2


@pytest.mark.django_db
def test_practice_quizzes_never_count_and_have_no_limit(site, lecturer, student, client_for, make_question):
    teacher = client_for(lecturer.user)
    made = teacher.post(
        "/api/v1/quizzes/",
        {"site": site.id, "title": "Revision", "is_practice": True, "weight": "3", "attempts_allowed": 1},
        format="json",
    ).json()
    assert made["weight"] == "0.00" and made["attempts_allowed"] == 0
    QuizSlot.objects.create(quiz_id=made["id"], question=make_question())
    teacher.patch(f"/api/v1/quizzes/{made['id']}/", {"is_published": True}, format="json")
    learner = client_for(student.user)
    for _ in range(3):
        aid = learner.post(f"/api/v1/quizzes/{made['id']}/start/").json()["id"]
        assert learner.post(f"/api/v1/quiz-attempts/{aid}/submit/").status_code == 200


@pytest.mark.django_db
def test_sequential_navigation_one_question_per_page(site, student, client_for, make_question, make_quiz):
    quiz = make_quiz(
        [make_question(name="one"), make_question(name="two")],
        questions_per_page=1,
        navigation=Quiz.Navigation.SEQUENTIAL,
    )
    learner = client_for(student.user)
    attempt = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()
    aid = attempt["id"]
    assert [q["position"] for q in attempt["questions"]] == [1] and attempt["last_page"] == 2
    assert put(learner, aid, 2, {"choice": "a"}).json()["code"] == "no_going_back"
    assert put(learner, aid, 1, {"choice": "a"}).status_code == 200
    moved = learner.post(f"/api/v1/quiz-attempts/{aid}/next-page/").json()
    assert [q["position"] for q in moved["questions"]] == [2]
    assert put(learner, aid, 1, {"choice": "b"}).json()["code"] == "no_going_back"
    assert learner.post(f"/api/v1/quiz-attempts/{aid}/next-page/").json()["code"] == "last_page"


# --- manual marking and release ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_essays_go_to_the_marking_queue_and_release_notifies(
    site, lecturer, student, client_for, make_question, make_quiz
):
    essay = make_question("essay", {"min_words": 0}, "Explain crop rotation.", mark=4)
    quiz = make_quiz([make_question(), essay], auto_release=False)
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    aid = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()["id"]
    put(learner, aid, 1, {"choice": "a"})
    put(learner, aid, 2, {"text": "Rotation breaks pest and disease cycles."})
    done = learner.post(f"/api/v1/quiz-attempts/{aid}/submit/").json()
    assert done["score"] is None and done["needs_grading"] is True

    queue = teacher.get(f"/api/v1/quizzes/{quiz.id}/marking-queue/").json()
    assert [(q["attempt"], q["position"]) for q in queue] == [(aid, 2)]
    assert learner.get(f"/api/v1/quizzes/{quiz.id}/marking-queue/").status_code == 403
    mark_url = f"/api/v1/quiz-attempts/{aid}/answers/2/mark/"
    assert learner.post(mark_url, {"mark": "4"}, format="json").status_code == 403
    assert teacher.post(mark_url, {"mark": "5"}, format="json").json()["code"] == "out_of_range"
    assert teacher.post(f"/api/v1/quiz-attempts/{aid}/release/").json()["code"] == "not_marked"
    marked = teacher.post(mark_url, {"mark": "3", "comment": "Good, add an example."}, format="json").json()
    assert marked["score"] == "4.00" and marked["needs_grading"] is False and marked["is_released"] is False
    assert AuditLog.objects.filter(entity="quizzes.attemptanswer", action="quiz_mark").exists()
    assert teacher.get(f"/api/v1/quizzes/{quiz.id}/marking-queue/").json() == []
    hidden = learner.get(f"/api/v1/quiz-attempts/{aid}/").json()
    assert hidden["score"] is None and "comment" not in hidden["questions"][1]

    released = teacher.post(f"/api/v1/quizzes/{quiz.id}/release/").json()
    assert released == {"released": 1, "awaiting_marking": 0}
    note = Notification.objects.get(recipient=student.user)
    assert note.title == "Result ready: Soils quiz"
    assert AuditLog.objects.filter(action="quiz_release").exists()
    shown = learner.get(f"/api/v1/quiz-attempts/{aid}/").json()
    assert shown["score"] == "4.00" and shown["questions"][1]["comment"] == "Good, add an example."
    # A later change of mark is audited too, and the attempt total follows.
    teacher.post(mark_url, {"mark": "4"}, format="json")
    assert learner.get(f"/api/v1/quiz-attempts/{aid}/").json()["score"] == "5.00"
    assert AuditLog.objects.filter(action="quiz_mark").count() == 2


@pytest.mark.django_db
def test_auto_release_after_manual_marking_notifies_the_student(
    site, lecturer, student, client_for, make_question, make_quiz
):
    quiz = make_quiz([make_question("essay", {}, "Explain.")])
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    aid = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()["id"]
    put(learner, aid, 1, {"text": "An answer."})
    learner.post(f"/api/v1/quiz-attempts/{aid}/submit/")
    assert not Notification.objects.filter(recipient=student.user).exists()
    teacher.post(f"/api/v1/quiz-attempts/{aid}/answers/1/mark/", {"mark": "1"}, format="json")
    assert Notification.objects.filter(recipient=student.user, title__startswith="Result ready").count() == 1


@pytest.mark.django_db
def test_file_response_upload_is_checked(site, lecturer, student, client_for, make_question, make_quiz):
    quiz = make_quiz(
        [make_question("file", {"allowed_extensions": ["pdf"], "max_size_mb": 1}, "Upload your report.")]
    )
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    aid = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()["id"]
    url = f"/api/v1/quiz-attempts/{aid}/answers/1/file/"
    wrong_type = learner.post(
        url, {"file": SimpleUploadedFile("report.docx", b"PK\x03\x04")}, format="multipart"
    )
    assert wrong_type.status_code == 400
    disguised = learner.post(url, {"file": SimpleUploadedFile("report.pdf", b"<html>")}, format="multipart")
    assert disguised.status_code == 400 and "do not match" in disguised.json()["detail"]
    ok = learner.post(url, {"file": SimpleUploadedFile("Ravi report.pdf", PDF)}, format="multipart")
    assert ok.status_code == 200, ok.content
    assert put(learner, aid, 1, {"filename": "x.pdf"}).status_code == 400  # files only through the upload
    learner.post(f"/api/v1/quiz-attempts/{aid}/submit/")
    download = teacher.get(url)
    assert download.status_code == 200 and "Ravi report.pdf" in download["Content-Disposition"]
    assert teacher.get(f"/api/v1/quizzes/{quiz.id}/marking-queue/").json()[0]["qtype"] == "file"


@pytest.mark.django_db
def test_diagram_image_is_served_to_staff_and_students_in_an_attempt(
    site, lecturer, student, other_student, client_for, make_question, make_quiz
):
    from quizzes.tests.test_marking import DIAGRAM

    question = make_question("image_label", DIAGRAM, "Label the plant.")
    teacher = client_for(lecturer.user)
    assert (
        teacher.post(
            f"/api/v1/questions/{question.id}/image/",
            {"image": SimpleUploadedFile("plant.svg", b"<svg/>")},
            format="multipart",
        ).status_code
        == 400
    )
    uploaded = teacher.post(
        f"/api/v1/questions/{question.id}/image/",
        {"image": SimpleUploadedFile("plant.png", PNG)},
        format="multipart",
    )
    assert uploaded.status_code == 200
    version_id = uploaded.json()["latest"]["id"]
    image_url = f"/api/v1/question-versions/{version_id}/image/"
    assert client_for(student.user).get(image_url).status_code == 403
    quiz = make_quiz([question])
    learner = client_for(student.user)
    attempt = learner.post(f"/api/v1/quizzes/{quiz.id}/start/").json()
    shown = attempt["questions"][0]
    assert shown["image_url"] == image_url and all("label" not in z for z in shown["data"]["zones"])
    assert learner.get(image_url).status_code == 200
    assert client_for(other_student.user).get(image_url).status_code == 403
    put(learner, attempt["id"], 1, {"zones": {"z1": "root", "z2": "leaf", "z3": "root"}})
    done = learner.post(f"/api/v1/quiz-attempts/{attempt['id']}/submit/").json()
    assert done["percent"] == "66.67"


# --- statistics, import and export ------------------------------------------------------------------------


@pytest.mark.django_db
def test_statistics_for_teaching_staff_only(
    site, lecturer, student, other_student, client_for, make_question, make_quiz
):
    quiz = make_quiz([make_question(name="easy"), make_question(name="hard")])
    for person, answers in ((student, ("a", "a")), (other_student, ("a", "b"))):
        client = client_for(person.user)
        aid = client.post(f"/api/v1/quizzes/{quiz.id}/start/").json()["id"]
        for position, choice in enumerate(answers, 1):
            put(client, aid, position, {"choice": choice})
        client.post(f"/api/v1/quiz-attempts/{aid}/submit/")
    assert client_for(student.user).get(f"/api/v1/quizzes/{quiz.id}/statistics/").status_code == 403
    stats = client_for(lecturer.user).get(f"/api/v1/quizzes/{quiz.id}/statistics/").json()
    assert stats["attempts"] == 2 and stats["mean_percent"] == 75.0
    by_name = {q["name"]: q for q in stats["questions"]}
    assert by_name["easy"]["facility_index"] == 100.0 and by_name["hard"]["facility_index"] == 50.0
    assert {r["response"]: r["count"] for r in by_name["hard"]["responses"]} == {"a": 1, "b": 1}
    assert by_name["easy"]["discrimination_index"] is None  # everyone right: it separates no one


@pytest.mark.django_db
def test_import_and_export_through_the_api(site, bank, category, lecturer, student, client_for):
    teacher = client_for(lecturer.user)
    gift = "::A::Clay holds water {T}\n\n::B::Pick {=Nitrogen ~Sand}\n\n::C::Bad {=a -> }\n"
    report = teacher.post(
        "/api/v1/questions/import/",
        {"bank": bank.id, "category": category.id, "format": "gift", "content": gift},
        format="json",
    )
    assert report.status_code == 200, report.content
    body = report.json()
    assert [q["name"] for q in body["imported"]] == ["A", "B"] and body["skipped"][0]["name"] == "C"
    assert AuditLog.objects.filter(action="quiz_import").exists()
    upload = SimpleUploadedFile("q.xml", b'<!DOCTYPE quiz [<!ENTITY a "x">]><quiz/>')
    unsafe = teacher.post(
        "/api/v1/questions/import/",
        {"bank": bank.id, "format": "moodle_xml", "file": upload},
        format="multipart",
    )
    assert unsafe.status_code == 400 and unsafe.json()["code"] == "unreadable"
    assert (
        client_for(student.user)
        .post(
            "/api/v1/questions/import/", {"bank": bank.id, "format": "gift", "content": gift}, format="json"
        )
        .status_code
        == 403
    )
    exported = teacher.get(f"/api/v1/questions/export/?bank={bank.id}&file_format=gift").json()
    assert exported["exported"] == 2 and "$CATEGORY: $course$/top/Soils" in exported["content"]
    xml = teacher.get(f"/api/v1/questions/export/?bank={bank.id}").json()
    assert xml["content"].startswith("<?xml") and 'type="truefalse"' in xml["content"]
    assert client_for(student.user).get(f"/api/v1/questions/export/?bank={bank.id}").status_code == 404
