"""Assignments, submissions and marks. Coursework totals are returned to the SRMS, which owns results.

A student's Submission is the record that is marked; each time work is handed in an attempt is added to it
with its own receipt (item 2.21), and the latest attempt is the one marked. In a group assignment one
member hands in for the group: the attempt is kept on that member's submission, and every member's
submission names the group, so the group's work is found through it (item 2.27).
"""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from core.fields import EncryptedTextField
from core.models import TimeStampedModel
from core.uploads import feedback_name, submission_name


class GradeCategory(TimeStampedModel):
    """A part of a site's coursework with its own weight, such as "Tests" or "Practicals" (item 2.28).

    Assignments, quizzes and practical tasks may each be placed in one. The coursework total is then the
    weighted mean of the categories; items in no category count together as one more category, whose
    weight is the sum of their own weights (assessments.services.coursework_working).
    """

    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="grade_categories")
    name = models.CharField(max_length=80)
    weight = models.DecimalField(
        max_digits=6, decimal_places=2, help_text="Relative weight of the category in the coursework total"
    )
    drop_lowest = models.PositiveSmallIntegerField(
        default=0, help_text="How many of the lowest counted items to leave out (at least one always counts)"
    )
    position = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["position", "id"]
        verbose_name_plural = "grade categories"
        constraints = [
            models.UniqueConstraint(fields=["site", "name"], name="grade_category_name_once"),
            models.CheckConstraint(condition=Q(weight__gt=0), name="grade_category_weight_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.site.code}: {self.name}"


class Assignment(TimeStampedModel):
    class LatePenalty(models.TextChoices):
        NONE = "none", "No penalty"
        PER_DAY = "per_day", "A percentage for each day or part of a day late"
        PER_HOUR = "per_hour", "A percentage for each hour or part of an hour late"

    class Moderation(models.TextChoices):
        NONE = "none", "No moderation"
        SAMPLE = "sample", "A second marker checks a sample"
        DOUBLE = "double", "Every submission is marked twice"

    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="assignments")
    title = models.CharField(max_length=160)
    instructions = models.TextField(blank=True)
    opens_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField()
    max_mark = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=1, help_text="Relative weight within the site's coursework"
    )
    allow_late = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False)
    category = models.ForeignKey(
        GradeCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="assignments"
    )
    # Handing in (items 2.21, 2.22, 3.22)
    allow_resubmission = models.BooleanField(
        default=True, help_text="Work may be handed in again, until the due date, while it is not marked"
    )
    accepted_kinds = ArrayField(
        models.CharField(max_length=10),
        default=list,
        blank=True,
        help_text="File kinds accepted (core.uploads); empty accepts every kind a submission may be",
    )
    max_files = models.PositiveSmallIntegerField(
        default=5, help_text="Files in one hand-in; 0 allows text only"
    )
    requires_integrity = models.BooleanField(
        default=False, help_text="The student accepts the academic integrity statement with each hand-in"
    )
    # Late work (item 2.35)
    late_penalty = models.CharField(max_length=10, choices=LatePenalty.choices, default=LatePenalty.NONE)
    late_penalty_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Percent of the maximum mark taken per day or hour",
    )
    late_penalty_cap = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="The most taken in all, in percent"
    )
    # Groups (item 2.27)
    is_group = models.BooleanField(default=False, help_text="One submission per group, marked for the group")
    groups = models.ManyToManyField(
        "courses.SiteGroup", blank=True, related_name="+", help_text="Groups that take part; empty is all"
    )
    # Marking (items 3.09, 3.10, 3.16, 3.17)
    rubric = models.ForeignKey(
        "rubrics.Rubric", null=True, blank=True, on_delete=models.PROTECT, related_name="assignments"
    )
    anonymous = models.BooleanField(
        default=False, help_text="Names hidden from markers until marks are released"
    )
    moderation = models.CharField(max_length=10, choices=Moderation.choices, default=Moderation.NONE)
    marks_released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(max_mark__gt=0) & Q(weight__gt=0), name="assignment_positive_values"
            ),
            models.CheckConstraint(
                condition=Q(late_penalty_percent__gte=0) & Q(late_penalty_percent__lte=100),
                name="assignment_late_penalty_percentage",
            ),
            models.CheckConstraint(
                condition=Q(late_penalty_cap__isnull=True)
                | (Q(late_penalty_cap__gte=0) & Q(late_penalty_cap__lte=100)),
                name="assignment_late_penalty_cap_percentage",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.site.code}: {self.title}"

    @property
    def names_hidden(self) -> bool:
        """Anonymous marking: names stay hidden from markers until the marks are released (item 3.16)."""
        return self.anonymous and self.marks_released_at is None


