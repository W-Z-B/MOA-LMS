"""The term calendar and the archives of course sites whose term is long closed (item 7.12)."""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Term(TimeStampedModel):
    """One term of the academic calendar, named by the code the SRMS gives its offerings ("2026-27-S1").

    Sites are matched to their term by CourseSite.term_code. Students hand work in until the end of the close
    date and the grace that follows it; the sites are then kept read-only for appeals and, once the
    retention schedule's period for course sites has passed, archived.
    """

    class Source(models.TextChoices):
        SRMS = "srms", "From the SRMS"
        LOCAL = "local", "Entered in the LMS"

    code = models.CharField(max_length=16, unique=True, help_text="The SRMS term code, e.g. 2026-27-S1")
    name = models.CharField(max_length=60)
    starts_on = models.DateField()
    ends_on = models.DateField(help_text="Last day of teaching")
    closes_on = models.DateField(help_text="Last day on which work is handed in; sites close after it")
    grace_days = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Days after the close date still accepted; empty: TERM_GRACE_DAYS"
    )
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.LOCAL)
    closed_at = models.DateTimeField(null=True, blank=True, help_text="When the nightly job closed its sites")
    archived_at = models.DateTimeField(null=True, blank=True, help_text="When every site was archived")

    class Meta:
        ordering = ["-starts_on", "code"]

    def __str__(self) -> str:
        return self.code


def archive_name(instance, filename: str) -> str:
    return f"archives/{instance.term_code}/{filename}"


class SiteArchive(models.Model):
    """The read-only export of a course site, kept once its term is archived. Nothing is deleted by archiving:
    records go only through the retention schedule's disposal runs (privacy.retention)."""

    site = models.OneToOneField("courses.CourseSite", on_delete=models.CASCADE, related_name="archive")
    term_code = models.CharField(max_length=16)
    file = models.FileField(upload_to=archive_name, max_length=255)
    size = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    records = models.PositiveIntegerField(help_text="Rows exported, all kinds together")
    files = models.PositiveIntegerField(help_text="Stored files copied into the export")
    made_at = models.DateTimeField(auto_now_add=True)
    made_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-made_at"]

    def __str__(self) -> str:
        return f"Archive of {self.site_id} ({self.term_code})"
