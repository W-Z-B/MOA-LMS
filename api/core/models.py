"""Shared base models used by every module."""

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Every business table carries creation and update stamps and the acting user."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )

    class Meta:
        abstract = True


class PublicHoliday(TimeStampedModel):
    """Guyana public holidays, seeded per year; used by leave and scheduling calculations."""

    date = models.DateField(unique=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["date"]

    def __str__(self) -> str:
        return f"{self.date:%d/%m/%Y} {self.name}"