class Submission(TimeStampedModel):
    """One student's work for one assignment, and the record that is marked. text, file and submitted_at
    repeat the latest attempt (the first of its files), so a list of submissions reads them directly."""

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey("people.PersonRef", on_delete=models.PROTECT, related_name="submissions")
    group = models.ForeignKey(
        "courses.SiteGroup", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    text = models.TextField(blank=True)
    file = models.FileField(upload_to=submission_name, blank=True)
    original_name = models.CharField(
        max_length=255, blank=True, help_text="The name the file had when handed in; used for downloads"
    )
    submitted_at = models.DateTimeField()
    client_submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the device says it was handed in, for work sent later from its offline queue. "
        "Server time decides lateness; this is shown to teaching staff, who may excuse it by an extension.",
    )
    is_late = models.BooleanField(default=False)

    class Meta:
        unique_together = [("assignment", "student")]
        ordering = ["assignment", "student"]

    def __str__(self) -> str:
        return f"{self.student} for {self.assignment.title}"


class SubmissionAttempt(models.Model):
    """One hand-in, kept for good (item 2.21). The receipt code and the content hash let the student prove
    what they handed in and when."""

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="attempts")
    number = models.PositiveSmallIntegerField()
    submitted_by = models.ForeignKey("people.PersonRef", on_delete=models.PROTECT, related_name="+")
    submitted_at = models.DateTimeField()
    client_submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The device's time, for work sent later from its offline queue (4.02)",
    )
    text = models.TextField(blank=True)
    is_late = models.BooleanField(default=False)
    receipt = models.CharField(max_length=20, unique=True)
    content_hash = models.CharField(max_length=64, help_text="SHA-256 of the text and every file, in order")
    integrity_statement = models.TextField(
        blank=True, help_text="The academic integrity statement the student accepted with this hand-in"
    )

    class Meta:
        ordering = ["submission", "number"]
        constraints = [
            models.UniqueConstraint(fields=["submission", "number"], name="submission_attempt_number_once")
        ]

    def __str__(self) -> str:
        return f"{self.submission} attempt {self.number}"


class SubmissionFile(models.Model):
    attempt = models.ForeignKey(SubmissionAttempt, on_delete=models.CASCADE, related_name="files")
    position = models.PositiveSmallIntegerField(default=1)
    file = models.FileField(upload_to=submission_name)
    original_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)

    class Meta:
        ordering = ["attempt", "position"]

    def __str__(self) -> str:
        return self.original_name


class Mark(TimeStampedModel):
    class Source(models.TextChoices):
        MANUAL = "manual", "Entered by the marker"
        RUBRIC = "rubric", "Filled from the rubric or marking guide"
        UPLOAD = "upload", "Uploaded from a spreadsheet"
        GROUP = "group", "The group's mark, with any individual adjustment"
        AGREED = "agreed", "Agreed after moderation"

    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, related_name="mark")
    mark = models.DecimalField(max_digits=6, decimal_places=2)
    feedback = models.TextField(blank=True)
    marked_by = models.ForeignKey("people.PersonRef", null=True, blank=True, on_delete=models.SET_NULL)
    is_released = models.BooleanField(default=False)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    group_mark = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, help_text="The group's mark before adjustment"
    )
    adjustment = models.DecimalField(
        max_digits=6, decimal_places=2, default=0, help_text="This member's adjustment to the group's mark"
    )
    rubric_scores = models.JSONField(
        default=list,
        blank=True,
        help_text='[{"criterion": id, "level": id or null, "points": "2.00" or null, "comment": ""}]',
    )

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(mark__gte=0), name="mark_not_negative")]

    def __str__(self) -> str:
        return f"{self.submission}: {self.mark}"


