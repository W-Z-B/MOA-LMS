"""Help requests (item 7.17): anyone signed in asks for help from the page they are on, and the course
administrators answer. The request keeps the page so whoever answers can open what the person was looking at.
"""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class HelpRequest(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Waiting for an answer"
        ANSWERED = "answered", "Answered"

    asked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    page = models.CharField(
        max_length=200,
        blank=True,
        help_text="The address in the web app the person asked from, e.g. /sites/4",
    )
    subject = models.CharField(max_length=160)
    message = models.TextField(help_text="Plain text, as the person wrote it")
    client_sent_at = models.DateTimeField(
        null=True, blank=True, help_text="When it was written on the phone, if it waited in the offline queue"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    answer = models.TextField(blank=True)
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return self.subject
