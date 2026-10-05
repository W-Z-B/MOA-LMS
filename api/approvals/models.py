"""Stand-ins (ported from the HRMS approvals, its item 1.33): while someone is away, a colleague decides what
is sent to them."""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from core.models import TimeStampedModel


class Delegation(TimeStampedModel):
    """From one day to another, the delegate may decide whatever is sent to the delegator, as they could."""

    delegator = models.ForeignKey(
        "people.PersonRef", on_delete=models.CASCADE, related_name="delegations_given"
    )
    delegate = models.ForeignKey(
        "people.PersonRef", on_delete=models.CASCADE, related_name="delegations_held"
    )
    starts = models.DateField()
    ends = models.DateField()
    reason = models.CharField(max_length=160, blank=True, help_text="Such as annual leave, or a course")
    cancelled = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-starts", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends__gte=F("starts")), name="delegation_ends_after_it_starts"
            ),
            models.CheckConstraint(condition=~Q(delegate=F("delegator")), name="delegation_to_someone_else"),
        ]

    def __str__(self) -> str:
        return f"{self.delegate} for {self.delegator}, {self.starts:%d/%m/%Y} to {self.ends:%d/%m/%Y}"
