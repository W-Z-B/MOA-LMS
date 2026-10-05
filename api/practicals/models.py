"""Practical and field assessment (items 3.12 to 3.15).

Observation checklists marked in the field, competency records against the Council for TVET's
occupational standards (decision D8), the student's practical logbook with the supervisor's sign-off,
and the keys that let a phone's offline queue send the same record twice without making two.
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel
from practicals.uploads import evidence_name


class UnitType(models.TextChoices):
    """The kind of place practical work is done in."""

    CROP_PLOT = "crop_plot", "Crop plot"
    LIVESTOCK_UNIT = "livestock_unit", "Livestock unit"
    POND = "pond", "Fish pond"
    FOREST_STAND = "forest_stand", "Forest stand"
    LABORATORY = "laboratory", "Laboratory"
    PROCESSING_UNIT = "processing_unit", "Processing unit"
    OTHER = "other", "Other"


def _place_constraints(prefix: str) -> list[models.CheckConstraint]:
    return [
        models.CheckConstraint(
            condition=Q(latitude__isnull=True) | Q(latitude__gte=-90, latitude__lte=90),
            name=f"{prefix}_latitude_range",
        ),
        models.CheckConstraint(
            condition=Q(longitude__isnull=True) | Q(longitude__gte=-180, longitude__lte=180),
            name=f"{prefix}_longitude_range",
        ),
    ]


class PracticalAssessor(TimeStampedModel):
    """A field instructor or assessor named on a site. They may record observations and competency results
    on the site's practical tasks without being one of its teaching staff (courses.Membership is left as it
    is: an assessor is often a farm manager or technician who teaches nothing else on the course)."""

    site = models.ForeignKey(
        "courses.CourseSite", on_delete=models.CASCADE, related_name="practical_assessors"
    )
    person = models.ForeignKey("people.PersonRef", on_delete=models.CASCADE, related_name="+")
    note = models.CharField(max_length=160, blank=True, help_text="For example: farm manager, poultry unit")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["site", "person__last_name", "person__first_name"]
        unique_together = [("site", "person")]

    def __str__(self) -> str:
        return f"{self.person} assesses on {self.site.code}"


class PracticalTask(TimeStampedModel):
    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="practical_tasks")
    title = models.CharField(max_length=160)
    instructions = models.TextField(blank=True)
    unit_type = models.CharField(max_length=20, choices=UnitType.choices, default=UnitType.CROP_PLOT)
    location = models.CharField(max_length=160, blank=True, help_text="Where it is done, for example Plot 7")
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Relative weight within the site's coursework; 0 when the task does not count",
    )
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(
        null=True, blank=True, help_text="After this a student with no observation counts as missed"
    )
    max_attempts = models.PositiveSmallIntegerField(default=3, help_text="First attempt and re-assessments")
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["closes_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(weight__gte=0), name="practical_task_weight_not_negative"),
            models.CheckConstraint(condition=Q(max_attempts__gte=1), name="practical_task_one_attempt"),
            models.CheckConstraint(
                condition=Q(opens_at__isnull=True)
                | Q(closes_at__isnull=True)
                | Q(closes_at__gt=models.F("opens_at")),
                name="practical_task_window_order",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.site.code}: {self.title}"


class PracticalCriterion(TimeStampedModel):
    class Kind(models.TextChoices):
        PASS_FAIL = "pass_fail", "Pass or fail"
        SCORED = "scored", "Scored from 0"

    task = models.ForeignKey(PracticalTask, on_delete=models.CASCADE, related_name="criteria")
    position = models.PositiveSmallIntegerField(default=1)
    text = models.CharField(max_length=300)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PASS_FAIL)
    max_score = models.PositiveSmallIntegerField(default=1, help_text="1 for pass or fail")
    pass_score = models.PositiveSmallIntegerField(
        default=1, help_text="The least score that counts as a pass"
    )
    is_critical = models.BooleanField(default=False, help_text="Must be passed for the task to be passed")
    performance_criteria = models.ManyToManyField(
        "PerformanceCriterion", blank=True, related_name="practical_criteria"
    )

    class Meta:
        ordering = ["position", "id"]
        verbose_name_plural = "practical criteria"
        constraints = [
            models.CheckConstraint(condition=Q(max_score__gte=1), name="practical_criterion_max_score"),
            models.CheckConstraint(
                condition=Q(pass_score__gte=1) & Q(pass_score__lte=models.F("max_score")),
                name="practical_criterion_pass_score",
            ),
        ]

    def __str__(self) -> str:
        return self.text


class Observation(TimeStampedModel):
    """One attempt by one student at a practical task, marked against every criterion. A re-assessment is a
    new observation with the next attempt number; earlier attempts are kept as they were."""

    task = models.ForeignKey(PracticalTask, on_delete=models.PROTECT, related_name="observations")
    student = models.ForeignKey("people.PersonRef", on_delete=models.PROTECT, related_name="+")
    attempt = models.PositiveSmallIntegerField()
    assessor = models.ForeignKey("people.PersonRef", on_delete=models.PROTECT, related_name="+")
    observed_at = models.DateTimeField(help_text="When it was observed, by the phone's clock")
    recorded_at = models.DateTimeField(auto_now_add=True, help_text="When the server received it")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_text = models.CharField(max_length=160, blank=True)
    comments = models.TextField(blank=True)
    is_released = models.BooleanField(default=False)
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["task", "student", "attempt"]
        unique_together = [("task", "student", "attempt")]
        constraints = _place_constraints("observation")

    def __str__(self) -> str:
        return f"{self.student} on {self.task.title}, attempt {self.attempt}"

    def score(self) -> tuple[int, int]:
        """(earned, possible) over every criterion: a pass counts 1 of 1, a score counts as given."""
        earned = possible = 0
        for result in self.results.all():
            criterion = result.criterion
            possible += criterion.max_score
            if criterion.kind == PracticalCriterion.Kind.SCORED:
                earned += min(result.score or 0, criterion.max_score)
            elif result.passed:
                earned += 1
        return earned, possible

    def fraction(self) -> Decimal | None:
        earned, possible = self.score()
        return Decimal(earned) / Decimal(possible) if possible else None

    def critical_passed(self) -> bool:
        return all(r.passed for r in self.results.all() if r.criterion.is_critical)


class ObservationResult(models.Model):
    observation = models.ForeignKey(Observation, on_delete=models.CASCADE, related_name="results")
    criterion = models.ForeignKey(PracticalCriterion, on_delete=models.PROTECT, related_name="results")
    passed = models.BooleanField()
    score = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Scored criteria only")
    comment = models.CharField(max_length=500, blank=True)

    class Meta:
        unique_together = [("observation", "criterion")]
        ordering = ["criterion__position", "criterion_id"]


class ObservationPhoto(TimeStampedModel):
    observation = models.ForeignKey(Observation, on_delete=models.CASCADE, related_name="photos")
    file = models.FileField(upload_to=evidence_name)
    original_name = models.CharField(max_length=255, blank=True)

    def __str__(self) -> str:
        return self.original_name or self.file.name


class CompetencyFramework(TimeStampedModel):
    """An occupational standard, imported as published: units of competence, their elements and the
    performance criteria. The LMS reads frameworks, it does not author them (feature 19)."""

    code = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    source = models.CharField(
        max_length=200, blank=True, help_text='e.g. "Council for TVET occupational standard"'
    )
    version = models.CharField(max_length=20, default="1")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("code", "version")]
        ordering = ["code", "version"]

    def __str__(self) -> str:
        return f"{self.code} v{self.version} {self.title}"


class CompetencyUnit(models.Model):
    framework = models.ForeignKey(CompetencyFramework, on_delete=models.CASCADE, related_name="units")
    code = models.CharField(max_length=40)
    title = models.CharField(max_length=300)
    position = models.PositiveSmallIntegerField(default=1)

    class Meta:
        unique_together = [("framework", "code")]
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.code} {self.title}"


class CompetencyElement(models.Model):
    unit = models.ForeignKey(CompetencyUnit, on_delete=models.CASCADE, related_name="elements")
    code = models.CharField(max_length=40)
    title = models.CharField(max_length=300)
    position = models.PositiveSmallIntegerField(default=1)

    class Meta:
        unique_together = [("unit", "code")]
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.code} {self.title}"


class PerformanceCriterion(models.Model):
    element = models.ForeignKey(CompetencyElement, on_delete=models.CASCADE, related_name="criteria")
    code = models.CharField(max_length=40)
    text = models.CharField(max_length=500)
    position = models.PositiveSmallIntegerField(default=1)

    class Meta:
        unique_together = [("element", "code")]
        ordering = ["position", "id"]
        verbose_name_plural = "performance criteria"

    def __str__(self) -> str:
        return f"{self.code} {self.text}"


class SiteFramework(TimeStampedModel):
    """The site follows this framework: its units are recorded beside the marks."""

    site = models.ForeignKey(
        "courses.CourseSite", on_delete=models.CASCADE, related_name="competency_frameworks"
    )
    framework = models.ForeignKey(CompetencyFramework, on_delete=models.PROTECT, related_name="sites")

    class Meta:
        ordering = ["site", "id"]
        unique_together = [("site", "framework")]


class AssignmentCompetencyMap(TimeStampedModel):
    """An assignment (assessments.Assignment, held by id so this module does not change that one) gives
    evidence towards a performance criterion."""

    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="+")
    assignment_id = models.PositiveIntegerField()
    performance_criterion = models.ForeignKey(
        PerformanceCriterion, on_delete=models.CASCADE, related_name="assignment_maps"
    )

    class Meta:
        ordering = ["site", "assignment_id", "id"]
        unique_together = [("assignment_id", "performance_criterion")]


class CompetencyResult(TimeStampedModel):
    """One student's standing on one unit of competence, as confirmed by an assessor. The system suggests;
    a person decides. Every change is in the audit log with what it was before."""

    class Status(models.TextChoices):
        COMPETENT = "competent", "Competent"
        NOT_YET_COMPETENT = "not_yet_competent", "Not yet competent"
        NOT_ASSESSED = "not_assessed", "Not assessed"

    site = models.ForeignKey(
        "courses.CourseSite", on_delete=models.CASCADE, related_name="competency_results"
    )
    student = models.ForeignKey("people.PersonRef", on_delete=models.PROTECT, related_name="+")
    unit = models.ForeignKey(CompetencyUnit, on_delete=models.PROTECT, related_name="results")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_ASSESSED)
    assessor = models.ForeignKey("people.PersonRef", on_delete=models.PROTECT, related_name="+")
    decided_on = models.DateField()
    comments = models.TextField(blank=True)
    client_recorded_at = models.DateTimeField(null=True, blank=True)
    evidence_observations = models.ManyToManyField(Observation, blank=True, related_name="competency_results")
    evidence_submission_ids = ArrayField(models.PositiveIntegerField(), default=list, blank=True)

    class Meta:
        unique_together = [("site", "student", "unit")]
        ordering = ["site", "student", "unit__position"]

    def __str__(self) -> str:
        return f"{self.student} {self.unit.code}: {self.status}"


class LogbookEntry(TimeStampedModel):
    """A student's own record of practical work. Signed entries are locked."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for sign-off"
        SIGNED = "signed", "Signed off"
        RETURNED = "returned", "Returned for correction"

    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="logbook_entries")
    student = models.ForeignKey("people.PersonRef", on_delete=models.PROTECT, related_name="+")
    work_date = models.DateField()
    unit_type = models.CharField(max_length=20, choices=UnitType.choices)
    unit_text = models.CharField(max_length=160, blank=True, help_text="For example: Pen 3, broilers")
    task = models.CharField(max_length=300)
    hours = models.DecimalField(max_digits=4, decimal_places=2)
    notes = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    client_recorded_at = models.DateTimeField(help_text="When it was written, by the phone's clock")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    supervisor = models.ForeignKey(
        "people.PersonRef", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-work_date", "-id"]
        verbose_name_plural = "logbook entries"
        constraints = [
            models.CheckConstraint(
                condition=Q(hours__gt=0) & Q(hours__lte=24), name="logbook_hours_in_a_day"
            ),
            *_place_constraints("logbook"),
        ]

    def __str__(self) -> str:
        return f"{self.student} {self.work_date}: {self.task}"


class LogbookPhoto(TimeStampedModel):
    entry = models.ForeignKey(LogbookEntry, on_delete=models.CASCADE, related_name="photos")
    file = models.FileField(upload_to=evidence_name)
    original_name = models.CharField(max_length=255, blank=True)

    def __str__(self) -> str:
        return self.original_name or self.file.name


class IdempotencyKey(models.Model):
    """A write already done, by its client-made key: the same key sent again returns the same answer and
    changes nothing. Only successful writes are kept, so a refused request can be corrected and resent."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    key = models.UUIDField()
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=300)
    fingerprint = models.CharField(max_length=64)
    status_code = models.PositiveSmallIntegerField()
    response = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "key")]

    def __str__(self) -> str:
        return f"{self.method} {self.path} {self.key}"