class MarkVersion(models.Model):
    """Every state a mark has had, kept as evidence for appeals (item 3.19)."""

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="mark_versions")
    mark = models.DecimalField(max_digits=6, decimal_places=2)
    feedback = models.TextField(blank=True)
    is_released = models.BooleanField(default=False)
    source = models.CharField(max_length=10, choices=Mark.Source.choices)
    rubric_scores = models.JSONField(default=list, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["submission", "changed_at", "id"]

    def __str__(self) -> str:
        return f"{self.submission}: {self.mark} at {self.changed_at:%d/%m/%Y %H:%M}"


class FeedbackFile(TimeStampedModel):
    """A feedback sheet, marked-up work or a recording returned to the student with the mark (item 2.24)."""

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="feedback_files")
    file = models.FileField(upload_to=feedback_name)
    original_name = models.CharField(max_length=255)
    kind = models.CharField(max_length=10, help_text="The kind core.uploads found in the file")
    size = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["submission", "id"]

    def __str__(self) -> str:
        return self.original_name


class Moderation(TimeStampedModel):
    """A second marking of one submission (item 3.17). Both originals stay; the agreed mark is the mark."""

    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, related_name="moderation")
    first_mark = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    first_marker = models.ForeignKey(
        "people.PersonRef", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    second_mark = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    second_marker = models.ForeignKey(
        "people.PersonRef", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    second_note = models.TextField(blank=True)
    agreed_mark = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    agreed_by = models.ForeignKey(
        "people.PersonRef", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    agreed_at = models.DateTimeField(null=True, blank=True)
    agreed_note = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"Moderation of {self.submission}"


class Extension(TimeStampedModel):
    """A later due date for one student or one group, with the reason (item 2.26)."""

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="extensions")
    student = models.ForeignKey(
        "people.PersonRef", null=True, blank=True, on_delete=models.CASCADE, related_name="extensions"
    )
    group = models.ForeignKey(
        "courses.SiteGroup", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    due_at = models.DateTimeField()
    reason = models.CharField(max_length=300)
    granted_by = models.ForeignKey(
        "people.PersonRef", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["assignment", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(student__isnull=False) & Q(group__isnull=True))
                | (Q(student__isnull=True) & Q(group__isnull=False)),
                name="extension_student_or_group",
            ),
            models.UniqueConstraint(fields=["assignment", "student"], name="extension_once_per_student"),
            models.UniqueConstraint(fields=["assignment", "group"], name="extension_once_per_group"),
        ]

    def __str__(self) -> str:
        return f"Extension on {self.assignment} to {self.due_at:%d/%m/%Y %H:%M}"


class Accommodation(TimeStampedModel):
    """Arrangements held once for a student and applied everywhere automatically (item 3.23).

    Course administrators keep them. Teaching staff learn only that an accommodation applies, never why.
    """

    person = models.OneToOneField("people.PersonRef", on_delete=models.CASCADE, related_name="accommodation")
    extra_time_percent = models.PositiveSmallIntegerField(
        default=0, help_text="Added to every quiz time limit, in percent"
    )
    extra_days = models.PositiveSmallIntegerField(default=0, help_text="Added to every assignment due date")
    other_format = models.CharField(
        max_length=300, blank=True, help_text="Another format of material or assessment the student needs"
    )
    # Often a health matter: encrypted at rest, and masked in the audit log (ASVS 6.1.2).
    reason = EncryptedTextField(null=True, blank=True, help_text="Why; seen only by course administrators")
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"Accommodation for {self.person}"


class SrmsTransfer(models.Model):
    """What was sent to the SRMS for one student on one site, and what the SRMS answered (items 2.31, 3.18).

    Once the SRMS has accepted or locked a student's coursework, the student's marks on the site are locked
    in the LMS: a change goes through the SRMS's correction process.
    """

    class Outcome(models.TextChoices):
        ACCEPTED = "accepted", "Accepted by the SRMS"
        LOCKED = "locked", "Already locked in the SRMS"
        UNKNOWN = "unknown", "Not known to the SRMS"

    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="srms_transfers")
    student = models.ForeignKey("people.PersonRef", on_delete=models.PROTECT, related_name="srms_transfers")
    percent = models.DecimalField(max_digits=6, decimal_places=2)
    outcome = models.CharField(max_length=10, choices=Outcome.choices)
    sent_at = models.DateTimeField()
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["site", "student", "-sent_at"]

    def __str__(self) -> str:
        return f"{self.student} on {self.site.code}: {self.percent} ({self.outcome})"
