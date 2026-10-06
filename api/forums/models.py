"""Discussion forums (items 4.08 to 4.10): forums on a site or a module, threads, replies, subscriptions,
moderation with reports, the conduct statement, and participation marks for graded discussion."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class Forum(TimeStampedModel):
    class Type(models.TextChoices):
        GENERAL = "general", "General discussion"
        QUESTION = "question", "Question and answer: students post before they see others' replies"
        GRADED = "graded", "Graded discussion"

    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="forums")
    module = models.ForeignKey(
        "courses.Module",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="forums",
        help_text="Empty for a forum of the whole site",
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, help_text="Cleaned HTML (courses.richtext)")
    forum_type = models.CharField(max_length=10, choices=Type.choices, default=Type.GENERAL)
    is_published = models.BooleanField(default=True)
    groups = models.ManyToManyField(
        "courses.SiteGroup", blank=True, related_name="+", help_text="Shown only to members of these groups"
    )
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Relative weight within the site's coursework (graded forums only); 0 when it does not "
        "count",
    )
    max_mark = models.DecimalField(max_digits=6, decimal_places=2, default=10)
    # The rubric a participation mark is given against (item 4.10): one of the site's rubrics (3.09).
    rubric = models.ForeignKey(
        "rubrics.Rubric",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Rubric to mark against, if any",
    )
    grade_category = models.ForeignKey(
        "assessments.GradeCategory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="forums",
        help_text="The gradebook category it counts in (item 2.28)",
    )

    class Meta:
        ordering = ["site", "title", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(weight__gte=0), name="forum_weight_not_negative"),
            models.CheckConstraint(condition=Q(max_mark__gt=0), name="forum_max_mark_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.site.code}: {self.title}"


class Thread(TimeStampedModel):
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE, related_name="threads")
    title = models.CharField(max_length=200)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    is_pinned = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False, help_text="No new replies while locked")
    last_post_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-is_pinned", "-last_post_at", "-id"]

    def __str__(self) -> str:
        return self.title


class Post(TimeStampedModel):
    """The opening post of a thread (no parent) or a reply to another post of the same thread."""

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="posts")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    body = models.TextField(help_text="Cleaned HTML (courses.richtext)")
    edited_at = models.DateTimeField(null=True, blank=True)
    is_hidden = models.BooleanField(
        default=False, help_text="Hidden from students while a report by teaching staff is reviewed"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    delete_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"Post {self.pk} in {self.thread}"

    @property
    def site(self):
        return self.thread.forum.site


class Subscription(models.Model):
    """Notices of new posts: to a whole forum, or to one thread."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    forum = models.ForeignKey(Forum, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    thread = models.ForeignKey(Thread, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(forum__isnull=False, thread__isnull=True)
                | Q(forum__isnull=True, thread__isnull=False),
                name="subscription_to_forum_or_thread",
            ),
            models.UniqueConstraint(fields=["user", "forum"], name="subscription_once_per_forum"),
            models.UniqueConstraint(fields=["user", "thread"], name="subscription_once_per_thread"),
        ]


class PostReport(TimeStampedModel):
    """Someone says a post breaks the conduct statement (item 4.09). A report by the site's teaching staff or
    a course administrator hides the post at once; a student's report waits for review, as for takedowns."""

    class Status(models.TextChoices):
        OPEN = "open", "Waiting for review"
        REMOVED = "removed", "Post removed"
        RESTORED = "restored", "Post kept"

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reports")
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    reason = models.TextField(max_length=1000)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Report of post {self.post_id} ({self.status})"


class ConductStatement(models.Model):
    """One version of the online conduct statement. A published version never changes; a new version must
    be accepted again before the person next posts or sends a message."""

    version = models.PositiveIntegerField(unique=True)
    body = models.TextField(help_text="Plain text; a blank line starts a new paragraph")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    published_at = models.DateTimeField(null=True, blank=True, help_text="Empty while it is a draft")

    class Meta:
        ordering = ["-version"]

    def __str__(self) -> str:
        return f"Conduct statement {self.version}{'' if self.published_at else ' (draft)'}"


class ConductAcceptance(models.Model):
    statement = models.ForeignKey(ConductStatement, on_delete=models.PROTECT, related_name="acceptances")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["statement", "user"], name="conduct_accepted_once")]

    def __str__(self) -> str:
        return f"{self.user} accepted conduct statement {self.statement.version}"


class ParticipationMark(TimeStampedModel):
    """A student's mark for their part in a graded forum, given by teaching staff (item 4.10)."""

    forum = models.ForeignKey(Forum, on_delete=models.CASCADE, related_name="marks")
    student = models.ForeignKey("people.PersonRef", on_delete=models.CASCADE, related_name="forum_marks")
    mark = models.DecimalField(max_digits=6, decimal_places=2)
    feedback = models.TextField(blank=True)
    rubric = models.ForeignKey(
        "rubrics.Rubric",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Rubric used",
    )
    is_released = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["forum", "student"], name="participation_mark_once"),
            models.CheckConstraint(condition=Q(mark__gte=0), name="participation_mark_not_negative"),
        ]

    def __str__(self) -> str:
        return f"{self.student} in {self.forum}: {self.mark}"
