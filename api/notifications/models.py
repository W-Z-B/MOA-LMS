"""F11 Notifications: in-app messages with optional email delivery, deduplicated by key."""

from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        INFO = "info", "Information"
        APPROVAL = "approval", "Action required"
        ALERT = "alert", "Alert"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.INFO)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=200, blank=True, help_text="In-app route, e.g. /leave/requests/12")
    dedupe_key = models.CharField(max_length=120, blank=True, help_text="Same key per recipient is sent once")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    emailed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "dedupe_key"],
                condition=models.Q(dedupe_key__gt=""),
                name="notification_once_per_recipient_and_key",
            )
        ]

    def __str__(self) -> str:
        return f"{self.recipient}: {self.title}"
