"""Quiz rules: who may use a bank, question versions, attempts, server-side timing, marking and release.

Server time governs everything. A client's timestamp is stored for the record (and to drop an answer that
arrives after a newer one from the same device) but never decides whether an answer is in time.
"""

import math
import secrets
import statistics as stats
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from audit.services import record
from core import uploads
from courses.access import TEACHING, can_teach, person_of
from courses.models import Membership
from iam.models import Role, RoleScope
from iam.services import SITE_ADMIN_ROLES, has_role
from quizzes import marking, schemas
from quizzes.models import (
    Attempt,
    AttemptAnswer,
    AttemptEvent,
    Question,
    QuestionBank,
    QuestionCategory,
    QuestionVersion,
    Quiz,
    QuizOverride,
)

FOUR_PLACES = Decimal("0.0001")
TWO_PLACES = Decimal("0.01")


def grace_seconds() -> int:
    """Answers that reach the server this soon after the deadline are still accepted (slow connections)."""
    return int(getattr(settings, "QUIZ_GRACE_SECONDS", 30))


class Refusal(Exception):
    """A rule refuses the request. Rendered as {code, detail} with the given HTTP status."""

    def __init__(self, code: str, detail: str, status: int = 409):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


# ---------------------------------------------------------------------------------------------------------
# Banks


def _teaches_anywhere(user) -> bool:
    person = person_of(user)
    return (
        person is not None
        and Membership.objects.filter(
            person=person, is_active=True, role__in=[r for r in TEACHING if r != "admin"]
        ).exists()
    )


def can_manage_bank(user, bank: QuestionBank) -> bool:
    """Site banks: the site's teaching staff. Department banks: course administrators and lecturers whose
    lecturer role is scoped to that department's unit code."""
    if bank.site_id:
        return can_teach(user, bank.site)
    if has_role(user, *SITE_ADMIN_ROLES):
        return True
    return RoleScope.objects.filter(
        user=user, role__code=Role.LECTURER, unit_code=bank.department_code
    ).exists()


def can_use_bank(user, bank: QuestionBank) -> bool:
    """Read the bank and put its questions in quizzes. Department banks are shared with all teaching staff."""
    if bank.site_id:
        return can_teach(user, bank.site)
    return can_manage_bank(user, bank) or has_role(user, Role.LECTURER) or _teaches_anywhere(user)


def usable_banks(user):
    banks = QuestionBank.objects.select_related("site")
    if has_role(user, *SITE_ADMIN_ROLES):
        return banks
    person = person_of(user)
    teaching_sites = (
        Membership.objects.filter(person=person, is_active=True, role__in=["lecturer", "assistant"]).values(
            "site"
        )
        if person
        else Membership.objects.none().values("site")
    )
    shared = (
        Q(site__isnull=True) if (has_role(user, Role.LECTURER) or _teaches_anywhere(user)) else Q(pk__in=[])
    )
    scoped = RoleScope.objects.filter(user=user, role__code=Role.LECTURER).exclude(unit_code="")
    mine = Q(site__isnull=True, department_code__in=scoped.values("unit_code"))
    return banks.filter(Q(site__in=teaching_sites) | shared | mine)


# ---------------------------------------------------------------------------------------------------------
# Questions and versions


def version_in_use(version: QuestionVersion) -> bool:
    return AttemptAnswer.objects.filter(version=version).exists()


def save_question_version(question: Question, user, **content) -> tuple[QuestionVersion, bool]:
    """Change a question's wording or settings. A version an attempt has used is never changed: a new
    version is made instead and later attempts get it. Returns (version, new_version_made)."""
    current = question.latest
    if current is None or version_in_use(current):
        values = {
            "text": current.text if current else "",
            "data": current.data if current else {},
            "default_mark": current.default_mark if current else Decimal(1),
            "general_feedback": current.general_feedback if current else "",
            "image": current.image if current else "",
        }
        values.update(content)
        version = QuestionVersion.objects.create(
            question=question, number=(current.number + 1) if current else 1, created_by=user, **values
        )
        question._latest = version
        return version, current is not None
    for key, value in content.items():
        setattr(current, key, value)
    current.save()
    return current, False


