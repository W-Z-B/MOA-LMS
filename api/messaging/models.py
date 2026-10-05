"""Messages (item 4.11): conversations between a student and the teaching staff of a site, and notices from
teaching staff to a group or to the whole site. Private messages between students are off unless GSA asks
for them (MESSAGING_STUDENT_TO_STUDENT)."""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Conversation(TimeStampedModel):
    class Audience(models.TextChoices):
        DIRECT = "direct", "Between a student and teaching staff"
        GROUP = "group", "Teaching staff to a group"
        SITE = "site", "Teaching staff to the whole site"

    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="conversations")
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.DIRECT)
    subject = models.CharField(max_length=200)
    group = models.ForeignKey(
        "courses.SiteGroup", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_message_at", "-id"]

    def __str__(self) -> str:
        return self.subject


class Participant(models.Model):
    """Who is in a conversation, and up to when they have read it (the read receipt)."""

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    may_send = models.BooleanField(
        default=True, help_text="False for students receiving a group or site notice"
    )
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "user"], name="participant_once")]

    def __str__(self) -> str:
        return f"{self.user} in {self.conversation}"


class Message(TimeStampedModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    body = models.TextField(help_text="Cleaned HTML (courses.richtext)")
    client_sent_at = models.DateTimeField(
        null=True, blank=True, help_text="When it was written on the phone, if it waited in the offline queue"
    )

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"Message {self.pk} in {self.conversation}"
