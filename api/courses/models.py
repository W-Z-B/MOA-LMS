"""Course sites, memberships, content and announcements."""

from django.db import models

from core.models import TimeStampedModel


class CourseSite(TimeStampedModel):
    class Source(models.TextChoices):
        SRMS = "srms", "Course offering from the SRMS"
        LOCAL = "local", "Created in the LMS"

    class Kind(models.TextChoices):
        ACADEMIC = "academic", "Academic course"
        STAFF_DEVELOPMENT = "staff_development", "Staff development"

    code = models.CharField(max_length=40, unique=True, help_text="SRMS offering code for academic sites")
    title = models.CharField(max_length=200)
    term_code = models.CharField(max_length=16, blank=True)
    campus_code = models.CharField(max_length=10, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.LOCAL)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.ACADEMIC)
    description = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    coursework_weight = models.DecimalField(max_digits=5, decimal_places=2, default=40)

    class Meta:
        ordering = ["-term_code", "code"]

    def __str__(self) -> str:
        return f"{self.code} {self.title}"


class Membership(TimeStampedModel):
    class SiteRole(models.TextChoices):
        STUDENT = "student", "Student"
        LECTURER = "lecturer", "Lecturer"
        ASSISTANT = "assistant", "Teaching assistant"

    site = models.ForeignKey(CourseSite, on_delete=models.CASCADE, related_name="memberships")
    person = models.ForeignKey("people.PersonRef", on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=SiteRole.choices, default=SiteRole.STUDENT)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("site", "person")]

    def __str__(self) -> str:
        return f"{self.person} in {self.site.code} as {self.role}"


class Module(TimeStampedModel):
    site = models.ForeignKey(CourseSite, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=160)
    position = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.site.code} / {self.title}"


class ContentItem(TimeStampedModel):
    class Kind(models.TextChoices):
        PAGE = "page", "Page"
        FILE = "file", "File"
        LINK = "link", "Link"

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="items")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PAGE)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    file = models.FileField(upload_to="content/%Y/%m/", blank=True)
    url = models.URLField(blank=True)
    position = models.PositiveSmallIntegerField(default=1)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.title


class Announcement(TimeStampedModel):
    site = models.ForeignKey(CourseSite, on_delete=models.CASCADE, related_name="announcements")
    title = models.CharField(max_length=160)
    body = models.TextField()
    author = models.ForeignKey("people.PersonRef", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.site.code}: {self.title}"


class Completion(TimeStampedModel):
    """A person completed a site. For staff-development sites this is reported to the HRMS training record."""

    site = models.ForeignKey(CourseSite, on_delete=models.CASCADE, related_name="completions")
    person = models.ForeignKey("people.PersonRef", on_delete=models.CASCADE, related_name="completions")
    completed_on = models.DateField()
    certificate = models.CharField(max_length=160, blank=True)
    reported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("site", "person")]

    def __str__(self) -> str:
        return f"{self.person} completed {self.site.code}"
