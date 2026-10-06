"""The similarity check (item 3.20; decision D4, ADR 0006 and ADR 0021).

Each submission's latest hand-in is read into words, and a sample of fingerprints of its five-word runs is
kept so later work can be compared with it. Everything here is derived from the submission and goes with
it: deleting a submission deletes its document, its fingerprints and every match that names it.

The report is for teaching staff only. It is evidence for a person to weigh, never a verdict.
"""

from django.db import models

from core.models import TimeStampedModel


class SimilarityDocument(TimeStampedModel):
    """The words of one submission's latest hand-in, as compared, and the outcome of its check."""

    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting to be checked"
        DONE = "done", "Checked"
        NO_TEXT = "no_text", "No text could be read"
        FAILED = "failed", "The check could not be finished"

    submission = models.OneToOneField(
        "assessments.Submission", on_delete=models.CASCADE, related_name="similarity"
    )
    attempt_number = models.PositiveSmallIntegerField(help_text="The hand-in that was read")
    words = models.TextField(
        blank=True,
        help_text="The words compared, apart by single spaces: quotations and the instructions left out",
    )
    word_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    overall_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Share of the words found elsewhere"
    )
    notes = models.JSONField(
        default=list, blank=True, help_text="What could not be read, said in words, one note a line"
    )
    checked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Similarity of {self.submission}"


class Fingerprint(models.Model):
    """One kept fingerprint of a document: the hash of a five-word run and where the run starts.

    A btree index on the hash finds every earlier document that shares a run, whatever the number of
    documents, so a new hand-in is compared with every GSA submission without reading them all.
    """

    document = models.ForeignKey(SimilarityDocument, on_delete=models.CASCADE, related_name="fingerprints")
    hash = models.BigIntegerField(db_index=True)
    position = models.PositiveIntegerField()

    class Meta:
        indexes = [models.Index(fields=["document", "hash"], name="fingerprint_document_hash")]

    def __str__(self) -> str:
        return f"{self.hash} at {self.position}"


class SimilarityMatch(models.Model):
    """What one document shares with another: the share of its words, and the passages side by side.

    Kept for both documents of a pair, each from its own side, so an earlier submission's report shows a
    later one that copies it.
    """

    document = models.ForeignKey(SimilarityDocument, on_delete=models.CASCADE, related_name="matches")
    other = models.ForeignKey(SimilarityDocument, on_delete=models.CASCADE, related_name="+")
    shared_words = models.PositiveIntegerField()
    percent = models.DecimalField(max_digits=5, decimal_places=2)
    ranges = models.JSONField(default=list, help_text="[[start, end], ...] word ranges of this document")
    passages = models.JSONField(
        default=list, help_text='[{"mine": "...", "theirs": "...", "words": 14}] longest first'
    )
    found_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["document", "-percent", "id"]
        constraints = [
            models.UniqueConstraint(fields=["document", "other"], name="similarity_match_once"),
        ]

    def __str__(self) -> str:
        return f"{self.document} shares {self.percent}% with {self.other_id}"
