"""Insight (phase 6 and item 3.11): what the SRMS says about a site, learning outcomes, and early alerts.

Course analytics, progress and the reports are worked out from records the LMS already keeps (item 1.20):
item completions, hand-ins, marks, quiz attempts and the audit log. Nothing here records more about what
people do. The early alerts (item 6.05, decision D5, ADR 0007) follow visible rules whose thresholds course
administrators set; each alert carries its evidence, and a person decides what, if anything, to do.
"""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class SiteProfile(models.Model):
    """What the SRMS says about a site's offering beyond the site itself: the course it is an offering of
    and the programmes it belongs to. Filled by the nightly site sync (integration.srms.sync_sites)."""

    site = models.OneToOneField("courses.CourseSite", on_delete=models.CASCADE, related_name="profile")
    course_code = models.CharField(max_length=20, blank=True, db_index=True)
    programme_codes = ArrayField(
        models.CharField(max_length=20),
        default=list,
        blank=True,
        help_text="Programmes the offering belongs to, when the SRMS sends them",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.site.code}: {self.course_code or 'course not known'}"


class Outcome(TimeStampedModel):
    """A learning outcome (item 3.11). Outcomes come from the SRMS course outline and are shared by every
    offering of the course; a lecturer may add the site's own only while the SRMS has none for the course."""

    class Source(models.TextChoices):
        SRMS = "srms", "From the SRMS course outline"
        LOCAL = "local", "Added on the site"

    source = models.CharField(max_length=10, choices=Source.choices)
    course_code = models.CharField(max_length=20, blank=True, help_text="SRMS outcomes: the course")
    site = models.ForeignKey(
        "courses.CourseSite",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="local_outcomes",
        help_text="Local outcomes: the site",
    )
    code = models.CharField(max_length=20)
    text = models.TextField()
    position = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(
        default=True, help_text="False once the SRMS no longer lists it; its links and evidence stay"
    )

    class Meta:
        ordering = ["position", "code", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(source="srms") & ~Q(course_code="") & Q(site__isnull=True))
                | (Q(source="local") & Q(site__isnull=False)),
                name="outcome_source_owner",
            ),
            models.UniqueConstraint(
                fields=["course_code", "code"], condition=Q(source="srms"), name="outcome_srms_code_once"
            ),
            models.UniqueConstraint(
                fields=["site", "code"], condition=Q(source="local"), name="outcome_local_code_once"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.text[:60]}"


class OutcomeLink(TimeStampedModel):
    """Evidence towards an outcome on one site: an assignment, a quiz question or a rubric criterion."""

    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="outcome_links")
    outcome = models.ForeignKey(Outcome, on_delete=models.CASCADE, related_name="links")
    assignment = models.ForeignKey(
        "assessments.Assignment", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    question = models.ForeignKey(
        "quizzes.Question", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    criterion = models.ForeignKey(
        "rubrics.RubricCriterion", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )

    class Meta:
        ordering = ["outcome", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(assignment__isnull=False) & Q(question__isnull=True) & Q(criterion__isnull=True))
                | (Q(assignment__isnull=True) & Q(question__isnull=False) & Q(criterion__isnull=True))
                | (Q(assignment__isnull=True) & Q(question__isnull=True) & Q(criterion__isnull=False)),
                name="outcome_link_one_target",
            ),
            models.UniqueConstraint(
                fields=["site", "outcome", "assignment"],
                condition=Q(assignment__isnull=False),
                name="outcome_link_assignment_once",
            ),
            models.UniqueConstraint(
                fields=["site", "outcome", "question"],
                condition=Q(question__isnull=False),
                name="outcome_link_question_once",
            ),
            models.UniqueConstraint(
                fields=["site", "outcome", "criterion"],
                condition=Q(criterion__isnull=False),
                name="outcome_link_criterion_once",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.outcome.code} on {self.site.code}"

    @property
    def kind(self) -> str:
        if self.assignment_id:
            return "assignment"
        return "question" if self.question_id else "criterion"


class AlertRule(TimeStampedModel):
    """One early-alert rule (item 6.05): what it looks for, and the threshold a course administrator set.

    The rules are visible to teaching staff and stated in the privacy notice. They never predict: each
    one counts something the LMS already holds and names it as the alert's evidence.
    """

    class Kind(models.TextChoices):
        MISSED_WORK = "missed_work", "Missed work"
        FALLING_MARKS = "falling_marks", "Falling marks"
        NO_VISITS = "no_visits", "No visits"

    kind = models.CharField(max_length=20, choices=Kind.choices, unique=True)
    threshold = models.PositiveSmallIntegerField(
        help_text="Missed work: pieces of work missed. Falling marks: percentage points fallen. "
        "No visits: days with nothing done on the course."
    )
    window_days = models.PositiveSmallIntegerField(
        default=28,
        help_text="Missed work: only work due in this many days counts. Falling marks: the latest mark "
        "must be this recent. Not used for no visits.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind"]
        constraints = [models.CheckConstraint(condition=Q(threshold__gt=0), name="alert_rule_threshold_set")]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} ({self.threshold})"

    def describe(self) -> str:
        """The rule in a sentence, as teaching staff and the privacy notice see it."""
        if self.kind == self.Kind.MISSED_WORK:
            return (
                f"{self.threshold} or more pieces of work missed (past their due date with nothing "
                f"handed in) in the last {self.window_days} days"
            )
        if self.kind == self.Kind.FALLING_MARKS:
            return (
                f"the two latest marks are, on average, {self.threshold} or more percentage points below the "
                f"student's earlier marks, the latest within the last {self.window_days} days"
            )
        return f"nothing done on the course for {self.threshold} days or more"


class Alert(TimeStampedModel):
    """A rule matched one student on one site. Shown to the site's teaching staff and course administrators
    with its evidence, never to the student as a label. A person acknowledges it, acts (usually by a
    message to the student) or dismisses it with a reason."""

    class State(models.TextChoices):
        OPEN = "open", "New"
        ACKNOWLEDGED = "acknowledged", "Seen"
        ACTED = "acted", "Acted on"
        DISMISSED = "dismissed", "Dismissed"

    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="alerts")
    student = models.ForeignKey("people.PersonRef", on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=20, choices=AlertRule.Kind.choices)
    summary = models.CharField(max_length=300)
    evidence = models.JSONField(default=list, help_text='[{"what": "...", "when": "ISO date or null"}]')
    evidence_key = models.CharField(
        max_length=64, help_text="What the evidence is about; the same evidence never raises a second alert"
    )
    raised_at = models.DateTimeField()
    state = models.CharField(max_length=15, choices=State.choices, default=State.OPEN)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    handled_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, help_text="What was done, or why it was dismissed")
    conversation = models.ForeignKey(
        "messaging.Conversation", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-raised_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["site", "student", "kind", "evidence_key"], name="alert_evidence_once"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.student} on {self.site.code}"

    @property
    def is_open(self) -> bool:
        return self.state in (self.State.OPEN, self.State.ACKNOWLEDGED)
