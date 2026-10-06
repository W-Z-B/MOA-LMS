"""People as references. The LMS owns no person: staff come from the HRMS, students from the SRMS.

An account is opened for a person from their reference (item 1.22, iam.accounts); when the reference goes
inactive the account is closed at once (people.signals).
"""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class PersonRef(TimeStampedModel):
    class Kind(models.TextChoices):
        STAFF = "staff", "Staff (HRMS employee number)"
        STUDENT = "student", "Student (SRMS student number)"
        LEARNER = "learner", "Learner on open courses, self-registered (item 5.07)"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    external_id = models.CharField(max_length=20, help_text="Employee number or student number")
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    campus_code = models.CharField(max_length=10, blank=True)
    # From the HRMS staff record (blank for students): what required training is assigned by (item 5.05).
    post_title = models.CharField(max_length=160, blank=True, help_text="Post held, from the HRMS")
    unit_code = models.CharField(max_length=20, blank=True, help_text="Organisational unit, from the HRMS")
    supervisor = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supervisees",
        help_text="Who approves this person's staff-development enrolments; filled once the HRMS sends it",
    )
    is_active = models.BooleanField(default=True)
    invited_at = models.DateTimeField(
        null=True, blank=True, help_text="When the last invitation to choose a password was sent (item 1.22)"
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="person"
    )

    class Meta:
        unique_together = [("kind", "external_id")]
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return f"{self.external_id} {self.full_name}"

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p) or self.external_id
