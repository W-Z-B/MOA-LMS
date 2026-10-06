"""Quizzes in the coursework total and the gradebook (feature 10 with feature 17)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from assessments.models import GradeCategory, Mark, Submission
from assessments.services import coursework_percent, coursework_working
from quizzes import services
from quizzes.models import Attempt, Quiz


def take(quiz, person, choice):
    """One finished attempt answering the single multiple-choice question."""
    attempt, _ = services.start_attempt(quiz, person, person.user)
    services.save_answer(attempt, 1, {"choice": choice})
    return services.submit_attempt(attempt)


@pytest.mark.django_db
def test_a_quiz_counts_like_an_assignment(site, assignment, student, other_student, make_question, make_quiz):
    quiz = make_quiz([make_question(), make_question(name="second")], weight=1, attempts_allowed=0)
    report = Submission.objects.create(
        assignment=assignment, student=student, text="x", submitted_at=timezone.now()
    )
    Mark.objects.create(submission=report, mark=40)  # 40/50 at weight 2
    attempt, _ = services.start_attempt(quiz, student, student.user)
    services.save_answer(attempt, 1, {"choice": "a"})
    services.save_answer(attempt, 2, {"choice": "b"})
    services.submit_attempt(attempt)  # 1 of 2 at weight 1
    # (2*0.8 + 1*0.5) / 3 = 70%
    assert coursework_percent(site, student) == Decimal("70.00")
    # The other student: the quiz is still open, the report not yet due: nothing counts.
    assert coursework_percent(site, other_student) is None
    Quiz.objects.filter(pk=quiz.pk).update(closes_at=timezone.now() - timedelta(minutes=1))
    assert coursework_percent(site, other_student) == Decimal("0.00")  # closed with no attempt


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "expected"),
    [("highest", "100.00"), ("first", "0.00"), ("last", "100.00"), ("average", "50.00")],
)
def test_grading_methods(site, student, make_question, make_quiz, method, expected):
    quiz = make_quiz([make_question()], grading_method=method, attempts_allowed=0)
    take(quiz, student, "b")
    take(quiz, student, "a")
    assert coursework_percent(site, student) == Decimal(expected)


@pytest.mark.django_db
def test_an_attempt_awaiting_marking_is_pending(site, student, lecturer, make_question, make_quiz, rf):
    quiz = make_quiz([make_question("essay", {}, "Explain.")], closes_at=timezone.now() + timedelta(days=1))
    attempt, _ = services.start_attempt(quiz, student, student.user)
    services.save_answer(attempt, 1, {"text": "An answer."})
    services.submit_attempt(attempt)
    Quiz.objects.filter(pk=quiz.pk).update(closes_at=timezone.now() - timedelta(minutes=1))
    assert coursework_percent(site, student) is None  # pending, not zero
    request = rf.post("/")
    request.user = lecturer.user
    answer = attempt.answers.get()
    services.manual_mark(answer, Decimal("0.5"), "", request=request)
    assert coursework_percent(site, student) == Decimal("50.00")


@pytest.mark.django_db
def test_the_students_own_total_waits_for_release(site, student, lecturer, make_question, make_quiz, rf):
    quiz = make_quiz([make_question()], auto_release=False)
    attempt = take(quiz, student, "a")
    assert coursework_percent(site, student) == Decimal("100.00")
    assert coursework_percent(site, student, released_only=True) is None
    request = rf.post("/")
    request.user = lecturer.user
    services.release_attempt(attempt, request=request)
    assert coursework_percent(site, student, released_only=True) == Decimal("100.00")


@pytest.mark.django_db
def test_practice_and_unpublished_quizzes_do_not_count(site, student, make_question, make_quiz):
    practice = make_quiz([make_question()], is_practice=True, weight=0, attempts_allowed=0)
    take(practice, student, "b")
    make_quiz([make_question(name="draft")], is_published=False, closes_at=timezone.now() - timedelta(days=1))
    assert coursework_percent(site, student) is None


@pytest.mark.django_db
def test_gradebook_has_quiz_columns_and_submits_timed_out_attempts(
    site, student, lecturer, client_for, make_question, make_quiz
):
    quiz = make_quiz([make_question()], time_limit_minutes=5)
    attempt, _ = services.start_attempt(quiz, student, student.user)
    services.save_answer(attempt, 1, {"choice": "a"})
    Attempt.objects.filter(pk=attempt.pk).update(deadline=timezone.now() - timedelta(minutes=10))
    book = client_for(lecturer.user).get(f"/api/v1/sites/{site.id}/gradebook/").json()
    assert book["quizzes"][0]["id"] == quiz.id and book["quizzes"][0]["counts"] is True
    row = next(r for r in book["rows"] if r["student_no"] == student.external_id)
    assert row["quizzes"][str(quiz.id)] == {"attempts": 1, "state": "graded", "percent": "100.00"}
    assert row["coursework_percent"] == "100.00"
    own = client_for(student.user).get(f"/api/v1/sites/{site.id}/gradebook/").json()
    assert len(own["rows"]) == 1 and own["rows"][0]["quizzes"][str(quiz.id)]["percent"] == "100.00"


@pytest.mark.django_db
def test_a_quiz_can_be_placed_in_a_gradebook_category(site, student, make_question, make_quiz):
    category = GradeCategory.objects.create(site=site, name="Quizzes", weight=1)
    quiz = make_quiz([make_question()], attempts_allowed=0)
    quiz.grade_category = category
    quiz.save()
    attempt, _ = services.start_attempt(quiz, student, student.user)
    services.save_answer(attempt, 1, {"choice": "a"})
    services.submit_attempt(attempt)
    working = coursework_working(site, student)
    item = next(i for i in working["items"] if i["kind"] == "quiz")
    assert item["category"] == category.id and working["categories"][0]["percent"] == "100.00"
