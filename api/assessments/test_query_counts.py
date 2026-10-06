"""The busiest endpoints read the database a fixed number of times, however large the class (item 7.08).

The load test (docs/performance.md) found the gradebook making some 16 queries for each student, about 1,400
for a class of ninety, and quizzes reading each question's latest version one at a time. These tests count
the queries with a small class and with a larger one (or few questions and more) and require the same
number, so a change that brings back a query per student or per question fails here.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from assessments.models import Extension, GradeCategory, Mark, Submission
from courses.models import Membership
from forums.models import Forum, ParticipationMark
from practicals.models import Observation, ObservationResult, PracticalCriterion, PracticalTask
from quizzes import schemas
from quizzes.models import Attempt, Question, QuestionBank, QuestionCategory, QuestionVersion, Quiz, QuizSlot

MC = {
    "single": True,
    "shuffle": True,
    "choices": [
        {"id": "a", "text": "Clay", "fraction": 1, "feedback": "Yes."},
        {"id": "b", "text": "Sand", "fraction": 0, "feedback": "No."},
    ],
}


def queries(client, method, path, body=None):
    with CaptureQueriesContext(connection) as captured:
        answer = getattr(client, method)(path, body, format="json")
    assert answer.status_code < 400, answer.content
    return len(captured.captured_queries), answer


@pytest.fixture
def quiz_of(site):
    def make(count):
        bank = QuestionBank.objects.create(site=site, name=f"Bank {count}")
        category = QuestionCategory.objects.create(bank=bank, name="Soil")
        quiz = Quiz.objects.create(
            site=site, title=f"Quiz {count}", closes_at=timezone.now() + timedelta(days=1), weight=1
        )
        for n in range(1, count + 1):
            question = Question.objects.create(
                bank=bank, category=category, qtype="multichoice", name=f"Q{n}"
            )
            data = schemas.validate_question("multichoice", "Which holds water?", MC)
            QuestionVersion.objects.create(question=question, text="Which holds water?", data=data)
            QuestionVersion.objects.create(
                question=question, number=2, text="Which holds most water?", data=data
            )
            QuizSlot.objects.create(quiz=quiz, position=n, question=question)
        Quiz.objects.filter(pk=quiz.pk).update(is_published=True)
        return Quiz.objects.get(pk=quiz.pk)

    return make


def _enrol_more(site, make_person, start, count):
    for n in range(start, start + count):
        person = make_person("student", f"26MRP{n:04d}", "Student", f"{n}", "student")
        Membership.objects.create(site=site, person=person, role="student")


def _coursework_for_everyone(site, assignment, quiz, lecturer):
    """Something in every part of the total for every student: a marked submission, an extension, a quiz
    attempt, a practical observation and a forum mark."""
    task = PracticalTask.objects.filter(site=site).first() or PracticalTask.objects.create(
        site=site, title="Prepare a bed", weight=1, is_published=True
    )
    criterion = PracticalCriterion.objects.get_or_create(
        task=task, position=1, defaults={"text": "Bed formed"}
    )[0]
    forum = Forum.objects.get_or_create(
        site=site, title="Field notes", defaults={"forum_type": "graded", "weight": 1, "is_published": True}
    )[0]
    GradeCategory.objects.get_or_create(site=site, name="Tests", defaults={"weight": 50})
    for membership in Membership.objects.filter(site=site, role="student").select_related("person"):
        person = membership.person
        submission = Submission.objects.get_or_create(
            assignment=assignment, student=person, defaults={"submitted_at": timezone.now(), "text": "Report"}
        )[0]
        Mark.objects.get_or_create(submission=submission, defaults={"mark": Decimal(30)})
        Extension.objects.get_or_create(
            assignment=assignment,
            student=person,
            defaults={"due_at": assignment.due_at + timedelta(days=2), "reason": "Illness"},
        )
        Attempt.objects.get_or_create(
            quiz=quiz,
            student=person,
            defaults={"started_at": timezone.now(), "state": "finished", "score": 1, "max_score": 2},
        )
        observation, made = Observation.objects.get_or_create(
            task=task,
            student=person,
            defaults={"attempt": 1, "assessor": lecturer, "observed_at": timezone.now()},
        )
        if made:
            ObservationResult.objects.create(observation=observation, criterion=criterion, passed=True)
        ParticipationMark.objects.get_or_create(forum=forum, student=person, defaults={"mark": 5})


@pytest.mark.django_db
def test_the_gradebook_reads_the_class_at_once(site, assignment, lecturer, make_person, client_for, quiz_of):
    teacher = client_for(lecturer.user)
    quiz = quiz_of(3)
    _coursework_for_everyone(site, assignment, quiz, lecturer)
    small, book = queries(teacher, "get", f"/api/v1/sites/{site.id}/gradebook/")
    few_attempts, _ = queries(teacher, "get", f"/api/v1/quizzes/{quiz.id}/attempts/")
    assert len(book.json()["rows"]) == 2
    _enrol_more(site, make_person, 10, 8)
    _coursework_for_everyone(site, assignment, quiz, lecturer)
    large, book = queries(teacher, "get", f"/api/v1/sites/{site.id}/gradebook/")
    many_attempts, listed = queries(teacher, "get", f"/api/v1/quizzes/{quiz.id}/attempts/")
    assert len(listed.json()) == 10 and many_attempts == few_attempts  # the attempts list, one query for all
    assert len(book.json()["rows"]) == 10
    assert large == small, f"{small} queries for 2 students, {large} for 10"
    assert large < 40
    row = book.json()["rows"][0]
    assert (
        row["marks"][str(assignment.id)]["mark"] == "30.00"
        and row["quizzes"][str(quiz.id)]["percent"] == "50.00"
    )
    # The spreadsheet of the gradebook too.
    small_csv, _ = queries(teacher, "get", f"/api/v1/sites/{site.id}/gradebook/export/")
    _enrol_more(site, make_person, 30, 3)
    _coursework_for_everyone(site, assignment, quiz, lecturer)
    large_csv, export = queries(teacher, "get", f"/api/v1/sites/{site.id}/gradebook/export/")
    assert large_csv == small_csv
    assert b"".join(export.streaming_content).count(b"\n") == 14  # the header and 13 students


@pytest.mark.django_db
def test_a_quiz_starts_lists_and_is_handed_in_in_the_same_number_of_queries_however_long(
    site, student, client_for, quiz_of
):
    learner = client_for(student.user)
    counts = {}
    for size in (2, 12):
        Quiz.objects.update(is_published=False)  # the list holds one quiz each time: only its length differs
        quiz = quiz_of(size)
        listed, _ = queries(learner, "get", f"/api/v1/quizzes/?site={site.id}")
        started, attempt = queries(learner, "post", f"/api/v1/quizzes/{quiz.id}/start/")
        aid = attempt.json()["id"]
        assert [q["text"] for q in attempt.json()["questions"]][
            0
        ] == "<p>Which holds most water?</p>"  # latest
        for position in range(1, size + 1):
            learner.put(
                f"/api/v1/quiz-attempts/{aid}/answers/{position}/",
                {"response": {"choice": "a"}},
                format="json",
            )
        handed_in, done = queries(learner, "post", f"/api/v1/quiz-attempts/{aid}/submit/")
        assert done.json()["score"] == f"{size}.00"
        counts[size] = (started, handed_in)
        counts[f"list{size}"] = listed
    assert counts[2] == counts[12], counts
    assert counts["list12"] == counts["list2"], counts  # ten more questions, no more queries
