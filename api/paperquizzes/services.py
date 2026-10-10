"""Making a paper from a quiz, and keying answer sheets in as attempts (item 3.24).

Answers are keyed as the student wrote them: letters for options, T or F, the words or number written, and
for a written answer marked by hand the marks given. Each keyed sheet becomes an attempt at the quiz, marked
by quizzes.services.mark_answers, the same rules as online, so it counts in the gradebook the same way.
"""

import csv
import io
import re
import secrets
import string
from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from audit.services import record
from courses.access import person_of
from courses.models import Membership
from paperquizzes.models import PaperQuiz, PaperScript, PaperVersion
from quizzes import schemas
from quizzes.models import Attempt, AttemptAnswer, AttemptEvent, Question
from quizzes.services import FOUR_PLACES, _pool, mark_answers, regrade

LETTERS = string.ascii_uppercase
# Question types that can be answered on paper and keyed back: by letters, words or numbers...
KEYED = frozenset(
    {
        schemas.MULTICHOICE,
        schemas.TRUEFALSE,
        schemas.MATCHING,
        schemas.ORDERING,
        schemas.SHORTANSWER,
        schemas.NUMERICAL,
    }
)
# ...and those a person marks, keyed as the marks given.
BY_HAND = frozenset({schemas.ESSAY})
LABELS = ("A", "B")
MAX_CSV_BYTES = 1024 * 1024


class Refusal(Exception):
    def __init__(self, code: str, detail: str, status: int = 409):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


class CellError(ValueError):
    """What is wrong with one keyed answer, said in words."""


# ---------------------------------------------------------------------------------------------------------
# Making a paper


def _drawn(quiz) -> list[tuple[Question, Decimal | None]]:
    rng = secrets.SystemRandom()
    slots = list(quiz.slots.select_related("question", "category"))
    used = {s.question_id for s in slots if s.question_id}
    chosen = []
    for slot in slots:
        if slot.question_id:
            chosen.append((slot.question, slot.mark))
            continue
        pool = list(_pool(slot, exclude=used))
        if len(pool) < slot.random_count:
            raise Refusal("not_enough_questions", f"Question {slot.position}: the category has run short.")
        for question in rng.sample(pool, slot.random_count):
            used.add(question.id)
            chosen.append((question, slot.mark))
    return chosen


def paper_problems(quiz) -> list[str]:
    """Why a quiz cannot be printed: no questions, or questions that cannot be answered on paper."""
    slots = list(quiz.slots.select_related("question", "category"))
    if not slots:
        return ["Add at least one question."]
    problems = []
    allowed = KEYED | BY_HAND
    for slot in slots:
        if slot.question_id and slot.question.qtype not in allowed:
            problems.append(
                f"Question {slot.position} ({slot.question.get_qtype_display()}) cannot be answered on paper."
            )
        if slot.category_id and _pool(slot, exclude=set()).exclude(qtype__in=allowed).exists():
            problems.append(
                f"Question {slot.position} draws from '{slot.category.name}', which holds questions that "
                "cannot be answered on paper."
            )
    return problems


def make_paper(quiz, *, title: str, sat_on, versions: int, request) -> PaperQuiz:
    problems = paper_problems(quiz)
    if problems:
        raise Refusal("not_printable", " ".join(problems), 400)
    chosen = _drawn(quiz)
    rng = secrets.SystemRandom()
    with transaction.atomic():
        paper = PaperQuiz.objects.create(
            quiz=quiz, title=title, sat_on=sat_on, created_by=request.user, updated_by=request.user
        )
        for index, label in enumerate(LABELS[:versions]):
            order = list(chosen)
            if index:  # version B: the questions and their options in another order
                rng.shuffle(order)
            items = []
            for question, mark in order:
                version = question.latest
                items.append(
                    {
                        "version": version.id,
                        "max_mark": str(mark or version.default_mark),
                        "layout": schemas.make_layout(
                            question.qtype, version.data, shuffle=bool(index), rng=rng
                        ),
                    }
                )
            PaperVersion.objects.create(paper=paper, label=label, items=items)
        record(
            request,
            "create",
            paper,
            after={"quiz": quiz.id, "title": title, "versions": versions, "questions": len(chosen)},
        )
    return paper


