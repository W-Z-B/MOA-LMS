"""Identity and access for the LMS: system roles, multi-factor devices, login attempts.

Access to a course site is decided by membership of that site (courses.Membership); the roles here
cover system-wide duties only. Campuses are referenced by the codes the HRMS owns.
"""

from django.conf import settings
from django.db import models

from core.fields import EncryptedTextField
from core.models import TimeStampedModel


class Role(TimeStampedModel):
    ADMINISTRATOR = "administrator"
    COURSE_ADMIN = "course_admin"
    LECTURER = "lecturer"
    STUDENT = "student"
    AUDITOR = "auditor"
    DPO = "dpo"
    CODES = (
        (ADMINISTRATOR, "System Administrator"),
        (COURSE_ADMIN, "Course Administrator"),
        (LECTURER, "Lecturer or Instructor"),
        (STUDENT, "Student"),
        (AUDITOR, "Auditor"),
        (DPO, "Data Protection Officer"),
    )
    MFA_REQUIRED = frozenset({ADMINISTRATOR, COURSE_ADMIN})

    code = models.CharField(max_length=40, unique=True, choices=CODES)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


class RoleScope(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_scopes")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="scopes")
    campus_code = models.CharField(max_length=10, blank=True)
    unit_code = models.CharField(max_length=20, blank=True)

    class Meta:
        unique_together = [("user", "role", "campus_code", "unit_code")]

    def __str__(self) -> str:
        scope = self.unit_code or self.campus_code or "all campuses"
        return f"{self.user} as {self.role.code} ({scope})"


class TotpDevice(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="totp_device"
    )
    secret = EncryptedTextField()
    confirmed_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None


class LoginAttempt(models.Model):
    username = models.CharField(max_length=150, db_index=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    success = models.BooleanField(default=False)

    class Meta:
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"{self.username} {'ok' if self.success else 'failed'} at {self.at:%Y-%m-%d %H:%M}"


class AccessReview(models.Model):
    """A sign-off that someone went through who holds a role and who teaches which site, and confirmed it
    (item 1.21). The access-review list is what was read; this row is the evidence that it was checked."""

    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reviewed_at = models.DateTimeField(auto_now_add=True)
    role_holders = models.PositiveIntegerField(help_text="How many role grants the list held when signed off")
    teaching_staff = models.PositiveIntegerField(
        help_text="How many teaching memberships the list held when signed off"
    )
    notes = models.TextField(blank=True, help_text="What was changed or queried as a result")

    class Meta:
        ordering = ["-reviewed_at"]

    def __str__(self) -> str:
        return f"Access review {self.reviewed_at:%d/%m/%Y} by {self.reviewed_by}"
