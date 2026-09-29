"""Assignments, submissions and marks. Coursework totals are returned to the SRMS, which owns results."""

from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class Assignment(TimeStampedModel):
    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="assignments")
    title = models.CharField(max_length=160)
    instructions = models.TextField(blank=True)
    opens_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField()
    max_mark = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=1, help_text="Relative weight within the site's coursework"
    )
    allow_late = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["due_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(max_mark__gt=0) & Q(weight__gt=0), name="assignment_positive_values"
            )
        ]

    def __str__(self) -> str:
        return f"{self.site.code}: {self.title}"


class Submission(TimeStampedModel):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey("people.PersonRef", on_delete=models.PROTECT, related_name="submissions")
    text = models.TextField(blank=True)
    file = models.FileField(upload_to="submissions/%Y/%m/", blank=True)
    submitted_at = models.DateTimeField()
    is_late = models.BooleanField(default=False)

    class Meta:
        unique_together = [("assignment", "student")]
        ordering = ["assignment", "student"]

    def __str__(self) -> str:
        return f"{self.student} for {self.assignment.title}"


class Mark(TimeStampedModel):
    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, related_name="mark")
    mark = models.DecimalField(max_digits=6, decimal_places=2)
    feedback = models.TextField(blank=True)
    marked_by = models.ForeignKey("people.PersonRef", null=True, blank=True, on_delete=models.SET_NULL)
    is_released = models.BooleanField(default=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(mark__gte=0), name="mark_not_negative")]

    def __str__(self) -> str:
        return f"{self.submission}: {self.mark}"
