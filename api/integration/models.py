"""Service clients (hashed, scoped keys) and reference data cached from the HRMS."""

import hashlib
import hmac
import secrets

from django.db import models

PREFIX_LENGTH = 8
MIN_KEY_LENGTH = 32


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class ServiceClient(models.Model):
    """A sibling system allowed to call the integration API with a scoped key."""

    name = models.CharField(max_length=60, unique=True)  # srms, lms, ...
    key_prefix = models.CharField(max_length=PREFIX_LENGTH, unique=True)
    key_hash = models.CharField(max_length=64)
    scopes = models.JSONField(default=list, help_text="e.g. ['staff:read', 'org:read']")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.name

    @classmethod
    def issue(cls, name: str, scopes: list[str]) -> tuple["ServiceClient", str]:
        """Create or rotate a client. Returns the client and the key, which is shown only once."""
        key = secrets.token_urlsafe(32)
        return cls.register(name, scopes, key), key

    @classmethod
    def register(cls, name: str, scopes: list[str], key: str) -> "ServiceClient":
        """Create or rotate a client with a key that the caller already holds (a shared platform secret)."""
        if len(key) < MIN_KEY_LENGTH:
            raise ValueError(f"A service key must be at least {MIN_KEY_LENGTH} characters long.")
        client, _ = cls.objects.update_or_create(
            name=name,
            defaults={
                "key_prefix": key[:PREFIX_LENGTH],
                "key_hash": _hash(key),
                "scopes": scopes,
                "is_active": True,
            },
        )
        return client

    @classmethod
    def authenticate(cls, key: str) -> "ServiceClient | None":
        client = cls.objects.filter(key_prefix=key[:PREFIX_LENGTH], is_active=True).first()
        if client is None or not hmac.compare_digest(client.key_hash, _hash(key)):
            return None
        return client

    def has_scope(self, scope: str) -> bool:
        return scope in (self.scopes or [])


class CampusRef(models.Model):
    """Campus reference data owned by the HRMS and cached here by code."""

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    region = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.name


class IntegrationRun(models.Model):
    """One run of a push to, or a pull from, a sibling system, and how each row fared (item 1.23).

    A row the other system refuses (an employee it does not know, a result already locked) is counted as
    failed and named in errors; the rest of the run carries on. A run stopped because the other system could
    not be reached says so in `stopped`, and what was not sent is sent on the next run.
    """

    class Kind(models.TextChoices):
        TRAINING_PUSH = "training_push", "Training completions to the HRMS"
        MARKS_PUSH = "marks_push", "Coursework totals to the SRMS"
        STAFF_SYNC = "staff_sync", "Staff records from the HRMS"
        OUTCOME_SYNC = "outcome_sync", "Learning outcomes from the SRMS course outlines"
        COMPETENCY_PUSH = "competency_push", "Competency results and outcome standings to the SRMS"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    trigger = models.CharField(max_length=20, default="schedule", help_text="schedule, completion or command")
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    ok = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    errors = models.JSONField(
        default=list, blank=True, help_text='[{"ref": ..., "code": ..., "detail": ...}]'
    )
    stopped = models.CharField(max_length=300, blank=True, help_text="Why the run stopped early, if it did")

    class Meta:
        ordering = ["-started_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} at {self.started_at:%Y-%m-%d %H:%M}"
