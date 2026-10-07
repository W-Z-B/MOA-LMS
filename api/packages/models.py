"""Packaged content (items 5.12, 5.13) and the statements it reports (item 6.09).

A package is a content item of kind "package": the item keeps the zip file (so it counts against the course's
storage allowance, is copied with the course, and has the item's licence and release conditions), and the
ContentPackage beside it says what the package is and how it counts. Each time a learner opens it they work
in an attempt, which keeps the SCORM run-time data (CMI) for each part of the package, or the H5P result.

Statements are the LMS's own small store of xAPI statements: what packaged content reports, for teaching
staff to read. It is not a general learning record store (see packages.xapi).
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class ContentPackage(TimeStampedModel):
    class Standard(models.TextChoices):
        SCORM12 = "scorm12", "SCORM 1.2"
        SCORM2004 = "scorm2004", "SCORM 2004"
        H5P = "h5p", "H5P"

    item = models.OneToOneField("courses.ContentItem", on_delete=models.CASCADE, related_name="package")
    standard = models.CharField(max_length=10, choices=Standard.choices)
    version_label = models.CharField(max_length=80, blank=True, help_text="As the package describes itself")
    scos = models.JSONField(
        default=list, help_text='The parts a learner opens: [{"id", "title", "href", "parameters"}]'
    )
    entries = models.PositiveIntegerField(default=0, help_text="Files in the package")
    unpacked_bytes = models.PositiveBigIntegerField(default=0)
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Relative weight within the site's coursework; 0 means it does not count",
    )
    grade_category = models.ForeignKey(
        "assessments.GradeCategory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="packages",
        help_text="The gradebook category it counts in (item 2.28)",
    )
    max_attempts = models.PositiveSmallIntegerField(default=0, help_text="0 means no limit")

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(weight__gte=0), name="package_weight_not_negative")]

    def __str__(self) -> str:
        return f"{self.get_standard_display()}: {self.item.title}"

    @property
    def site(self):
        return self.item.module.site


class PackageAttempt(TimeStampedModel):
    """One learner's go at a package. Teaching staff trying it out get preview attempts, never counted."""

    class Completion(models.TextChoices):
        NOT_ATTEMPTED = "not_attempted", "Not started"
        INCOMPLETE = "incomplete", "Started"
        COMPLETED = "completed", "Completed"

    class Success(models.TextChoices):
        UNKNOWN = "unknown", "No result"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Not passed"

    package = models.ForeignKey(ContentPackage, on_delete=models.CASCADE, related_name="attempts")
    person = models.ForeignKey(
        "people.PersonRef",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="package_attempts",
        help_text="The learner; empty only for a preview by someone with no person record",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="package_attempts",
    )
    number = models.PositiveSmallIntegerField(default=1)
    registration = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="The xAPI registration that ties statements to this attempt",
    )
    is_preview = models.BooleanField(default=False)
    runtime = models.JSONField(
        default=dict,
        help_text="Per part of the package: the CMI data as last committed (SCORM), or the result",
    )
    completion = models.CharField(max_length=14, choices=Completion.choices, default=Completion.NOT_ATTEMPTED)
    success = models.CharField(max_length=8, choices=Success.choices, default=Success.UNKNOWN)
    score = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="As a fraction of the maximum, 0 to 1",
    )
    last_commit_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["package", "person", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["package", "person", "number"],
                condition=Q(is_preview=False),
                name="package_attempt_number",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.person} attempt {self.number} at {self.package}"

    @property
    def finished(self) -> bool:
        return self.completion == self.Completion.COMPLETED or self.success != self.Success.UNKNOWN


class Statement(models.Model):
    """An xAPI statement kept by the LMS (item 6.09). The actor is always the learner the LMS knows."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    site = models.ForeignKey(
        "courses.CourseSite", null=True, blank=True, on_delete=models.CASCADE, related_name="statements"
    )
    package = models.ForeignKey(
        ContentPackage, null=True, blank=True, on_delete=models.SET_NULL, related_name="statements"
    )
    attempt = models.ForeignKey(
        PackageAttempt, null=True, blank=True, on_delete=models.SET_NULL, related_name="statements"
    )
    person = models.ForeignKey(
        "people.PersonRef", null=True, blank=True, on_delete=models.CASCADE, related_name="statements"
    )
    verb = models.CharField(max_length=300)
    activity = models.CharField(max_length=500, help_text="The object's id (an IRI)")
    statement = models.JSONField(help_text="The statement as stored, with the LMS's actor, id and times")
    timestamp = models.DateTimeField()
    stored = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-stored"]
        indexes = [
            models.Index(fields=["activity"], name="statement_activity"),
            models.Index(fields=["person", "stored"], name="statement_person_stored"),
        ]

    def __str__(self) -> str:
        return f"{self.verb} {self.activity}"