# ---------------------------------------------------------------------------------------------------------
# What each printed question looks like, for the PDF and the grid


def printed(version: PaperVersion) -> list[dict]:
    """Each question as printed: its type, the options with their letters, and how its answer is keyed."""
    from quizzes.models import QuestionVersion

    found = {
        v.id: v
        for v in QuestionVersion.objects.filter(id__in=[i["version"] for i in version.items]).select_related(
            "question"
        )
    }
    rows = []
    for number, item in enumerate(version.items, start=1):
        qv = found[item["version"]]
        qtype, data, layout = qv.question.qtype, qv.data, item["layout"]
        row = {
            "number": number,
            "qtype": qtype,
            "text": qv.text,
            "max_mark": item["max_mark"],
            "options": [],
            "prompts": [],
            "hint": "",
            "key": "",
        }
        if qtype == schemas.MULTICHOICE:
            by_id = {c["id"]: c for c in data["choices"]}
            order = layout.get("choices") or list(by_id)
            row["options"] = [{"letter": LETTERS[i], "text": by_id[c]["text"]} for i, c in enumerate(order)]
            right = [LETTERS[i] for i, c in enumerate(order) if by_id[c]["fraction"] > 0]
            best = max(order, key=lambda c: by_id[c]["fraction"])
            row["key"] = LETTERS[order.index(best)] if data["single"] else "".join(right)
            last = LETTERS[len(order) - 1]
            row["hint"] = (
                f"One letter, A to {last}" if data["single"] else f"Every letter that applies, A to {last}"
            )
        elif qtype == schemas.TRUEFALSE:
            row["hint"], row["key"] = "T or F", "T" if data["correct"] else "F"
        elif qtype == schemas.MATCHING:
            answers = layout.get("answers") or sorted({p["answer"] for p in data["pairs"]})
            row["options"] = [{"letter": LETTERS[i], "text": a} for i, a in enumerate(answers)]
            row["prompts"] = [p["prompt"] for p in data["pairs"]]
            row["key"] = "".join(LETTERS[answers.index(p["answer"])] for p in data["pairs"])
            row["hint"] = f"{len(data['pairs'])} letters, one for each numbered line"
        elif qtype == schemas.ORDERING:
            items = {i["id"]: i for i in data["items"]}
            shown = layout.get("items") or list(items)
            row["options"] = [{"letter": LETTERS[i], "text": items[x]["text"]} for i, x in enumerate(shown)]
            row["key"] = "".join(LETTERS[shown.index(i["id"])] for i in data["items"])
            row["hint"] = f"All {len(shown)} letters, first to last"
        elif qtype == schemas.SHORTANSWER:
            row["hint"] = "The words written"
            row["key"] = max(data["answers"], key=lambda a: a["fraction"])["text"]
        elif qtype == schemas.NUMERICAL:
            row["hint"] = "The number written"
            best = max(data["answers"], key=lambda a: a["fraction"])
            row["key"] = "" if best["value"] is None else f"{best['value']:g}"
        else:
            row["hint"] = f"Marks given, 0 to {item['max_mark']}, or ? to mark later"
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------------------------------------
# Keying answers in


def _letters(cell: str) -> list[str]:
    return [c for c in re.sub(r"[\s,;/]+", "", cell.upper())]


def _letter_index(letter: str, count: int, number: int) -> int:
    index = LETTERS.find(letter)
    if index < 0 or index >= count:
        raise CellError(f"Question {number}: '{letter}' is not one of A to {LETTERS[count - 1]}.")
    return index


