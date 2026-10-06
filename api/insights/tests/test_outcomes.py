"""Item 3.11: learning outcomes from the SRMS course outline, linked to assignments, questions and rubric
criteria, and each student's standing on each."""

from decimal import Decimal

import pytest
from django.utils import timezone

from audit.models import AuditLog
from courses.models import CourseSite
from insights.models import Outcome, OutcomeLink, SiteProfile
from insights.tests.conftest import hand_in
from quizzes.models import Attempt, AttemptAnswer, Question, QuestionBank, QuestionVersion, Quiz
from rubrics.models import Rubric, RubricCriterion, RubricLevel

pytestmark = pytest.mark.django_db


@pytest.fixture
def outline(site):
    SiteProfile.objects.create(site=site, course_code="AGR101", programme_codes=["DIP-AG"])
    return [
        Outcome.objects.create(
            source="srms", course_code="AGR101", code="LO1", text="Sample a soil", position=1
        ),
        Outcome.objects.create(
            source="srms", course_code="AGR101", code="LO2", text="Plan a crop", position=2
        ),
    ]


def test_the_site_shows_its_courses_srms_outcomes_and_refuses_its_own(site, lecturer, outline, client_for):
    client = client_for(lecturer.user)
    data = client.get(f"/api/v1/sites/{site.id}/outcomes/").json()
    assert data["course_code"] == "AGR101" and data["from_srms"] is True and data["may_add"] is False
    assert [o["code"] for o in data["outcomes"]] == ["LO1", "LO2"]
    answer = client.post(f"/api/v1/sites/{site.id}/outcomes/", {"code": "X1", "text": "Mine"}, format="json")
    assert answer.status_code == 409 and answer.json()["code"] == "outcomes_from_srms"


def test_a_lecturer_adds_the_sites_own_outcomes_while_the_srms_has_none(site, lecturer, student, client_for):
    client = client_for(lecturer.user)
    answer = client.post(
        f"/api/v1/sites/{site.id}/outcomes/", {"code": "L1", "text": "Name soils"}, format="json"
    )
    assert answer.status_code == 201
    data = answer.json()
    assert data["from_srms"] is False and data["may_add"] is True
    outcome = Outcome.objects.get(site=site, code="L1")
    assert AuditLog.objects.filter(entity="insights.outcome", entity_id=outcome.id, action="create").exists()
    again = client.post(f"/api/v1/sites/{site.id}/outcomes/", {"code": "L1", "text": "Twice"}, format="json")
    assert again.status_code == 400
    changed = client.patch(f"/api/v1/outcomes/{outcome.id}/", {"text": "Name three soils"}, format="json")
    assert changed.status_code == 200 and changed.json()["text"] == "Name three soils"
    # Students do not write outcomes; nobody changes an SRMS outcome here.
    assert client_for(student.user).patch(f"/api/v1/outcomes/{outcome.id}/", {"text": "x"}).status_code == 403
    srms = Outcome.objects.create(source="srms", course_code="AGR101", code="LO1", text="From the SRMS")
    assert client.patch(f"/api/v1/outcomes/{srms.id}/", {"text": "x"}, format="json").status_code == 404
    assert client.delete(f"/api/v1/outcomes/{outcome.id}/").status_code == 204
    assert not Outcome.objects.filter(pk=outcome.pk).exists()


def test_a_second_local_outcome_cannot_take_a_code_already_used(site, lecturer, client_for):
    first = Outcome.objects.create(source="local", site=site, code="L1", text="One")
    Outcome.objects.create(source="local", site=site, code="L2", text="Two")
    answer = client_for(lecturer.user).patch(f"/api/v1/outcomes/{first.id}/", {"code": "L2"}, format="json")
    assert answer.status_code == 400


def _rubric(site):
    rubric = Rubric.objects.create(site=site, title="Report rubric", kind="scored")
    criterion = RubricCriterion.objects.create(rubric=rubric, title="Method", position=1)
    levels = [
        RubricLevel.objects.create(criterion=criterion, position=n, points=p, description=d)
        for n, (p, d) in enumerate([(0, "Absent"), (2, "Partial"), (4, "Complete")], 1)
    ]
    return rubric, criterion, levels


