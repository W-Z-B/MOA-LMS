"""The shared content library (item 5.14): material and question banks shared across courses and departments.

A library item is a copy kept apart from any course: a page, a file, a link or a package (SCORM or H5P),
with whose material it is and how to credit it. It belongs to a department (an HRMS unit code) or, with no
department, to the whole School. Teaching staff anywhere browse the library and copy an item into a module
of a course they teach, as a draft; the copy is the course's own from then on.

Open educational resources from trusted sources (FAO, CABI and the like) come in the same way, as files,
links or packages, marked as open resources with their publisher and open licence.

Question banks are shared as department banks (quizzes.QuestionBank with a department code), which every
lecturer may already use; a SharedBank row gives such a bank its licence and where it came from.
"""

from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.models import TimeStampedModel
from core.uploads import _stored
from courses.models import ContentItem


def library_name(instance, filename: str) -> str:
    return _stored("library", filename)


class Licensed(models.Model):
    """Whose material it is, as for a course's items (item 2.19)."""

    licence = models.CharField(max_length=20, choices=ContentItem.Licence.choices)
    open_licence = models.CharField(max_length=10, choices=ContentItem.OpenLicence.choices, blank=True)
    source = models.TextField(blank=True, help_text="Where the material comes from and how to credit it")
    publisher = models.CharField(
        max_length=120, blank=True, help_text="Such as FAO or CABI, for open resources"
    )

    class Meta:
        abstract = True


class LibraryItem(Licensed, TimeStampedModel):
    # Lecture videos are not shared through the library: their copies and captions belong to a course.
    kind = models.CharField(
        max_length=10, choices=[c for c in ContentItem.Kind.choices if c[0] != ContentItem.Kind.VIDEO]
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    body = models.TextField(blank=True, help_text="A page's text as cleaned HTML (courses.richtext)")
    file = models.FileField(upload_to=library_name, blank=True)
    original_name = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    url = models.URLField(blank=True)
    package = models.JSONField(
        default=dict, blank=True, help_text="For a package: what the check found (standard, parts, sizes)"
    )
    department_code = models.CharField(
        max_length=20, blank=True, help_text="HRMS unit code of the department; empty for the whole School"
    )
    is_open_resource = models.BooleanField(default=False, help_text="An open educational resource")
    tags = ArrayField(models.CharField(max_length=40), default=list, blank=True)
    shared_from = models.ForeignKey(
        ContentItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="library_copies"
    )

    class Meta:
        ordering = ["title", "id"]

    def __str__(self) -> str:
        return self.title


class SharedBank(Licensed, TimeStampedModel):
    bank = models.OneToOneField("quizzes.QuestionBank", on_delete=models.CASCADE, related_name="shared")
    copied_from = models.ForeignKey(
        "quizzes.QuestionBank", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self) -> str:
        return f"Shared {self.bank}"