def read_cell(qtype: str, data: dict, layout: dict, cell: str, number: int, max_mark: Decimal):
    """(response, hand_mark) for one keyed answer. A blank cell is no answer (None, None)."""
    cell = (cell or "").strip()
    if not cell:
        return None, None
    if qtype == schemas.MULTICHOICE:
        order = layout.get("choices") or [c["id"] for c in data["choices"]]
        letters = _letters(cell)
        indexes = sorted({_letter_index(letter, len(order), number) for letter in letters})
        if data["single"]:
            if len(indexes) != 1:
                raise CellError(f"Question {number}: give one letter.")
            return {"choice": order[indexes[0]]}, None
        return {"choices": sorted(order[i] for i in indexes)}, None
    if qtype == schemas.TRUEFALSE:
        word = cell.casefold()
        if word in {"t", "true"}:
            return {"answer": True}, None
        if word in {"f", "false"}:
            return {"answer": False}, None
        raise CellError(f"Question {number}: give T or F.")
    if qtype == schemas.MATCHING:
        answers = layout.get("answers") or sorted({p["answer"] for p in data["pairs"]})
        letters = _letters(cell)
        if len(letters) != len(data["pairs"]):
            raise CellError(f"Question {number}: give {len(data['pairs'])} letters, one for each line.")
        return {
            "matches": {
                p["id"]: answers[_letter_index(letter, len(answers), number)]
                for p, letter in zip(data["pairs"], letters, strict=True)
                if letter != "-"
            }
        }, None
    if qtype == schemas.ORDERING:
        shown = layout.get("items") or [i["id"] for i in data["items"]]
        letters = _letters(cell)
        indexes = [_letter_index(letter, len(shown), number) for letter in letters]
        if sorted(indexes) != list(range(len(shown))):
            raise CellError(f"Question {number}: give every letter once, first to last.")
        return {"order": [shown[i] for i in indexes]}, None
    if qtype == schemas.SHORTANSWER:
        return {"text": cell[:500]}, None
    if qtype == schemas.NUMERICAL:
        return {"value": cell[:60], "unit": ""}, None
    if cell == "?":  # answered, to be marked later in the quiz's marking queue
        return {"text": "Answered on paper."}, None
    try:
        given = Decimal(cell)
    except InvalidOperation as error:
        raise CellError(f"Question {number}: give the marks as a number.") from error
    if given < 0 or given > max_mark:
        raise CellError(f"Question {number}: the marks must be from 0 to {max_mark}.")
    return {"text": "Answered on paper."}, given


def _student(paper: PaperQuiz, student_no: str):
    membership = (
        Membership.objects.filter(
            site=paper.quiz.site,
            role=Membership.SiteRole.STUDENT,
            is_active=True,
            person__external_id__iexact=(student_no or "").strip(),
        )
        .select_related("person")
        .first()
    )
    if membership is None:
        raise CellError(f"'{student_no}' is not a student of this course.")
    return membership.person


