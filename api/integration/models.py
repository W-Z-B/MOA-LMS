"""Service clients (hashed, scoped keys) and reference data cached from the HRMS."""

import hashlib
import hmac
import secrets

from django.db import models

PREFIX_LENGTH = 8


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
        client, _ = cls.objects.update_or_create(
            name=name,
            defaults={
                "key_prefix": key[:PREFIX_LENGTH],
                "key_hash": _hash(key),
                "scopes": scopes,
                "is_active": True,
            },
        )
        return client, key

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
