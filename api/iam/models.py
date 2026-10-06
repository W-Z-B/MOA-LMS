"""Identity and access for the LMS: system roles, multi-factor devices, login attempts.

Access to a course site is decided by membership of that site (courses.Membership); the roles here
cover system-wide duties only. Campuses are referenced by the codes the HRMS owns.
"""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.fields import EncryptedTextField
from core.models import TimeStampedModel


class Role(TimeStampedModel):
    ADMINISTRATOR = "administrator"
    COURSE_ADMIN = "course_admin"
    LECTURER = "lecturer"
    STUDENT = "student"
    AUDITOR = "auditor"
    DPO = "dpo"
    # Reports (items 6.03, 6.04): a head of department reads them for the units of their grants
    # (RoleScope.unit_code), the Registrar for their campus, or every campus when the grant names none.
    HEAD_OF_DEPARTMENT = "head_of_department"
    REGISTRAR = "registrar"
    CODES = (
        (ADMINISTRATOR, "System Administrator"),
        (COURSE_ADMIN, "Course Administrator"),
        (LECTURER, "Lecturer or Instructor"),
        (STUDENT, "Student"),
        (AUDITOR, "Auditor"),
        (DPO, "Data Protection Officer"),
        (HEAD_OF_DEPARTMENT, "Head of Department"),
        (REGISTRAR, "Registrar"),
    )
    # Lecturers too (decision D14): they release marks that become results in the SRMS. Heads of department
    # and the Registrar read reports on marking and staff across their units or campuses. The auditor and the
    # Data Protection Officer read sensitive records (every site and the audit log; anyone's whole record).
    MFA_REQUIRED = frozenset(
        {ADMINISTRATOR, COURSE_ADMIN, LECTURER, HEAD_OF_DEPARTMENT, REGISTRAR, AUDITOR, DPO}
    )

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
    last_used_step = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="The 30-second step of the last code accepted: a code is used once (ASVS 2.8.4)",
    )

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None


class LoginAttempt(models.Model):
    """Every login attempt, used to hold back an account, or a network address, after repeated failures."""

    username = models.CharField(max_length=150, db_index=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    success = models.BooleanField(default=False)

    class Meta:
        ordering = ["-at"]
        indexes = [models.Index(fields=["source_ip", "at"], name="loginattempt_ip_at")]

    def __str__(self) -> str:
        return f"{self.username} {'ok' if self.success else 'failed'} at {self.at:%Y-%m-%d %H:%M}"


class UserSession(models.Model):
    """One signed-in browser or phone, so people can see where they are signed in and end a session.

    Created on sign-in and deleted on sign-out (iam.sessions); the middleware keeps last_seen_at current
    and ends sessions that are idle or too old.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_sessions")
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self) -> str:
        return f"{self.user} since {self.created_at:%Y-%m-%d %H:%M}"


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


class PasswordResetRequest(models.Model):
    """A request for a password link, kept to limit how often one address, or one account, may ask.

    What was typed is not kept: only the account it matched, if any, and the address it came from.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-at"]
        indexes = [models.Index(fields=["source_ip", "at"], name="resetrequest_ip_at")]

    def __str__(self) -> str:
        return f"Password link asked for at {self.at:%Y-%m-%d %H:%M}"


class EmailChange(models.Model):
    """A change of sign-in email address, waiting for the link sent to the new address (item 1.10, ported
    from the HRMS's item 1.42).

    The address is where links to choose a password go, so a change takes effect only when the person
    proves they can read mail sent to the new one. Only a fingerprint of the link's token is kept.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_changes")
    old_email = models.EmailField(blank=True)
    new_email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    asked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    asked_at = models.DateTimeField(auto_now_add=True, db_index=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-asked_at"]

    @property
    def expires_at(self):
        return self.asked_at + timedelta(hours=settings.EMAIL_CHANGE_HOURS)

    @property
    def pending(self) -> bool:
        return self.confirmed_at is None and self.cancelled_at is None and timezone.now() < self.expires_at

    def __str__(self) -> str:
        return f"{self.user} to {self.new_email}"
