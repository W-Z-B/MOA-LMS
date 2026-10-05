"""A person's private calendar feed (item 2.32): a secret address a phone calendar subscribes to."""

from django.conf import settings
from django.db import models

from core.fields import EncryptedTextField


class CalendarFeed(models.Model):
    """The secret is kept twice: hashed, to find the feed from the address without storing it in clear,
    and encrypted, so that its owner can see their own address again. Rotating it makes a new secret, and
    the old address stops working at once."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calendar_feed"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    token = EncryptedTextField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Calendar feed of {self.user}"
