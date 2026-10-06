"""Course sites, memberships, content and announcements."""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel
from core.uploads import content_name


class CourseSite(TimeStampedModel):
    class Source(models.TextChoices):
        SRMS = "srms", "Course offering from the SRMS"
        LOCAL = "local", "Created in the LMS"

    class Kind(models.TextChoices):
        ACADEMIC = "academic", "Academic course"
        STAFF_DEVELOPMENT = "staff_development", "Staff development"
        OPEN = "open", "Open short course for farmers and extension officers (item 5.07)"

    code = models.CharField(max_length=40, unique=True, help_text="SRMS offering code for academic sites")
    title = models.CharField(max_length=200)
    term_code = models.CharField(max_length=16, blank=True)
    campus_code = models.CharField(max_length=10, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.LOCAL)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.ACADEMIC)
    description = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    coursework_weight = models.DecimalField(max_digits=5, decimal_places=2, default=40)
    storage_allowance_mb = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Storage for this site's files in megabytes; empty means SITE_STORAGE_ALLOWANCE_MB",
    )

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


class SiteGroup(TimeStampedModel):
    """A named group of a site's members, used to release content to some of the class (item 2.16).

    Deliberately minimal: group work and group assignments (item 4.12) build on it.
    """

    site = models.ForeignKey(CourseSite, on_delete=models.CASCADE, related_name="groups")
    name = models.CharField(max_length=80)
    members = models.ManyToManyField(Membership, blank=True, related_name="groups")

    class Meta:
        ordering = ["name", "id"]
        unique_together = [("site", "name")]
        verbose_name = "group"

    def __str__(self) -> str:
        return f"{self.site.code}: {self.name}"


class ReleaseConditions(models.Model):
    """When a module or an item is shown to students (item 2.16). Every condition set must be met.

    Teaching staff always see everything, with the conditions described.
    """

    available_from = models.DateTimeField(null=True, blank=True, help_text="Hidden from students until then")
    requires_item = models.ForeignKey(
        "courses.ContentItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Hidden from a student until they have completed this item",
    )
    groups = models.ManyToManyField(
        SiteGroup, blank=True, related_name="+", help_text="Shown only to members of these groups"
    )

    class Meta:
        abstract = True


class Module(ReleaseConditions, TimeStampedModel):
    site = models.ForeignKey(CourseSite, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=160)
    position = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.site.code} / {self.title}"


class ContentItem(ReleaseConditions, TimeStampedModel):
    class Kind(models.TextChoices):
        PAGE = "page", "Page"
        FILE = "file", "File"
        LINK = "link", "Link"
        PACKAGE = "package", "SCORM or H5P package"
        # Lecture video (item 4.06): its copies and captions are a video.Video; file_size counts them all.
        VIDEO = "video", "Video"

    class Licence(models.TextChoices):
        GSA_OWN = "gsa_own", "GSA's own material"
        OPEN_LICENCE = "open_licence", "Under an open licence"
        FAIR_DEALING = "fair_dealing", "Used under fair dealing for research or private study"
        PERMISSION_HELD = "permission_held", "Used with the owner's permission"
        UNKNOWN = "unknown", "Not yet known"

    class OpenLicence(models.TextChoices):
        CC_BY = "cc_by", "CC BY"
        CC_BY_SA = "cc_by_sa", "CC BY-SA"
        CC_BY_NC = "cc_by_nc", "CC BY-NC"
        CC0 = "cc0", "CC0"
        OTHER = "other", "Another open licence"

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="items")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PAGE)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True, help_text="A page's text as cleaned HTML (courses.richtext)")
    file = models.FileField(upload_to=content_name, blank=True)
    original_name = models.CharField(
        max_length=255, blank=True, help_text="The name the file had when it was put up; used for downloads"
    )
    file_size = models.PositiveBigIntegerField(default=0, help_text="Bytes; counted against the allowance")
    url = models.URLField(blank=True)
    position = models.PositiveSmallIntegerField(default=1)
    is_published = models.BooleanField(default=True)
    licence = models.CharField(max_length=20, choices=Licence.choices, default=Licence.GSA_OWN)
    open_licence = models.CharField(
        max_length=10, choices=OpenLicence.choices, blank=True, help_text="Which open licence"
    )
    source = models.TextField(blank=True, help_text="Where the material comes from and how to credit it")
    under_review = models.BooleanField(
        default=False, help_text="Hidden from students while a takedown request is reviewed"
    )

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.title

    @property
    def site(self) -> CourseSite:
        return self.module.site


class ItemCompletion(models.Model):
    """A person has viewed or completed an item: opened a page, downloaded a file, or marked it done."""

    class How(models.TextChoices):
        VIEWED = "viewed", "Viewed"
        DOWNLOADED = "downloaded", "Downloaded"
        MARKED = "marked", "Marked as complete"
        PACKAGE = "package", "Completed in the package"

    person = models.ForeignKey("people.PersonRef", on_delete=models.CASCADE, related_name="item_completions")
    item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="completions")
    completed_at = models.DateTimeField()
    how = models.CharField(max_length=12, choices=How.choices)

    class Meta:
        unique_together = [("person", "item")]

    def __str__(self) -> str:
        return f"{self.person} completed {self.item}"


class TakedownRequest(TimeStampedModel):
    """Someone says an item should not be there (item 2.19). The item is hidden from students until a
    course administrator decides."""

    class Status(models.TextChoices):
        OPEN = "open", "Waiting for review"
        WITHDRAWN = "withdrawn", "Item withdrawn"
        RESTORED = "restored", "Item restored"

    item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="takedowns")
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Takedown of {self.item} ({self.status})"


class SiteTemplate(TimeStampedModel):
    """A standard layout of modules and draft pages given to new, empty sites (item 2.17).

    structure: {"modules": [{"title": "...", "items": [{"kind": "page", "title": "...", "body": "..."}]}]}
    """

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    structure = models.JSONField(default=dict)
    is_default = models.BooleanField(default=False, help_text="Applied to every new site")

    class Meta:
        ordering = ["-is_default", "name"]

    def __str__(self) -> str:
        return self.name


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
    """A person completed a site. For staff-development sites this is reported to the HRMS training record.

    One row per person and site: a renewal (item 5.05) moves it to the new date and expiry, and is reported
    to the HRMS again under a reference of its own. Each certificate issued keeps the earlier dates.
    """

    class How(models.TextChoices):
        RULES = "rules", "The site's completion rules were met"
        RECORDED = "recorded", "Recorded by a course administrator"

    site = models.ForeignKey(CourseSite, on_delete=models.CASCADE, related_name="completions")
    person = models.ForeignKey("people.PersonRef", on_delete=models.CASCADE, related_name="completions")
    completed_on = models.DateField()
    expires_on = models.DateField(null=True, blank=True, help_text="When the training must be renewed")
    how = models.CharField(max_length=10, choices=How.choices, default=How.RECORDED)
    certificate = models.CharField(max_length=160, blank=True)
    external_ref = models.CharField(
        max_length=120, blank=True, help_text="The reference the HRMS keeps it under; set when first reported"
    )
    reported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("site", "person")]

    def __str__(self) -> str:
        return f"{self.person} completed {self.site.code}"


# Groupings and self-sign-up (item 4.12) live in their own module; imported here so Django registers them.
from courses.groups import Grouping, GroupSignUp  # noqa: E402, F401
