"""Rubrics and marking guides (items 3.09, 3.10). Moodle's advanced grading is the reference.

A rubric has criteria, each with levels: a level has points and a description. A scored rubric fills the
mark from the levels chosen, scaled to the assignment's maximum; a descriptive rubric records the levels
as feedback only and the marker gives the mark. A marking guide has criteria with a maximum and a comment
in place of levels; the marker gives points up to each maximum, and those fill the mark.

A rubric belongs to one course site, or, with no site, to the GSA library kept by course administrators.
A library rubric is copied to a site before an assignment uses it, so the library can change without
changing how past work was marked.
"""

from decimal import Decimal

from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class Rubric(TimeStampedModel):
    class Kind(models.TextChoices):
        SCORED = "scored", "Rubric with points"
        DESCRIPTIVE = "descriptive", "Rubric with descriptions only"
        GUIDE = "guide", "Marking guide"

    site = models.ForeignKey(
        "courses.CourseSite", null=True, blank=True, on_delete=models.CASCADE, related_name="rubrics"
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.SCORED)
    copied_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="copies"
    )

    class Meta:
        ordering = ["title", "id"]

    def __str__(self) -> str:
        return f"{self.site.code if self.site_id else 'GSA library'}: {self.title}"

    @property
    def in_library(self) -> bool:
        return self.site_id is None

    def max_points(self) -> Decimal:
        """The most the rubric can give: the best level of each criterion, or each guide maximum."""
        total = Decimal(0)
        for criterion in self.criteria.all():
            if self.kind == self.Kind.GUIDE:
                total += criterion.max_points or 0
            else:
                total += max((level.points for level in criterion.levels.all()), default=Decimal(0))
        return total


class RubricCriterion(models.Model):
    rubric = models.ForeignKey(Rubric, on_delete=models.CASCADE, related_name="criteria")
    position = models.PositiveSmallIntegerField(default=1)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text="For a marking guide: what the marker looks for")
    max_points = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, help_text="Marking guides only"
    )

    class Meta:
        ordering = ["rubric", "position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(max_points__isnull=True) | Q(max_points__gt=0),
                name="rubric_criterion_max_positive",
            )
        ]

    def __str__(self) -> str:
        return self.title


class RubricLevel(models.Model):
    criterion = models.ForeignKey(RubricCriterion, on_delete=models.CASCADE, related_name="levels")
    position = models.PositiveSmallIntegerField(default=1)
    points = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    description = models.TextField()

    class Meta:
        ordering = ["criterion", "position", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(points__gte=0), name="rubric_level_points_not_negative")
        ]

    def __str__(self) -> str:
        return f"{self.criterion}: {self.points}"