def category_path_of(category) -> list[str]:
    path = []
    while category is not None:
        path.insert(0, category.name)
        category = category.parent
    return path


def _category_for(bank, base, path: list[str], cache: dict, user):
    parent = base
    for name in path:
        key = (parent.id if parent else None, name)
        if key not in cache:
            cache[key], _ = QuestionCategory.objects.get_or_create(
                bank=bank, parent=parent, name=name[:160], defaults={"created_by": user, "updated_by": user}
            )
        parent = cache[key]
    return parent


def import_questions(bank: QuestionBank, parsed, *, category=None, request) -> dict:
    """Save parsed questions into a bank. Each is validated like a hand-made one; failures are reported."""
    user = request.user
    imported, skipped, cache = [], list(parsed.skipped), {}
    with transaction.atomic():
        for item in parsed.questions:
            if not (item.text or "").strip():
                skipped.append({"name": item.name, "reason": "The question has no text."})
                continue
            try:
                data = schemas.validate_question(item.qtype, item.text, item.data)
            except schemas.QuestionDataError as error:
                skipped.append({"name": item.name, "reason": str(error)})
                continue
            target = _category_for(bank, category, item.category_path, cache, user)
            question = Question.objects.create(
                bank=bank,
                category=target,
                qtype=item.qtype,
                name=item.name or "Imported question",
                tags=[t[:40] for t in item.tags],
                created_by=user,
                updated_by=user,
            )
            QuestionVersion.objects.create(
                question=question,
                text=item.text,
                data=data,
                default_mark=Decimal(str(round(item.default_mark, 2))),
                general_feedback=item.general_feedback,
                created_by=user,
            )
            imported.append(
                {
                    "id": question.id,
                    "name": question.name,
                    "qtype": question.qtype,
                    "category": category_path_of(target),
                }
            )
        record(request, "quiz_import", bank, after={"imported": len(imported), "skipped": len(skipped)})
    return {"imported": imported, "skipped": skipped, "warnings": parsed.warnings}


def export_items(bank: QuestionBank, category=None):
    questions = Question.objects.filter(bank=bank, is_archived=False).select_related("category__parent")
    if category is not None:
        questions = questions.filter(category_id__in=category.descendant_ids())
    items = [(q, q.latest, category_path_of(q.category)) for q in questions]
    items.sort(key=lambda item: (item[2], item[0].name))
    return items


# ---------------------------------------------------------------------------------------------------------
# Per-student settings


@dataclass(frozen=True)
class Effective:
    closes_at: object
    time_limit_minutes: int | None
    attempts_allowed: int  # 0 means unlimited


def effective(quiz: Quiz, person) -> Effective:
    override = QuizOverride.objects.filter(quiz=quiz, student=person).first() if person else None
    closes_at = quiz.closes_at
    if override and override.closes_at:
        closes_at = override.closes_at
    limit = quiz.time_limit_minutes
    if limit and person:
        # A student's accommodation adds its percentage to every time limit (item 3.23), before any
        # extra minutes the teaching staff give for this quiz alone.
        from assessments.rules import extra_time_percent

        percent = extra_time_percent(person)
        if percent:
            limit = math.ceil(limit * (100 + percent) / 100)
    if limit and override:
        limit += override.extra_minutes
    allowed = 0 if quiz.is_practice else quiz.attempts_allowed
    if allowed and override:
        allowed += override.extra_attempts
    return Effective(closes_at, limit, allowed)


def is_closed(quiz: Quiz, person, now=None) -> bool:
    closes_at = effective(quiz, person).closes_at
    return closes_at is not None and (now or timezone.now()) >= closes_at


# ---------------------------------------------------------------------------------------------------------
# Quiz readiness and building an attempt


def quiz_problems(quiz: Quiz) -> list[str]:
    """Why a quiz cannot be published yet. Empty when it is ready."""
    problems = []
    slots = list(quiz.slots.select_related("question", "category"))
    if not slots:
        problems.append("Add at least one question.")
    if quiz.opens_at and quiz.closes_at and quiz.closes_at <= quiz.opens_at:
        problems.append("The quiz closes before it opens.")
    fixed = {s.question_id for s in slots if s.question_id}
    for slot in slots:
        if slot.category_id and _pool(slot, exclude=fixed).count() < slot.random_count:
            problems.append(
                f"Question {slot.position}: the category '{slot.category.name}' has fewer than "
                f"{slot.random_count} questions available."
            )
    return problems


