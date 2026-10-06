"""Lecture video (items 4.06, 4.07; ADR 0015): put up once, kept as a low and a standard copy and a copy
with sound only, with a poster frame and captions. The files live in the LMS's own file store and count
against the site's storage allowance through ContentItem.file_size."""

from django.db import models

from core.models import TimeStampedModel
from core.uploads import _stored


def video_name(instance, filename: str) -> str:
    """upload_to for video and its copies: video/<year>/<month>/<random>.<ext>."""
    return _stored("video", filename)


class Video(TimeStampedModel):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting to be prepared"
        CONVERTING = "converting", "Being prepared"
        READY = "ready", "Ready"
        FAILED = "failed", "Could not be prepared"

    class Transcription(models.TextChoices):
        NONE = "none", "Not asked for"
        WAITING = "waiting", "Waiting"
        WORKING = "working", "Being written"
        DONE = "done", "Written"
        FAILED = "failed", "Could not be written"

    item = models.OneToOneField("courses.ContentItem", on_delete=models.CASCADE, related_name="video")
    original = models.FileField(
        upload_to=video_name, blank=True, help_text="As put up; removed once the copies are made"
    )
    original_name = models.CharField(max_length=255, blank=True)
    original_size = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.WAITING)
    failure = models.TextField(blank=True, help_text="Why it could not be prepared, in words")
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    poster = models.FileField(
        upload_to=video_name, blank=True, help_text="A still frame shown before playing"
    )
    poster_size = models.PositiveBigIntegerField(default=0)
    converted_at = models.DateTimeField(null=True, blank=True)
    transcription = models.CharField(max_length=10, choices=Transcription.choices, default=Transcription.NONE)
    transcription_failure = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"Video of {self.item}"

    def total_size(self) -> int:
        """Every byte the video keeps on the server: what the site's storage allowance counts."""
        kept = sum(r.size for r in self.renditions.all())
        return kept + self.poster_size + (self.original_size if self.original else 0)


class Rendition(models.Model):
    """One copy of a video, made for a kind of connection."""

    class Quality(models.TextChoices):
        LOW = "low", "Low (240p): least data"
        STANDARD = "standard", "Standard"
        AUDIO = "audio", "Sound only"

    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="renditions")
    quality = models.CharField(max_length=10, choices=Quality.choices)
    file = models.FileField(upload_to=video_name)
    size = models.PositiveBigIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    bitrate_kbps = models.PositiveIntegerField(
        null=True, blank=True, help_text="The whole copy, sound included"
    )

    class Meta:
        ordering = ["video", "quality"]
        constraints = [models.UniqueConstraint(fields=["video", "quality"], name="video_rendition_once")]

    def __str__(self) -> str:
        return f"{self.video} ({self.quality})"


class CaptionTrack(TimeStampedModel):
    """Captions in one language, kept as WebVTT text so they can be corrected in the browser."""

    class Source(models.TextChoices):
        UPLOADED = "uploaded", "Put up as a file"
        EDITED = "edited", "Written or corrected in the LMS"
        TRANSCRIBED = "transcribed", "Written by speech recognition on GSA's server"

    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="captions")
    language = models.CharField(max_length=12, default="en", help_text="A language tag: en, es, pt")
    label = models.CharField(max_length=60, default="English")
    text = models.TextField(help_text="WebVTT")
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.UPLOADED)

    class Meta:
        ordering = ["video", "language"]
        constraints = [
            models.UniqueConstraint(fields=["video", "language"], name="caption_once_per_language")
        ]

    def __str__(self) -> str:
        return f"{self.video}: {self.label} captions"
