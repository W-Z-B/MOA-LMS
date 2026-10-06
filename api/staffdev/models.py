"""Staff development (Phase 5): the catalogue, enrolment approved through the approvals engine, completion
rules, learning paths and required training.

The courses themselves are ordinary course sites of the staff_development kind (item 5.01); what the catalogue
says about one, and the rules that complete it, are kept beside the site here so the site stays as it is.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class CatalogueEntry(TimeStampedModel):
    """What the catalogue says about a staff-development site, how one joins it, and when it is complete."""

    class Enrol(models.TextChoices):
        OPEN = "open", "Anyone on the staff may join"
        APPROVAL = "approval", "Joining is approved by the supervisor"
        CLOSED = "closed", "Not open to join; course administrators enrol people"

    site = models.OneToOneField("courses.CourseSite", on_delete=models.CASCADE, related_name="catalogue")
    summary = models.TextField(blank=True, help_text="What the course covers, in a few sentences")
    audience = models.CharField(max_length=200, blank=True, help_text="Who it is for")
    length_hours = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="About how many hours it takes",
    )
    self_enrol = models.CharField(max_length=10, choices=Enrol.choices, default=Enrol.APPROVAL)
    capacity = models.PositiveIntegerField(null=True, blank=True, help_text="Places; empty means no limit")
    # Completion rules (item 5.03). Every rule switched on must be met; with none on, the course is completed
    # only by a course administrator recording it.
    rule_all_items = models.BooleanField(default=True, help_text="Every published item completed")
    rule_quizzes_passed = models.BooleanField(
        default=False, help_text="Every published quiz with a pass mark passed at that mark"
    )
    rule_assignment_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Every published assignment marked, and released, at least this percentage",
    )
    validity_months = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="How long a completion lasts before it must be renewed"
    )
    issue_certificate = models.BooleanField(default=True, help_text="Issue a certificate on completion")
    certificate_template = models.CharField(
        max_length=40, default="completion", help_text="The certificate template's code"
    )

    class Meta:
        verbose_name_plural = "catalogue entries"

    def __str__(self) -> str:
        return f"Catalogue: {self.site}"

    @property
    def has_rules(self) -> bool:
        return self.rule_all_items or self.rule_quizzes_passed or self.rule_assignment_percent is not None


class EnrolmentRequest(TimeStampedModel):
    """A member of staff asks to join a course that needs approval (item 5.02). It goes to their supervisor
    from the HRMS record, or to the course administrators when the record names none (approvals engine)."""

    class State(models.TextChoices):
        SUBMITTED = "submitted", "Waiting for a decision"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Not approved"
        WITHDRAWN = "withdrawn", "Withdrawn"

    site = models.ForeignKey(
        "courses.CourseSite", on_delete=models.CASCADE, related_name="enrolment_requests"
    )
    person = models.ForeignKey(
        "people.PersonRef", on_delete=models.CASCADE, related_name="enrolment_requests"
    )
    approver = models.ForeignKey(
        "people.PersonRef",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enrolments_to_decide",
        help_text="The supervisor it was sent to; empty means the course administrators decide",
    )
    state = models.CharField(max_length=10, choices=State.choices, default=State.SUBMITTED)
    previous_state = models.CharField(max_length=10, blank=True)
    reason = models.TextField(blank=True, help_text="Why the person wants to take the course")
    decision_comment = models.TextField(blank=True)
    waiting_since = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["site", "person"], condition=Q(state="submitted"), name="one_open_enrolment_request"
            )
        ]

    def __str__(self) -> str:
        return f"{self.person} asks to join {self.site.code} ({self.state})"


class LearningPath(TimeStampedModel):
    """Courses in order for a role, such as new lecturer induction or farm safety (item 5.04). Each course
    opens to the person once the one before it is complete."""

    code = models.SlugField(max_length=40, unique=True)
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    audience = models.CharField(max_length=200, blank=True, help_text="The role it is for")
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class PathStep(models.Model):
    path = models.ForeignKey(LearningPath, on_delete=models.CASCADE, related_name="steps")
    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="path_steps")
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["path", "position"]
        constraints = [
            models.UniqueConstraint(fields=["path", "site"], name="path_site_once"),
            models.UniqueConstraint(fields=["path", "position"], name="path_position_once"),
        ]

    def __str__(self) -> str:
        return f"{self.path.code} {self.position}: {self.site.code}"


class PathEnrolment(models.Model):
    """A person following a path."""

    path = models.ForeignKey(LearningPath, on_delete=models.CASCADE, related_name="enrolments")
    person = models.ForeignKey("people.PersonRef", on_delete=models.CASCADE, related_name="paths")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["path", "person"], name="path_joined_once")]

    def __str__(self) -> str:
        return f"{self.person} on {self.path.code}"


class RequiredTraining(TimeStampedModel):
    """A course that staff must take, by campus, unit and post as the HRMS records them (item 5.05).

    Decision D13 (ADR 0019) puts the requirement in the HRMS. With HRMS_TRAINING_REQUIREMENTS_SYNC on, the
    nightly read of the HRMS's list (integration.hrms.sync_training_requirements) keeps the rows whose source
    is the HRMS, under the HRMS's own number; they are changed in the HRMS, not here. Course administrators
    keep the rest (source lms).
    """

    class Source(models.TextChoices):
        LMS = "lms", "Kept in the LMS"
        HRMS = "hrms", "Kept in the HRMS"

    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="requirements")
    campus_code = models.CharField(max_length=10, blank=True, help_text="Only staff of this campus")
    unit_code = models.CharField(max_length=20, blank=True, help_text="Only staff of this unit")
    post_title = models.CharField(max_length=160, blank=True, help_text="Only staff holding this post")
    due_days = models.PositiveSmallIntegerField(default=30, help_text="Days from assignment to the due date")
    renewal_months = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Taken again this often; empty means once"
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    source = models.CharField(max_length=4, choices=Source.choices, default=Source.LMS)
    hrms_id = models.PositiveIntegerField(
        null=True, blank=True, unique=True, help_text="The HRMS's own number for a requirement it keeps"
    )

    class Meta:
        ordering = ["site__title", "id"]

    def __str__(self) -> str:
        return f"{self.site.title} for {self.describe()}"

    def describe(self) -> str:
        parts = [
            f"post {self.post_title}" if self.post_title else "",
            f"unit {self.unit_code}" if self.unit_code else "",
            f"campus {self.campus_code}" if self.campus_code else "",
        ]
        return ", ".join(p for p in parts if p) or "all staff"


class TrainingAssignment(TimeStampedModel):
    """One member of staff required to take a course by a requirement, and by when (item 5.05).

    Completed when the course is; opened again with a new due date when the completion is about to expire.
    """

    requirement = models.ForeignKey(RequiredTraining, on_delete=models.CASCADE, related_name="assignments")
    person = models.ForeignKey(
        "people.PersonRef", on_delete=models.CASCADE, related_name="training_assignments"
    )
    assigned_on = models.DateField()
    due_on = models.DateField()
    completed_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["due_on", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["requirement", "person"], name="required_training_once_per_person"
            )
        ]

    def __str__(self) -> str:
        return f"{self.person} must take {self.requirement.site.code} by {self.due_on:%d/%m/%Y}"