def _quiz_answer(site, student, question, awarded, *, released=True):
    quiz = Quiz.objects.get_or_create(site=site, title="Soils quiz", defaults={"is_published": True})[0]
    number = Attempt.objects.filter(quiz=quiz, student=student).count() + 1
    attempt = Attempt.objects.create(
        quiz=quiz,
        student=student,
        number=number,
        started_at=timezone.now(),
        submitted_at=timezone.now(),
        state="finished",
        score=awarded,
        max_score=2,
        is_released=released,
    )
    AttemptAnswer.objects.create(
        attempt=attempt,
        position=1,
        version=question.versions.first(),
        max_mark=2,
        awarded=Decimal(str(awarded)),
    )


def test_standing_per_outcome_from_assignments_questions_and_rubric_criteria(
    site, lecturer, student, other_student, outline, make_assignment, client_for
):
    lo1, lo2 = outline
    rubric, criterion, levels = _rubric(site)
    report = make_assignment("Soil report", days=-3, rubric=rubric)
    bank = QuestionBank.objects.create(name="AGR101 questions", site=site)
    question = Question.objects.create(bank=bank, qtype="shortanswer", name="pH")
    QuestionVersion.objects.create(question=question, text="What is pH?", data={})
    client = client_for(lecturer.user)
    for body, outcome in (
        ({"assignment": report.id}, lo1),
        ({"criterion": criterion.id}, lo1),
        ({"question": question.id}, lo2),
    ):
        answer = client.post(f"/api/v1/sites/{site.id}/outcomes/{outcome.id}/links/", body, format="json")
        assert answer.status_code == 201, answer.json()
    duplicate = client.post(
        f"/api/v1/sites/{site.id}/outcomes/{lo1.id}/links/", {"assignment": report.id}, format="json"
    )
    assert duplicate.status_code == 409
    submission = hand_in(report, student, mark=45, released=True)
    submission.mark.rubric_scores = [{"criterion": criterion.id, "level": levels[1].id, "points": "2.00"}]
    submission.mark.save()
    _quiz_answer(site, student, question, 0.5)
    _quiz_answer(site, student, question, 2)  # the latest answer is the one that counts

    data = client.get(f"/api/v1/sites/{site.id}/outcome-standings/").json()

    ravi = next(s for s in data["students"] if s["person_id"] == student.id)
    first, second = ravi["outcomes"][str(lo1.id)], ravi["outcomes"][str(lo2.id)]
    assert first["standing"] == "met" and first["percent"] == "70.0"  # (90% + 50%) / 2
    assert {e["kind"] for e in first["evidence"]} == {"assignment", "criterion"}
    assert second["standing"] == "met" and second["percent"] == "100.0"
    devi = next(s for s in data["students"] if s["person_id"] == other_student.id)
    assert devi["outcomes"][str(lo1.id)] == {"standing": "no_evidence", "percent": None, "evidence": []}
    assert [o["links"] for o in data["outcomes"]] == [2, 1]


def test_a_student_sees_standings_only_from_released_marks_and_anonymous_marks_stay_hidden(
    site, lecturer, student, outline, make_assignment, client_for
):
    lo1, _ = outline
    report = make_assignment("Soil report", days=-3)
    secret = make_assignment("Anonymous essay", days=-3, anonymous=True)
    for assignment in (report, secret):
        OutcomeLink.objects.create(site=site, outcome=lo1, assignment=assignment)
    hand_in(report, student, mark=10)  # 20%, not released
    hand_in(secret, student, mark=50)  # 100%, names hidden until release

    mine = client_for(student.user).get(f"/api/v1/sites/{site.id}/my-progress/").json()
    staff = client_for(lecturer.user).get(f"/api/v1/sites/{site.id}/outcome-standings/").json()

    assert mine["outcomes"]["students"][0]["outcomes"][str(lo1.id)]["standing"] == "no_evidence"
    ravi = next(s for s in staff["students"] if s["person_id"] == student.id)
    cell = ravi["outcomes"][str(lo1.id)]
    assert cell["standing"] == "not_yet" and cell["percent"] == "20.0"


