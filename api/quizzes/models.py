"""Question banks, questions and versions, quizzes, attempts and answers (feature 10, items 3.01 to 3.08).

Moodle is the reference for behaviour. A question keeps every version: editing a question that an attempt
has already used creates a new version, and the attempt keeps the version it was given.
"""

import uuid
from pathlib import PurePath

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import TimeStampedModel
from quizzes.schemas import QTYPE_CHOICES


def _stored(folder: str, filename: str) -> str:
    """Random stored names: a file name never carries a person's name or details onto the disk."""
    extension = PurePath(filename).suffix.lower()[:10]
    now = timezone.now()
    return f"{folder}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{extension}"


def question_image_name(instance, filename: str) -> str:
    return _stored("questions", filename)


def answer_file_name(instance, filename: str) -> str:
    return _stored("quiz-answers", filename)


class QuestionBank(TimeStampedModel):
    """Owned by one course site, or shared by a department (an HRMS unit code)."""

    name = models.CharField(max_length=160)
    site = models.ForeignKey(
        "courses.CourseSite", null=True, blank=True, on_delete=models.CASCADE, related_name="question_banks"
    )
    department_code = models.CharField(
        max_length=20, blank=True, help_text="HRMS unit code of the department that shares this bank"
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(site__isnull=False) & Q(department_code=""))
                | (Q(site__isnull=True) & ~Q(department_code="")),
                name="question_bank_one_owner",
            )
        ]

    def __str__(self) -> str:
        return f"{self.owner_label}: {self.name}"

    @property
    def owner_label(self) -> str:
        return self.site.code if self.site_id else f"Department {self.department_code}"


class QuestionCategory(TimeStampedModel):
    bank = models.ForeignKey(QuestionBank, on_delete=models.CASCADE, related_name="categories")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    name = models.CharField(max_length=160)
    position = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["position", "name", "id"]
        verbose_name_plural = "question categories"

    def __str__(self) -> str:
        return self.name

    def descendant_ids(self) -> list[int]:
        """This category and every category below it."""
        ids, frontier = [self.id], [self.id]
        while frontier:
            frontier = list(
                QuestionCategory.objects.filter(parent_id__in=frontier).values_list("id", flat=True)
            )
            ids.extend(frontier)
        return ids


class Question(TimeStampedModel):
    """The lasting identity of a question. Its wording and settings live in versions."""

    bank = models.ForeignKey(QuestionBank, on_delete=models.CASCADE, related_name="questions")
    category = models.ForeignKey(
        QuestionCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="questions"
    )
    qtype = models.CharField(max_length=20, choices=QTYPE_CHOICES)
    name = models.CharField(max_length=200)
    tags = ArrayField(models.CharField(max_length=40), default=list, blank=True)
    is_archived = models.BooleanField(
        default=False, help_text="Hidden from new quizzes; kept for past attempts"
    )

    class Meta:
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name

    @property
    def latest(self) -> "QuestionVersion":
        cached = getattr(self, "_latest", None)
        if cached is None:
            cached = self.versions.order_by("-number").first()
            self._latest = cached
        return cached


