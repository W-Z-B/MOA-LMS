"""AI assistance within decision D5 (items 6.11, 6.12, ADR 0007).

Each course site has its own switches, off until its teaching staff turn them on, and only when GSA has
switched AI on for the whole LMS (AI_ENABLED). An Exchange records that the model was asked something:
for a lecturer's draft it keeps the draft, so that saving it can be marked as AI-drafted in the audit log;
for the student study helper it keeps neither the question nor the answer, only when it was asked, whether
it was answered and from which items. Exchanges go after the period of the retention rule "ai-exchanges"
(privacy.retention), as the activity logs do.
"""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.models import TimeStampedModel


class SiteSwitch(TimeStampedModel):
    site = models.OneToOneField("courses.CourseSite", on_delete=models.CASCADE, related_name="ai_switch")
    drafts = models.BooleanField(default=False, help_text="Teaching staff may ask for drafts")
    study_helper = models.BooleanField(default=False, help_text="Students may use the study helper")

    def __str__(self) -> str:
        return f"AI on {self.site.code}"


class Exchange(models.Model):
    class Kind(models.TextChoices):
        QUESTIONS = "questions", "Questions drafted from material"
        RUBRIC = "rubric", "Rubric wording drafted"
        ALT_TEXT = "alt_text", "Alternative text suggested"
        HELPER = "helper", "Study helper question"

    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    source = models.ForeignKey(
        "courses.ContentItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    output = models.JSONField(
        null=True, blank=True, help_text="A lecturer's draft; never kept for the helper"
    )
    answered = models.BooleanField(default=False)
    sources = ArrayField(models.BigIntegerField(), default=list, blank=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} on {self.site_id} at {self.at:%Y-%m-%d %H:%M}"
