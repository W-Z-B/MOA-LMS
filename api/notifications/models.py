"""F11 Notifications: in-app messages with optional email delivery, deduplicated by key."""

from django.conf import settings
from django.db import models

from core.fields import EncryptedTextField


class Notification(models.Model):
    class Kind(models.TextChoices):
        INFO = "info", "Information"
        APPROVAL = "approval", "Action required"
        ALERT = "alert", "Alert"
        MARK = "mark", "Marks and feedback"
        REMINDER = "reminder", "Reminders before due dates"
        RECEIPT = "receipt", "Receipts for work handed in"
        ANNOUNCEMENT = "announcement", "Course announcements"

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
    in_summary = models.BooleanField(
        default=False, help_text="Held for the person's daily summary email instead of an email of its own"
    )
    summarised_at = models.DateTimeField(null=True, blank=True)

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


class NotificationPreference(models.Model):
    """How one person wants one kind of notification (item 2.33). In-app notifications always arrive.

    No row means the default: an email at once, no push.
    """

    class Email(models.TextChoices):
        INSTANT = "instant", "An email for each"
        DAILY = "daily", "One daily summary email"
        OFF = "off", "No email"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences"
    )
    kind = models.CharField(max_length=20, choices=Notification.Kind.choices)
    email = models.CharField(max_length=10, choices=Email.choices, default=Email.INSTANT)
    push = models.BooleanField(
        default=False, help_text="Also a push notice to the person's installed app (4.04)"
    )

    class Meta:
        ordering = ["user", "kind"]
        constraints = [models.UniqueConstraint(fields=["user", "kind"], name="notification_preference_once")]

    def __str__(self) -> str:
        return f"{self.user}: {self.kind} by email {self.email}"


class PushSubscription(models.Model):
    """One installed app (a browser on a phone or computer) that has agreed to receive push notices (item
    4.04). The push service named by the endpoint delivers them; the keys encrypt each notice for that browser
    alone (RFC 8291), so the service cannot read it. Removed when the person turns push off there, or when
    the service says the subscription has expired."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = EncryptedTextField(help_text="The browser's public key for this subscription")
    auth = EncryptedTextField(help_text="The browser's authentication secret, encrypted at rest")
    device = models.CharField(max_length=120, blank=True, help_text="Which browser and system, in words")
    created_at = models.DateTimeField(auto_now_add=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    failures = models.PositiveSmallIntegerField(default=0, help_text="Sends that failed in a row")

    class Meta:
        ordering = ["user", "-created_at"]

    def __str__(self) -> str:
        return f"Push to {self.user} ({self.device or 'a browser'})"