class QuestionVersion(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField(default=1)
    text = models.TextField()
    data = models.JSONField(default=dict, help_text="Type-specific settings; see quizzes.schemas")
    default_mark = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    general_feedback = models.TextField(blank=True)
    image = models.FileField(upload_to=question_image_name, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )

    class Meta:
        ordering = ["question", "number"]
        constraints = [
            models.UniqueConstraint(fields=["question", "number"], name="question_version_number_unique"),
            models.CheckConstraint(condition=Q(default_mark__gt=0), name="question_default_mark_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.question} v{self.number}"


class Quiz(TimeStampedModel):
    class Grading(models.TextChoices):
        HIGHEST = "highest", "Highest attempt"
        AVERAGE = "average", "Average of attempts"
        FIRST = "first", "First attempt"
        LAST = "last", "Last attempt"

    class Review(models.TextChoices):
        IMMEDIATELY = "immediately", "Immediately after the attempt"
        AFTER_CLOSE = "after_close", "After the quiz closes"
        NEVER = "never", "Never"

    class Navigation(models.TextChoices):
        FREE = "free", "Free: move between pages in any order"
        SEQUENTIAL = "sequential", "Sequential: no going back"

    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="quizzes")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    time_limit_minutes = models.PositiveIntegerField(null=True, blank=True)
    attempts_allowed = models.PositiveSmallIntegerField(default=1, help_text="0 means unlimited")
    grading_method = models.CharField(max_length=10, choices=Grading.choices, default=Grading.HIGHEST)
    pass_mark = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Percentage needed to pass"
    )
    weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=1, help_text="Relative weight within the site's coursework"
    )
    is_practice = models.BooleanField(
        default=False, help_text="Revision only: never counts, unlimited attempts"
    )
    is_secure_exam = models.BooleanField(
        default=False,
        help_text=(
            "Secure exam mode (item 3.25, ADR 0045): one attempt only, enforced on the server, and the "
            "sitting's focus changes and copy/paste/right-click attempts are logged for teaching staff to "
            "review. A deterrent on a web page, not a lockdown browser or webcam proctoring (ADR 0006)."
        ),
    )
    is_published = models.BooleanField(default=False)
    shuffle_questions = models.BooleanField(default=False)
    shuffle_answers = models.BooleanField(default=True)
    questions_per_page = models.PositiveSmallIntegerField(
        default=0, help_text="0 puts every question on one page"
    )
    navigation = models.CharField(max_length=10, choices=Navigation.choices, default=Navigation.FREE)
    review_marks = models.CharField(max_length=12, choices=Review.choices, default=Review.IMMEDIATELY)
    review_correct = models.CharField(max_length=12, choices=Review.choices, default=Review.AFTER_CLOSE)
    review_feedback = models.CharField(max_length=12, choices=Review.choices, default=Review.IMMEDIATELY)
    auto_release = models.BooleanField(
        default=True,
        help_text="Release a result as soon as it is fully marked; otherwise the lecturer releases it",
    )
    grade_category = models.ForeignKey(
        "assessments.GradeCategory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quizzes",
        help_text="The gradebook category it counts in (item 2.28)",
    )
    feedback_bands = models.JSONField(
        default=list, blank=True, help_text='Overall feedback: [{"min_percent": 80, "feedback": "..."}]'
    )

    class Meta:
        ordering = ["closes_at", "id"]
        verbose_name_plural = "quizzes"
        constraints = [
            models.CheckConstraint(condition=Q(weight__gte=0), name="quiz_weight_not_negative"),
            models.CheckConstraint(
                condition=Q(pass_mark__isnull=True) | (Q(pass_mark__gte=0) & Q(pass_mark__lte=100)),
                name="quiz_pass_mark_percentage",
            ),
            models.CheckConstraint(
                condition=Q(is_secure_exam=False) | Q(attempts_allowed=1),
                name="quiz_secure_exam_one_attempt",
            ),
            models.CheckConstraint(
                condition=Q(is_secure_exam=False) | Q(is_practice=False),
                name="quiz_secure_exam_not_practice",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.site.code}: {self.title}"

    @property
    def counts(self) -> bool:
        """Counts towards coursework: published, not practice, and weighted."""
        return self.is_published and not self.is_practice and self.weight > 0


class QuizSlot(TimeStampedModel):
    """A fixed question, or N questions drawn at random from a category when each attempt starts."""

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="slots")
    position = models.PositiveSmallIntegerField(default=1)
    question = models.ForeignKey(
        Question, null=True, blank=True, on_delete=models.PROTECT, related_name="slots"
    )
    category = models.ForeignKey(
        QuestionCategory, null=True, blank=True, on_delete=models.PROTECT, related_name="slots"
    )
    random_count = models.PositiveSmallIntegerField(default=1)
    include_subcategories = models.BooleanField(default=True)
    tag = models.CharField(max_length=40, blank=True, help_text="Random questions only from this tag")
    mark = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(question__isnull=False) & Q(category__isnull=True))
                | (Q(question__isnull=True) & Q(category__isnull=False)),
                name="quiz_slot_question_or_category",
            ),
            models.CheckConstraint(
                condition=Q(mark__isnull=True) | Q(mark__gt=0), name="quiz_slot_mark_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quiz} slot {self.position}"


class QuizOverride(TimeStampedModel):
    """Per-student extra time, extra attempts or a later close date, set by teaching staff (part of 3.23)."""

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="overrides")
    student = models.ForeignKey("people.PersonRef", on_delete=models.CASCADE, related_name="quiz_overrides")
    extra_minutes = models.PositiveIntegerField(default=0)
    extra_attempts = models.PositiveSmallIntegerField(default=0)
    closes_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(
        max_length=200, blank=True, help_text="Kept for the record; not shown to students"
    )

    class Meta:
        ordering = ["quiz", "id"]
        constraints = [models.UniqueConstraint(fields=["quiz", "student"], name="quiz_override_once")]

    def __str__(self) -> str:
        return f"{self.quiz} override for {self.student}"