def _pool(slot, exclude):
    ids = slot.category.descendant_ids() if slot.include_subcategories else [slot.category_id]
    pool = Question.objects.filter(category_id__in=ids, is_archived=False).exclude(id__in=exclude)
    return pool.filter(tags__contains=[slot.tag]) if slot.tag else pool


def quiz_max_mark(quiz: Quiz) -> Decimal:
    total = Decimal(0)
    for slot in quiz.slots.select_related("question"):
        if slot.question_id:
            total += slot.mark or slot.question.latest.default_mark
        else:
            total += (slot.mark or Decimal(1)) * slot.random_count
    return total


def _record_event(attempt, kind, user=None, **detail):
    AttemptEvent.objects.create(attempt=attempt, kind=kind, actor=user, detail=detail)


def start_attempt(quiz: Quiz, person, user, now=None) -> tuple[Attempt, bool]:
    """Start a new attempt, or return the one in progress (a reconnect resumes it). (attempt, resumed)."""
    now = now or timezone.now()
    if not quiz.is_published:
        raise Refusal("not_open", "This quiz is not open.", 403)
    if quiz.opens_at and now < quiz.opens_at:
        raise Refusal("not_open", "The quiz has not opened yet.")
    with transaction.atomic():
        # Lock the person's attempts so two tabs cannot start two attempts at once.
        attempts = list(
            Attempt.objects.select_for_update().filter(quiz=quiz, student=person).order_by("number")
        )
        current = next((a for a in attempts if a.state == Attempt.State.IN_PROGRESS), None)
        if current is not None:
            if not finish_if_expired(current, now=now, user=user):
                _record_event(current, AttemptEvent.Kind.RESUMED, user)
                return current, True
            # The attempt in progress had run out of time and is now submitted; the limits below apply.
        settings_for = effective(quiz, person)
        if settings_for.closes_at and now >= settings_for.closes_at:
            raise Refusal("closed", "The quiz has closed.")
        if settings_for.attempts_allowed and len(attempts) >= settings_for.attempts_allowed:
            raise Refusal("no_attempts_left", "You have used all your attempts at this quiz.")
        deadlines = []
        if settings_for.time_limit_minutes:
            deadlines.append(now + timedelta(minutes=settings_for.time_limit_minutes))
        if settings_for.closes_at:
            deadlines.append(settings_for.closes_at)
        attempt = Attempt.objects.create(
            quiz=quiz,
            student=person,
            number=(attempts[-1].number + 1) if attempts else 1,
            started_at=now,
            deadline=min(deadlines) if deadlines else None,
            created_by=user,
            updated_by=user,
        )
        _build_answers(attempt)
        _record_event(attempt, AttemptEvent.Kind.STARTED, user)
    return attempt, False


