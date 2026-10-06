"""Peer review (item 4.13; Moodle's workshop is the reference).

An assignment may ask students to review each other's work. After the due date each student who handed in
is given a number of other students' work, without names, to assess against the assignment's rubric with a
comment, and, when the lecturer asks for it, to assess their own. The lecturer moderates: a review can be
left out, the peer mark can be set by hand, and the reviews reach the students only when released. The peer
mark may count as a share of the mark.
"""

from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class PeerReviewSetup(TimeStampedModel):
    assignment = models.OneToOneField(
        "assessments.Assignment", on_delete=models.CASCADE, related_name="peer_review"
    )
    reviews_each = models.PositiveSmallIntegerField(
        default=3, help_text="How many other students' work each student reviews"
    )
    reviews_due_at = models.DateTimeField(help_text="Reviews are taken until then")
    self_assessment = models.BooleanField(
        default=False, help_text="Each student also assesses their own work against the rubric"
    )
    peer_weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Percent of the mark that comes from the peer mark; 0 keeps peer review as feedback only",
    )
    allocated_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(
        null=True, blank=True, help_text="When the moderated reviews were shown to the students reviewed"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(peer_weight__gte=0) & Q(peer_weight__lte=100), name="peer_weight_percentage"
            ),
            models.CheckConstraint(condition=Q(reviews_each__gte=1), name="peer_reviews_each_positive"),
        ]

    def __str__(self) -> str:
        return f"Peer review of {self.assignment}"


class PeerReview(TimeStampedModel):
    """One student's review of one piece of work (their own, for a self-assessment)."""

    class Moderation(models.TextChoices):
        COUNTS = "counts", "Counts"
        LEFT_OUT = "left_out", "Left out by the lecturer"

    setup = models.ForeignKey(PeerReviewSetup, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey("people.PersonRef", on_delete=models.CASCADE, related_name="peer_reviews")
    submission = models.ForeignKey(
        "assessments.Submission", on_delete=models.CASCADE, related_name="peer_reviews"
    )
    position = models.PositiveSmallIntegerField(default=1, help_text="Work 1, 2 ... in the reviewer's list")
    is_self = models.BooleanField(default=False)
    scores = models.JSONField(default=list, blank=True, help_text="Rubric scores, as a marker's are kept")
    mark = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, help_text="Scaled to the assignment's maximum"
    )
    comment = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    moderation = models.CharField(max_length=10, choices=Moderation.choices, default=Moderation.COUNTS)
    moderation_note = models.CharField(max_length=300, blank=True, help_text="Why it was left out")
    moderated_by = models.ForeignKey(
        "people.PersonRef", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["setup", "reviewer", "position"]
        constraints = [
            models.UniqueConstraint(fields=["reviewer", "submission"], name="peer_review_once"),
        ]

    def __str__(self) -> str:
        return f"{self.reviewer} reviews {self.submission}"


class PeerOutcome(models.Model):
    """The peer mark of one piece of work, any override, and the mark it was folded into."""

    submission = models.OneToOneField(
        "assessments.Submission", on_delete=models.CASCADE, related_name="peer_outcome"
    )
    override = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, help_text="Set by the lecturer"
    )
    override_note = models.CharField(max_length=300, blank=True)
    staff_mark = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True, help_text="The marker's mark when folded in"
    )
    combined = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Peer outcome of {self.submission}"
