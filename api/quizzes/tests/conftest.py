"""Fixtures for quiz tests: a site bank with a category and a few questions, and a quiz built from them."""

import pytest

from quizzes import schemas
from quizzes.models import Question, QuestionBank, QuestionCategory, QuestionVersion, Quiz, QuizSlot

MC = {
    "single": True,
    "shuffle": True,
    "choices": [
        {"id": "a", "text": "Nitrogen", "fraction": 1, "feedback": "Yes."},
        {"id": "b", "text": "Sand", "fraction": 0, "feedback": "No."},
        {"id": "c", "text": "Glass", "fraction": 0, "feedback": "No."},
    ],
}


@pytest.fixture
def bank(site):
    return QuestionBank.objects.create(name="AGR101 questions", site=site)


@pytest.fixture
def category(bank):
    return QuestionCategory.objects.create(bank=bank, name="Soils")


@pytest.fixture
def make_question(bank, category):
    def _make(qtype="multichoice", data=None, text="Which is a plant nutrient?", name=None, cat=None, mark=1):
        data = schemas.validate_question(qtype, text, MC if data is None else data)
        question = Question.objects.create(
            bank=bank, category=cat or category, qtype=qtype, name=name or f"{qtype} question"
        )
        QuestionVersion.objects.create(question=question, text=text, data=data, default_mark=mark)
        return question

    return _make


@pytest.fixture
def make_quiz(site):
    def _make(questions, **options):
        options.setdefault("title", "Soils quiz")
        quiz = Quiz.objects.create(site=site, **options)
        for position, question in enumerate(questions, 1):
            QuizSlot.objects.create(quiz=quiz, position=position, question=question)
        if options.get("is_published") is None:
            Quiz.objects.filter(pk=quiz.pk).update(is_published=True)
            quiz.refresh_from_db()
        return quiz

    return _make