def test_evidence_must_belong_to_the_site(site, lecturer, outline, client_for):
    lo1, _ = outline
    other = CourseSite.objects.create(code="AGR999", title="Another course")
    from assessments.models import Assignment

    elsewhere = Assignment.objects.create(
        site=other, title="Theirs", due_at=timezone.now(), is_published=True
    )
    their_rubric = Rubric.objects.create(site=other, title="Theirs", kind="guide")
    their_criterion = RubricCriterion.objects.create(rubric=their_rubric, title="X", max_points=5)
    bank = QuestionBank.objects.create(name="Their bank", site=other)
    their_question = Question.objects.create(bank=bank, qtype="shortanswer", name="Theirs")
    client = client_for(lecturer.user)
    url = f"/api/v1/sites/{site.id}/outcomes/{lo1.id}/links/"
    for body in (
        {"assignment": elsewhere.id},
        {"criterion": their_criterion.id},
        {"question": their_question.id},
        {},
        {"assignment": elsewhere.id, "criterion": their_criterion.id},
    ):
        assert client.post(url, body, format="json").status_code == 400, body
    local = Outcome.objects.create(source="local", site=other, code="Z", text="Not this site's")
    answer = client.post(f"/api/v1/sites/{site.id}/outcomes/{local.id}/links/", {}, format="json")
    assert answer.status_code == 404


def test_a_link_is_removed_by_the_sites_teaching_staff_only(
    site, lecturer, student, outline, make_assignment, client_for
):
    link = OutcomeLink.objects.create(site=site, outcome=outline[0], assignment=make_assignment("Report"))
    assert client_for(student.user).delete(f"/api/v1/outcome-links/{link.id}/").status_code == 403
    assert client_for(lecturer.user).delete(f"/api/v1/outcome-links/{link.id}/").status_code == 204
    assert AuditLog.objects.filter(entity="insights.outcomelink", action="delete").exists()


def test_a_marking_guide_criterion_counts_its_points_and_a_descriptive_one_gives_no_evidence(
    site, student, outline, make_assignment
):
    from insights.outcomes import standings

    guide = Rubric.objects.create(site=site, title="Guide", kind="guide")
    method = RubricCriterion.objects.create(rubric=guide, title="Method", max_points=10)
    words = Rubric.objects.create(site=site, title="Words", kind="descriptive")
    tone = RubricCriterion.objects.create(rubric=words, title="Tone")
    lo1, lo2 = outline
    OutcomeLink.objects.create(site=site, outcome=lo1, criterion=method)
    OutcomeLink.objects.create(site=site, outcome=lo2, criterion=tone)
    submission = hand_in(make_assignment("Guided", rubric=guide), student, mark=30)
    submission.mark.rubric_scores = [{"criterion": method.id, "level": None, "points": "3"}]
    submission.mark.save()

    cells = standings(site, [student])["students"][0]["outcomes"]

    assert cells[str(lo1.id)]["standing"] == "not_yet" and cells[str(lo1.id)]["percent"] == "30.0"
    assert cells[str(lo2.id)]["standing"] == "no_evidence"


def test_the_evidence_a_lecturer_may_link_is_the_sites_own(
    site, lecturer, student, make_assignment, client_for
):
    from quizzes.models import QuizSlot

    rubric, criterion, _ = _rubric(site)
    make_assignment("Soil report", rubric=rubric)
    bank = QuestionBank.objects.create(name="AGR101 questions", site=site)
    own = Question.objects.create(bank=bank, qtype="shortanswer", name="pH")
    shared = QuestionBank.objects.create(name="Department bank", department_code="CROPS")
    borrowed = Question.objects.create(bank=shared, qtype="shortanswer", name="Borrowed")
    Question.objects.create(bank=shared, qtype="shortanswer", name="Not used here")
    quiz = Quiz.objects.create(site=site, title="Soils quiz")
    QuizSlot.objects.create(quiz=quiz, position=1, question=borrowed)

    data = client_for(lecturer.user).get(f"/api/v1/sites/{site.id}/outcome-evidence/").json()

    assert [a["title"] for a in data["assignments"]] == ["Soil report"]
    assert {q["id"] for q in data["questions"]} == {own.id, borrowed.id}
    assert data["criteria"] == [{"id": criterion.id, "title": "Report rubric: Method"}]
    assert client_for(student.user).get(f"/api/v1/sites/{site.id}/outcome-evidence/").status_code == 403
