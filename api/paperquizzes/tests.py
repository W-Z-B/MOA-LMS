"""Paper quizzes (item 3.24): drawn from the bank, printed in versions A and B, keyed back on a grid or from
CSV, marked by the same rules as online attempts and counted the same way."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from audit.models import AuditLog
from paperquizzes import pdf, services
from paperquizzes.models import PaperQuiz, PaperScript
from quizzes.models import Attempt
from quizzes.services import quiz_grade

TF = {"correct": True, "feedback_true": "", "feedback_false": ""}
MATCH = {
    "pairs": [
        {"id": "p1", "prompt": "Urea", "answer": "Nitrogen"},
        {"id": "p2", "prompt": "Bone meal", "answer": "Phosphorus"},
    ],
    "extra_answers": ["Iron"],
}
ORDER = {
    "items": [{"id": "i1", "text": "Plough"}, {"id": "i2", "text": "Harrow"}, {"id": "i3", "text": "Sow"}]
}
SHORT = {"answers": [{"text": "loam", "fraction": 1}], "case_sensitive": False}
NUMBER = {"answers": [{"value": 6.5, "tolerance": 0.1, "fraction": 1}], "units": [], "unit_mode": "none"}
ESSAY = {}


@pytest.fixture
def quiz(make_question, make_quiz):
    questions = [
        make_question(),  # multiple choice: a is right
        make_question("truefalse", TF, text="Lime raises soil pH."),
        make_question("matching", MATCH, text="Match each fertiliser to its nutrient."),
        make_question("ordering", ORDER, text="Put the field work in order."),
        make_question("shortanswer", SHORT, text="Name the best soil texture for vegetables."),
        make_question("numerical", NUMBER, text="Ideal pH for most crops?"),
        make_question("essay", ESSAY, text="Explain crop rotation.", mark=5),
    ]
    return make_quiz(questions, title="Soils test")


def _answers(paper, label: str, *, rotate_wrong=False) -> list[str]:
    """The full-mark answers for a version, read from its marking key."""
    rows = services.printed(paper.versions.get(label=label))
    keys = []
    for row in rows:
        if row["qtype"] == "essay":
            keys.append("4")  # four marks of five
        elif row["qtype"] == "truefalse" and rotate_wrong:
            keys.append("F")
        else:
            keys.append(row["key"])
    return keys


@pytest.mark.django_db
def test_a_paper_is_printed_keyed_and_counted_like_an_online_attempt(
    site, quiz, lecturer, student, other_student, client_for
):
    teacher = client_for(lecturer.user)
    made = teacher.post(
        f"/api/v1/quizzes/{quiz.id}/papers/",
        {"title": "Mid-term on paper", "sat_on": "2026-10-14"},
        format="json",
    )
    assert made.status_code == 201 and made.json()["versions"] == ["A", "B"] and made.json()["questions"] == 7
    paper = PaperQuiz.objects.get()
    detail = teacher.get(f"/api/v1/quiz-papers/{paper.id}/").json()
    a, b = (v["questions"] for v in detail["detail"])
    assert [q["qtype"] for q in a][:2] == ["multichoice", "truefalse"]  # A keeps the quiz's order
    assert sorted(q["qtype"] for q in a) == sorted(q["qtype"] for q in b)
    assert a[0]["options"][0] == {"letter": "A", "text": "Nitrogen"} and a[0]["key"] == "A"
    assert (
        len(a[2]["key"]) == 2 and sorted(a[3]["key"]) == ["A", "B", "C"] and "? to mark later" in a[6]["hint"]
    )

    # Each part of each version prints as a PDF; printing is audited.
    for part in ("questions", "answer-sheet", "key"):
        printed = teacher.get(f"/api/v1/quiz-papers/{paper.id}/pdf/?version=B&part={part}")
        assert printed.status_code == 200 and printed["Content-Type"] == "application/pdf"
        assert printed.content.startswith(b"%PDF")
    assert teacher.get(f"/api/v1/quiz-papers/{paper.id}/pdf/?version=C").status_code == 400
    assert AuditLog.objects.filter(action="paper_printed").count() == 3

    # Keyed on the grid: one student on version A with full marks but the essay at 4 of 5,
    # another on B with true-or-false wrong; a mistaken row is returned and the rest saved.
    keyed = teacher.post(
        f"/api/v1/quiz-papers/{paper.id}/grid/",
        {
            "rows": [
                {"student_no": student.external_id, "version": "a", "answers": _answers(paper, "A")},
                {
                    "student_no": other_student.external_id,
                    "version": "B",
                    "answers": _answers(paper, "B", rotate_wrong=True),
                },
                {"student_no": "99XXX0000", "version": "A", "answers": ["A"]},
                {"student_no": "", "version": "", "answers": ["", ""]},
            ]
        },
        format="json",
    ).json()
    assert keyed["saved"] == 2 and keyed["errors"] == [
        {"student_no": "99XXX0000", "detail": "'99XXX0000' is not a student of this course."}
    ]
    first = PaperScript.objects.get(student=student).attempt
    assert (
        first.state == Attempt.State.FINISHED and first.score == Decimal("10.0000") and first.max_score == 11
    )
    assert str(first.submitted_at.date()) == "2026-10-14" and first.is_released  # the quiz releases at once
    second = PaperScript.objects.get(student=other_student).attempt
    b_rows = services.printed(paper.versions.get(label="B"))
    tf_position = next(r["number"] for r in b_rows if r["qtype"] == "truefalse")
    assert second.answers.get(position=tf_position).awarded == 0
    # Counted the same way: the quiz grade comes from the attempt.
    assert quiz_grade(quiz, student).fraction == Decimal(10) / Decimal(11)

    # Keying again replaces the sheet; the grid shows the score.
    again = teacher.post(
        f"/api/v1/quiz-papers/{paper.id}/grid/",
        {
            "rows": [
                {
                    "student_no": student.external_id,
                    "version": "A",
                    "answers": _answers(paper, "A")[:-1] + ["?"],
                }
            ]
        },
        format="json",
    ).json()
    assert again == {"saved": 1, "errors": []}
    first.refresh_from_db()
    assert first.needs_grading and Attempt.objects.filter(student=student).count() == 1
    grid = teacher.get(f"/api/v1/quiz-papers/{paper.id}/grid/").json()
    row = next(r for r in grid["rows"] if r["student_no"] == student.external_id)
    assert row["version"] == "A" and row["needs_marking"] and len(grid["columns"]["B"]) == 7
    assert AuditLog.objects.filter(action="paper_keyed").count() == 3
    # A paper with sheets keyed stays.
    assert teacher.delete(f"/api/v1/quiz-papers/{paper.id}/").json()["code"] == "keyed"


@pytest.mark.django_db
def test_csv_upload_and_the_mistakes_it_reports(site, quiz, lecturer, student, client_for):
    teacher = client_for(lecturer.user)
    teacher.post(
        f"/api/v1/quizzes/{quiz.id}/papers/",
        {"title": "Test", "sat_on": "2026-10-14", "versions": 1},
        format="json",
    )
    paper = PaperQuiz.objects.get()
    keys = _answers(paper, "A")
    body = "student_no,version," + ",".join(f"q{i}" for i in range(1, 8)) + "\n"
    body += f"{student.external_id},A," + ",".join(keys) + "\n"
    body += f"{student.external_id},B," + ",".join(keys) + "\n"
    upload = SimpleUploadedFile("marks.csv", body.encode())
    result = teacher.post(
        f"/api/v1/quiz-papers/{paper.id}/upload/", {"file": upload}, format="multipart"
    ).json()
    assert result["saved"] == 1 and "version must be A" in result["errors"][0]["detail"]
    bad = SimpleUploadedFile("marks.csv", b"name,score\nx,1\n")
    assert (
        teacher.post(f"/api/v1/quiz-papers/{paper.id}/upload/", {"file": bad}, format="multipart").json()[
            "code"
        ]
        == "bad_header"
    )
    latin = SimpleUploadedFile("marks.csv", "student_no,version,q1\n\xe9,A,B\n".encode("latin-1"))
    assert (
        teacher.post(f"/api/v1/quiz-papers/{paper.id}/upload/", {"file": latin}, format="multipart").json()[
            "code"
        ]
        == "not_csv"
    )

    def mistake(index: int, value: str) -> str:
        cells = list(keys)
        cells[index] = value
        return services.key_rows(
            paper,
            [{"student_no": student.external_id, "version": "A", "answers": cells}],
            request=_req(lecturer),
        )["errors"][0]["detail"]

    assert mistake(0, "AB") == "Question 1: give one letter."
    assert mistake(0, "Z") == "Question 1: 'Z' is not one of A to C."
    assert mistake(1, "maybe") == "Question 2: give T or F."
    assert mistake(2, "A") == "Question 3: give 2 letters, one for each line."
    assert mistake(3, "AAB") == "Question 4: give every letter once, first to last."
    assert mistake(6, "9") == "Question 7: the marks must be from 0 to 5.00."
    assert mistake(6, "lots") == "Question 7: give the marks as a number."
    too_many = services.key_rows(
        paper,
        [{"student_no": student.external_id, "version": "A", "answers": keys + ["x"]}],
        request=_req(lecturer),
    )
    assert "only 7 questions" in too_many["errors"][0]["detail"]


def _req(person):
    from rest_framework.test import APIRequestFactory

    request = APIRequestFactory().post("/")
    request.user = person.user
    return request


@pytest.mark.django_db
def test_only_printable_quizzes_and_only_teaching_staff(
    site, make_question, make_quiz, lecturer, student, client_for
):
    cloze = make_question(
        "cloze",
        {"gaps": {"1": {"kind": "short", "answers": [{"text": "loam", "fraction": 1}]}}},
        text="Good soil is [[1]].",
    )
    quiz = make_quiz([cloze, make_question()])
    teacher = client_for(lecturer.user)
    refused = teacher.post(
        f"/api/v1/quizzes/{quiz.id}/papers/", {"title": "T", "sat_on": "2026-10-14"}, format="json"
    )
    assert refused.status_code == 400 and refused.json()["code"] == "not_printable"
    empty = make_quiz([], title="Empty")
    assert "Add at least one question." in services.paper_problems(empty)
    learner = client_for(student.user)
    assert learner.get(f"/api/v1/quizzes/{quiz.id}/papers/").status_code == 403
    plain = make_quiz([make_question()], title="Plain")
    made = teacher.post(
        f"/api/v1/quizzes/{plain.id}/papers/", {"title": "T", "sat_on": str(date(2026, 10, 1))}, format="json"
    )
    assert teacher.get(f"/api/v1/quizzes/{plain.id}/papers/").json()[0]["keyed"] == 0
    assert learner.get(f"/api/v1/quiz-papers/{made.json()['id']}/grid/").status_code == 403
    assert teacher.delete(f"/api/v1/quiz-papers/{made.json()['id']}/").status_code == 204
    assert pdf.plain('<p>Soil &amp; <img src="x"> water</p>') == ("Soil & water", True)
