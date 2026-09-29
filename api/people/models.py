"""People as references. The LMS owns no person: staff come from the HRMS, students from the SRMS."""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class PersonRef(TimeStampedModel):
    class Kind(models.TextChoices):
        STAFF = "staff", "Staff (HRMS employee number)"
        STUDENT = "student", "Student (SRMS student number)"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    external_id = models.CharField(max_length=20, help_text="Employee number or student number")
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    campus_code = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)
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