def key_script(paper: PaperQuiz, *, student_no: str, label: str, cells: list[str], request) -> PaperScript:
    """Key one answer sheet in. Keying the same student again replaces what was keyed before."""
    from quizzes.models import QuestionVersion

    person = _student(paper, student_no)
    version = paper.versions.filter(label=(label or "").strip().upper()).first()
    if version is None:
        labels = " or ".join(paper.versions.values_list("label", flat=True))
        raise CellError(f"{student_no}: the version must be {labels}.")
    if len(cells) > len(version.items):
        raise CellError(f"{student_no}: there are only {len(version.items)} questions.")
    cells = [str(c or "").strip() for c in cells] + [""] * (len(version.items) - len(cells))
    versions = {v.id: v for v in QuestionVersion.objects.filter(id__in=[i["version"] for i in version.items])}
    rows = []
    for number, (item, cell) in enumerate(zip(version.items, cells, strict=True), start=1):
        qv = versions[item["version"]]
        qtype = qv.question.qtype
        response, hand = read_cell(qtype, qv.data, item["layout"], cell, number, Decimal(item["max_mark"]))
        try:
            response = schemas.validate_response(qtype, qv.data, response)
        except schemas.QuestionDataError as error:
            raise CellError(f"Question {number}: {error}") from error
        rows.append((number, item, qv, response, hand))
    quiz = paper.quiz
    sat = timezone.make_aware(datetime.combine(paper.sat_on, time(12, 0)))
    with transaction.atomic():
        script = PaperScript.objects.select_for_update().filter(paper=paper, student=person).first()
        before = {"version": script.version.label, "cells": script.cells} if script else None
        if script is None:
            numbers = Attempt.objects.filter(quiz=quiz, student=person).values_list("number", flat=True)
            attempt = Attempt.objects.create(
                quiz=quiz,
                student=person,
                number=max(numbers, default=0) + 1,
                state=Attempt.State.FINISHED,
                started_at=sat,
                submitted_at=sat,
                created_by=request.user,
                updated_by=request.user,
            )
        else:
            attempt = script.attempt
            attempt.answers.all().delete()
        AttemptAnswer.objects.bulk_create(
            [
                AttemptAnswer(
                    attempt=attempt,
                    position=number,
                    page=1,
                    version=qv,
                    max_mark=Decimal(item["max_mark"]),
                    layout=item["layout"],
                    response=response,
                    saved_at=sat,
                )
                for number, item, qv, response, _ in rows
            ]
        )
        mark_answers(attempt)
        marker, now = person_of(request.user), timezone.now()
        for number, item, _, _, hand in rows:
            if hand is None:
                continue
            answer = attempt.answers.get(position=number)
            answer.awarded = hand.quantize(FOUR_PLACES)
            answer.fraction = (hand / Decimal(item["max_mark"])).quantize(Decimal("0.0000001"))
            answer.comment, answer.marked_by, answer.marked_at = "Marked on paper.", marker, now
            answer.save()
        AttemptEvent.objects.create(
            attempt=attempt,
            kind=AttemptEvent.Kind.SUBMITTED,
            actor=request.user,
            detail={"paper": paper.id, "version": version.label, "keyed": True},
        )
        if script is None:
            script = PaperScript(paper=paper, student=person, attempt=attempt, created_by=request.user)
        script.version, script.cells, script.updated_by = version, cells, request.user
        script.save()
        record(
            request,
            "paper_keyed",
            script,
            before=before,
            after={"version": version.label, "cells": cells, "attempt": attempt.id},
        )
        attempt.refresh_from_db()
        regrade(attempt, request=request)
    return script


def key_rows(paper: PaperQuiz, rows: list[dict], *, request) -> dict:
    """Key many sheets: each row on its own, so one mistake never loses the rest."""
    saved, errors = 0, []
    for row in rows:
        student_no = str(row.get("student_no") or "").strip()
        cells = [str(c or "") for c in row.get("answers") or []]
        if not student_no and not any(c.strip() for c in cells):
            continue
        try:
            key_script(
                paper,
                student_no=student_no,
                label=str(row.get("version") or ""),
                cells=cells,
                request=request,
            )
            saved += 1
        except CellError as error:
            errors.append({"student_no": student_no, "detail": str(error)})
    return {"saved": saved, "errors": errors}


def rows_from_csv(content: bytes) -> list[dict]:
    """A spreadsheet saved as CSV: student_no, version, then one column for each question in printed order."""
    if len(content) > MAX_CSV_BYTES:
        raise Refusal("too_large", "The file is larger than 1 MB.", 400)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise Refusal("not_csv", "Save the spreadsheet as CSV (UTF-8) and send that.", 400) from error
    reader = csv.reader(io.StringIO(text))
    header = [h.strip().casefold() for h in next(reader, [])]
    if (
        len(header) < 3
        or header[0] not in {"student_no", "student number", "student"}
        or header[1] != "version"
    ):
        raise Refusal("bad_header", "The first row must be: student_no, version, q1, q2 ...", 400)
    return [
        {"student_no": r[0] if r else "", "version": r[1] if len(r) > 1 else "", "answers": r[2:]}
        for r in reader
    ]