def _build_answers(attempt: Attempt) -> None:
    quiz, rng = attempt.quiz, secrets.SystemRandom()
    slots = list(quiz.slots.select_related("question", "category"))
    used = {s.question_id for s in slots if s.question_id}
    chosen: list[tuple[Question, Decimal | None]] = []
    for slot in slots:
        if slot.question_id:
            chosen.append((slot.question, slot.mark))
            continue
        pool = list(_pool(slot, exclude=used))
        if len(pool) < slot.random_count:
            raise Refusal(
                "not_enough_questions", "This quiz cannot start: a question category has run short."
            )
        for question in rng.sample(pool, slot.random_count):
            used.add(question.id)
            chosen.append((question, slot.mark))
    if quiz.shuffle_questions:
        rng.shuffle(chosen)
    per_page = quiz.questions_per_page
    rows = []
    for index, (question, mark) in enumerate(chosen):
        version = question.latest
        rows.append(
            AttemptAnswer(
                attempt=attempt,
                position=index + 1,
                page=(index // per_page) + 1 if per_page else 1,
                version=version,
                max_mark=mark or version.default_mark,
                layout=schemas.make_layout(
                    question.qtype, version.data, shuffle=quiz.shuffle_answers, rng=rng
                ),
            )
        )
    AttemptAnswer.objects.bulk_create(rows)
    attempt.max_score = sum((r.max_mark for r in rows), Decimal(0))
    attempt.save(update_fields=["max_score"])


def last_page(attempt: Attempt) -> int:
    return max((a.page for a in attempt.answers.all()), default=1)


# ---------------------------------------------------------------------------------------------------------
# Timing, answers and submission


def is_expired(attempt: Attempt, now=None) -> bool:
    now = now or timezone.now()
    return attempt.deadline is not None and now > attempt.deadline + timedelta(seconds=grace_seconds())


def finish_if_expired(attempt: Attempt, now=None, user=None) -> bool:
    """Submit an attempt whose time has run out. True when it was submitted now."""
    if attempt.state != Attempt.State.IN_PROGRESS or not is_expired(attempt, now):
        return False
    submit_attempt(attempt, user=user, auto=True, now=now)
    return True


def finish_expired_attempts(quizzes) -> int:
    """Submit every timed-out attempt of these quizzes (used before totals are worked out)."""
    now, count = timezone.now(), 0
    for attempt in Attempt.objects.filter(
        quiz__in=quizzes, state=Attempt.State.IN_PROGRESS, deadline__isnull=False
    ):
        count += finish_if_expired(attempt, now=now)
    return count


def save_answer(
    attempt: Attempt, position: int, response, *, client_saved_at=None, user=None, now=None
) -> dict:
    """Save one answer as it is given. Idempotent: sending the same answer again changes nothing.
    An answer older (by the device's clock) than the one already saved from that device is ignored."""
    now = now or timezone.now()
    # The attempt row is locked while the answer is written, so an answer can never land after a
    # submission that happens at the same moment: one waits for the other, then sees its result.
    with transaction.atomic():
        attempt = Attempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.state != Attempt.State.IN_PROGRESS:
            raise Refusal("finished", "This attempt has been submitted.")
        if not is_expired(attempt, now):
            return _save_locked_answer(attempt, position, response, client_saved_at, user, now)
    _record_event(attempt, AttemptEvent.Kind.ANSWER_REFUSED, user, position=position, reason="time_up")
    submit_attempt(attempt, user=user, auto=True, now=now)
    raise Refusal("time_up", "Time is up. Your saved answers have been submitted.")


def _save_locked_answer(attempt: Attempt, position: int, response, client_saved_at, user, now) -> dict:
    answer = attempt.answers.select_related("version__question").filter(position=position).first()
    if answer is None:
        raise Refusal("not_found", "There is no such question in this attempt.", 404)
    _check_page(attempt, answer, user)
    cleaned = schemas.validate_response(answer.qtype, answer.version.data, response)
    if client_saved_at and answer.client_saved_at and client_saved_at < answer.client_saved_at:
        return {"saved": False, "stale": True}
    if cleaned == answer.response:
        return {"saved": True, "stale": False, "unchanged": True}
    answer.response, answer.client_saved_at, answer.saved_at = cleaned, client_saved_at, now
    answer.save(update_fields=["response", "client_saved_at", "saved_at", "updated_at"])
    _record_event(attempt, AttemptEvent.Kind.ANSWER_SAVED, user, position=position)
    return {"saved": True, "stale": False, "unchanged": False}


def _check_page(attempt: Attempt, answer: AttemptAnswer, user) -> None:
    if attempt.quiz.navigation == Quiz.Navigation.SEQUENTIAL and answer.page != attempt.current_page:
        _record_event(
            attempt, AttemptEvent.Kind.ANSWER_REFUSED, user, position=answer.position, reason="page"
        )
        raise Refusal(
            "no_going_back", "This quiz does not let you go back to, or skip ahead to, that question."
        )


def save_file_answer(attempt: Attempt, position: int, upload, *, user=None, now=None) -> AttemptAnswer:
    now = now or timezone.now()
    if attempt.state != Attempt.State.IN_PROGRESS:
        raise Refusal("finished", "This attempt has been submitted.")
    if is_expired(attempt, now):
        submit_attempt(attempt, user=user, auto=True, now=now)
        raise Refusal("time_up", "Time is up. Your saved answers have been submitted.")
    answer = attempt.answers.select_related("version__question").filter(position=position).first()
    if answer is None or answer.qtype != schemas.FILE:
        raise Refusal("not_found", "There is no file question at that position.", 404)
    _check_page(attempt, answer, user)
    data = answer.version.data
    name = uploads.original_name(upload)
    try:
        uploads.validate_upload(upload, answer_policy(data))
    except ValidationError as error:
        raise Refusal("file_rejected", " ".join(str(m) for m in error.detail), 400) from error
    if answer.file:
        answer.file.delete(save=False)
    answer.file.save(name, upload, save=False)
    answer.response, answer.saved_at = {"filename": name}, now
    answer.save()
    _record_event(attempt, AttemptEvent.Kind.ANSWER_SAVED, user, position=position, filename=name)
    return answer


@dataclass(frozen=True)
class SizedPolicy(uploads.UploadPolicy):
    """An upload policy whose size limit is set per question rather than by a setting."""

    max_mb: int = 10

    @property
    def limit_mb(self) -> int:
        return self.max_mb


def answer_policy(data: dict) -> SizedPolicy:
    """The kinds a file-response question accepts (within what core.uploads can recognise) and its limit."""
    kinds = frozenset(
        kind
        for kind, extensions in uploads.EXTENSIONS.items()
        if any(ext.lstrip(".") in data["allowed_extensions"] for ext in extensions)
    )
    accepts = ", ".join(e.upper() for e in data["allowed_extensions"])
    return SizedPolicy(kinds, "", f"one of these file types: {accepts}", max_mb=data["max_size_mb"])


IMAGE_POLICY = SizedPolicy(frozenset({"png", "jpeg", "webp"}), "", "a PNG, JPG or WEBP image", max_mb=5)


def next_page(attempt: Attempt, user=None, now=None) -> Attempt:
    if attempt.state != Attempt.State.IN_PROGRESS:
        raise Refusal("finished", "This attempt has been submitted.")
    if finish_if_expired(attempt, now=now, user=user):
        raise Refusal("time_up", "Time is up. Your saved answers have been submitted.")
    if attempt.current_page >= last_page(attempt):
        raise Refusal("last_page", "This is the last page.")
    attempt.current_page += 1
    attempt.save(update_fields=["current_page", "updated_at"])
    _record_event(attempt, AttemptEvent.Kind.PAGE_CHANGED, user, page=attempt.current_page)
    return attempt


def submit_attempt(attempt: Attempt, *, user=None, auto=False, now=None) -> Attempt:
    """Finish the attempt and mark everything that can be marked automatically."""
    now = now or timezone.now()
    with transaction.atomic():
        attempt = Attempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.state != Attempt.State.IN_PROGRESS:
            return attempt
        for answer in attempt.answers.select_related("version__question"):
            result = marking.mark(answer.qtype, answer.version.data, answer.response)
            answer.needs_manual = result.needs_manual
            answer.auto_feedback = result.feedback
            if result.fraction is None:
                answer.fraction = answer.awarded = None
            else:
                answer.fraction = Decimal(str(result.fraction)).quantize(Decimal("0.0000001"))
                answer.awarded = (answer.fraction * answer.max_mark).quantize(
                    FOUR_PLACES, rounding=ROUND_HALF_UP
                )
            answer.save(update_fields=["needs_manual", "auto_feedback", "fraction", "awarded", "updated_at"])
        attempt.state = Attempt.State.FINISHED
        attempt.submitted_at = min(now, attempt.deadline) if (auto and attempt.deadline) else now
        attempt.auto_submitted = auto
        attempt.save(update_fields=["state", "submitted_at", "auto_submitted", "updated_at"])
        _record_event(
            attempt, AttemptEvent.Kind.AUTO_SUBMITTED if auto else AttemptEvent.Kind.SUBMITTED, user
        )
        regrade(attempt, notify_release=False)
    return attempt


def regrade(attempt: Attempt, *, notify_release=True, request=None) -> Attempt:
    """Work out the attempt's total from its answers; release it if the quiz releases automatically."""
    answers = list(attempt.answers.all())
    attempt.needs_grading = any(a.needs_manual and a.awarded is None for a in answers)
    attempt.score = sum((a.awarded or Decimal(0) for a in answers), Decimal(0))
    attempt.max_score = sum((a.max_mark for a in answers), Decimal(0))
    attempt.save(update_fields=["needs_grading", "score", "max_score", "updated_at"])
    if attempt.quiz.auto_release and not attempt.needs_grading and not attempt.is_released:
        release_attempt(attempt, request=request, notify_student=notify_release)
    return attempt


def manual_mark(answer: AttemptAnswer, mark: Decimal, comment: str, *, request) -> AttemptAnswer:
    """A person marks (or overrides the mark of) one answer. Audited."""
    if mark < 0 or mark > answer.max_mark:
        raise Refusal("out_of_range", f"The mark must be from 0 to {answer.max_mark}.", 400)
    with transaction.atomic():
        attempt = (
            Attempt.objects.select_for_update(of=("self",))
            .select_related("quiz__site", "student")
            .get(pk=answer.attempt_id)
        )
        if attempt.state != Attempt.State.FINISHED:
            raise Refusal("in_progress", "The attempt has not been submitted yet.")
        answer = AttemptAnswer.objects.get(pk=answer.pk)
        before = {"awarded": _s(answer.awarded), "comment": answer.comment}
        answer.awarded = mark.quantize(FOUR_PLACES)
        answer.fraction = (mark / answer.max_mark).quantize(Decimal("0.0000001"))
        answer.comment = comment
        answer.marked_by = person_of(request.user)
        answer.marked_at = timezone.now()
        answer.save()
        _record_event(
            attempt, AttemptEvent.Kind.MARKED, request.user, position=answer.position, mark=str(mark)
        )
        record(
            request,
            "quiz_mark",
            answer,
            before=before,
            after={"attempt": attempt.id, "position": answer.position, "awarded": _s(answer.awarded)},
        )
        regrade(attempt, request=request)
    return answer


def release_attempt(attempt: Attempt, *, request=None, notify_student=True) -> bool:
    """Let the student see the result (subject to the quiz's review options). False when not ready."""
    if attempt.state != Attempt.State.FINISHED or attempt.needs_grading:
        return False
    if attempt.is_released:
        return True
    attempt.is_released, attempt.released_at = True, timezone.now()
    attempt.save(update_fields=["is_released", "released_at", "updated_at"])
    actor = getattr(request, "user", None)
    _record_event(
        attempt, AttemptEvent.Kind.RELEASED, actor if getattr(actor, "is_authenticated", False) else None
    )
    if request is not None:
        record(request, "quiz_release", attempt, after={"quiz": attempt.quiz_id, "score": _s(attempt.score)})
    if notify_student and attempt.student.user_id:
        from notifications.services import notify

        quiz = attempt.quiz
        notify(
            [attempt.student.user],
            title=f"Result ready: {quiz.title}",
            body=f"{quiz.site.code}: your result for attempt {attempt.number} has been released.",
            link=f"/sites/{quiz.site_id}/quizzes/{quiz.id}",
            dedupe_key=f"quiz-attempt:{attempt.id}:released",
        )
    return True


def _s(value):
    return None if value is None else str(value)


# ---------------------------------------------------------------------------------------------------------
# What a student may see, and grades


def review_allows(option: str, attempt: Attempt, now=None) -> bool:
    """Review options as in Moodle. 'After close' never arrives for a quiz without a closing date."""
    if attempt.state != Attempt.State.FINISHED or option == Quiz.Review.NEVER:
        return False
    if option == Quiz.Review.IMMEDIATELY:
        return True
    return is_closed(attempt.quiz, attempt.student, now)


def student_sees_marks(attempt: Attempt, now=None) -> bool:
    return attempt.is_released and review_allows(attempt.quiz.review_marks, attempt, now)


def overall_feedback(quiz: Quiz, percent) -> str:
    if percent is None:
        return ""
    for band in sorted(quiz.feedback_bands or [], key=lambda b: -Decimal(str(b["min_percent"]))):
        if Decimal(percent) >= Decimal(str(band["min_percent"])):
            return band["feedback"]
    return ""


@dataclass(frozen=True)
class QuizGrade:
    state: str  # "graded", "pending" (marking or release outstanding, or an attempt in progress), "none"
    fraction: Decimal | None
    attempts: int


def quiz_grade(quiz: Quiz, person, *, released_only=False, now=None) -> QuizGrade:
    """The student's grade for the quiz by its grading method, as a fraction of the maximum."""
    attempts = list(Attempt.objects.filter(quiz=quiz, student=person).order_by("number"))
    finished = [a for a in attempts if a.state == Attempt.State.FINISHED]
    in_progress = len(finished) != len(attempts)
    if not finished:
        return QuizGrade("pending" if in_progress else "none", None, 0)
    method = quiz.grading_method
    considered = {Quiz.Grading.FIRST: finished[:1], Quiz.Grading.LAST: finished[-1:]}.get(method, finished)
    if method == Quiz.Grading.LAST and in_progress:
        return QuizGrade("pending", None, len(finished))

    def ready(a):
        return not a.needs_grading and a.max_score and (not released_only or student_sees_marks(a, now))

    if not all(ready(a) for a in considered):
        return QuizGrade("pending", None, len(finished))
    fractions = [a.score / a.max_score for a in considered]
    value = max(fractions) if method == Quiz.Grading.HIGHEST else sum(fractions) / len(fractions)
    return QuizGrade("graded", min(value, Decimal(1)), len(finished))


# ---------------------------------------------------------------------------------------------------------
# Statistics (item 3.06)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)


def quiz_statistics(quiz: Quiz) -> dict:
    """Facility index (how easy), discrimination index (how well the question separates strong and weak
    students: correlation with the rest of the quiz) and how often each option was chosen."""
    attempts = list(
        Attempt.objects.filter(quiz=quiz, state=Attempt.State.FINISHED, max_score__gt=0).prefetch_related(
            "answers__version__question"
        )
    )
    percents = [float(a.score / a.max_score * 100) for a in attempts if a.score is not None]
    per_question: dict[int, dict] = {}
    for attempt in attempts:
        for answer in attempt.answers.all():
            if answer.awarded is None:
                continue
            question = answer.version.question
            entry = per_question.setdefault(
                question.id,
                {
                    "question": question,
                    "fractions": [],
                    "rest": [],
                    "responses": Counter(),
                    "positions": set(),
                },
            )
            entry["positions"].add(answer.position)
            entry["fractions"].append(float(answer.awarded / answer.max_mark))
            rest_max = attempt.max_score - answer.max_mark
            entry["rest"].append(float((attempt.score - answer.awarded) / rest_max) if rest_max else 0.0)
            for key in _response_keys(question.qtype, answer.response):
                entry["responses"][key] += 1
    rows = []
    for entry in per_question.values():
        question, fractions = entry["question"], entry["fractions"]
        r = _pearson(fractions, entry["rest"])
        rows.append(
            {
                "question_id": question.id,
                "name": question.name,
                "qtype": question.qtype,
                "positions": sorted(entry["positions"]),
                "answered": len(fractions),
                "facility_index": round(sum(fractions) / len(fractions) * 100, 2),
                "discrimination_index": None if r is None else round(r * 100, 2),
                "responses": [{"response": k, "count": c} for k, c in entry["responses"].most_common(20)],
            }
        )
    rows.sort(key=lambda r: (min(r["positions"]), r["question_id"]))
    passed = (
        sum(1 for p in percents if p >= float(quiz.pass_mark))
        if quiz.pass_mark is not None and percents
        else None
    )
    return {
        "quiz": quiz.id,
        "attempts": len(attempts),
        "mean_percent": round(stats.fmean(percents), 2) if percents else None,
        "median_percent": round(stats.median(percents), 2) if percents else None,
        "pass_rate": round(passed / len(percents) * 100, 2) if passed is not None else None,
        "questions": rows,
    }


def _response_keys(qtype: str, response) -> list[str]:
    if not response:
        return ["(no answer)"]
    if qtype == schemas.MULTICHOICE:
        return (
            [response["choice"]]
            if "choice" in response and response["choice"]
            else response.get("choices", [])
        )
    if qtype == schemas.TRUEFALSE:
        return [str(response.get("answer")).lower()]
    if qtype == schemas.SHORTANSWER:
        return [marking.normalise(response.get("text", ""))[:100]]
    if qtype == schemas.NUMERICAL:
        return [f"{response.get('value', '')} {response.get('unit', '')}".strip()[:100]]
    return []