class Attempt(TimeStampedModel):
    class State(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        FINISHED = "finished", "Finished"

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey("people.PersonRef", on_delete=models.PROTECT, related_name="quiz_attempts")
    number = models.PositiveSmallIntegerField(default=1)
    state = models.CharField(max_length=12, choices=State.choices, default=State.IN_PROGRESS)
    started_at = models.DateTimeField()
    deadline = models.DateTimeField(
        null=True, blank=True, help_text="Server time after which answers are refused"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    auto_submitted = models.BooleanField(default=False)
    current_page = models.PositiveSmallIntegerField(default=1)
    score = models.DecimalField(max_digits=9, decimal_places=4, null=True, blank=True)
    max_score = models.DecimalField(max_digits=9, decimal_places=4, default=0)
    needs_grading = models.BooleanField(default=False)
    is_released = models.BooleanField(default=False)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["quiz", "student", "number"]
        constraints = [
            models.UniqueConstraint(fields=["quiz", "student", "number"], name="attempt_number_unique"),
            models.UniqueConstraint(
                fields=["quiz", "student"],
                condition=Q(state="in_progress"),
                name="attempt_one_in_progress",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student} attempt {self.number} at {self.quiz.title}"

    @property
    def percent(self):
        if self.score is None or not self.max_score:
            return None
        return self.score / self.max_score * 100


class AttemptAnswer(TimeStampedModel):
    """One question in one attempt: the version used, the option order shown, the answer and its mark."""

    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    position = models.PositiveSmallIntegerField()
    page = models.PositiveSmallIntegerField(default=1)
    version = models.ForeignKey(QuestionVersion, on_delete=models.PROTECT, related_name="answers")
    max_mark = models.DecimalField(max_digits=6, decimal_places=2)
    layout = models.JSONField(default=dict, blank=True)
    response = models.JSONField(null=True, blank=True)
    file = models.FileField(upload_to=answer_file_name, blank=True)
    client_saved_at = models.DateTimeField(null=True, blank=True)
    saved_at = models.DateTimeField(null=True, blank=True)
    fraction = models.DecimalField(max_digits=8, decimal_places=7, null=True, blank=True)
    awarded = models.DecimalField(max_digits=9, decimal_places=4, null=True, blank=True)
    auto_feedback = models.TextField(blank=True)
    needs_manual = models.BooleanField(default=False)
    comment = models.TextField(blank=True, help_text="The marker's comment")
    marked_by = models.ForeignKey(
        "people.PersonRef", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    marked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["attempt", "position"]
        constraints = [
            models.UniqueConstraint(fields=["attempt", "position"], name="attempt_answer_position_unique"),
            models.CheckConstraint(
                condition=Q(awarded__isnull=True) | Q(awarded__gte=0), name="awarded_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.attempt} question {self.position}"

    @property
    def qtype(self) -> str:
        return self.version.question.qtype


class AttemptEvent(models.Model):
    """What happened during an attempt, in server time (item 3.21 part).

    The INTEGRITY kinds (item 3.25) are reported by the student's own browser during a secure exam sitting:
    they describe what the page observed, in server time, not a verdict on the student. See
    quizzes.services.record_integrity_event and ADR 0045.
    """

    class Kind(models.TextChoices):
        STARTED = "started", "Started"
        RESUMED = "resumed", "Resumed"
        ANSWER_SAVED = "answer_saved", "Answer saved"
        ANSWER_REFUSED = "answer_refused", "Answer refused"
        PAGE_CHANGED = "page_changed", "Moved to the next page"
        SUBMITTED = "submitted", "Submitted"
        AUTO_SUBMITTED = "auto_submitted", "Submitted automatically when time ran out"
        MARKED = "marked", "Marked by a person"
        RELEASED = "released", "Result released"
        # Secure exam integrity events (item 3.25): reported by the browser, not enforced by it.
        FOCUS_LOST = "focus_lost", "Left the quiz window or tab"
        FOCUS_RESUMED = "focus_resumed", "Returned to the quiz window or tab"
        COPY_ATTEMPTED = "copy_attempted", "Tried to copy text from the quiz page"
        PASTE_ATTEMPTED = "paste_attempted", "Tried to paste into an answer"
        CONTEXT_MENU_BLOCKED = "context_menu_blocked", "Tried to open the right-click menu"

    # The kinds that make up the integrity log shown to teaching staff (item 3.25), as distinct from the
    # full event log (every kind) kept for every attempt.
    INTEGRITY_KINDS = frozenset(
        {
            Kind.FOCUS_LOST,
            Kind.FOCUS_RESUMED,
            Kind.COPY_ATTEMPTED,
            Kind.PASTE_ATTEMPTED,
            Kind.CONTEXT_MENU_BLOCKED,
        }
    )

    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    at = models.DateTimeField(auto_now_add=True)
    detail = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["at", "id"]

    def __str__(self) -> str:
        return f"{self.attempt}: {self.kind}"
