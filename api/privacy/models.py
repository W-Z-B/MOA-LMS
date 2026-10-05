"""Privacy under the Data Protection Act 2023: the notice each person reads and acknowledges, requests to
correct what the LMS holds about them (item 1.18), the retention schedule with disposal approved by a second
person, and the breach register (item 1.19)."""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class PrivacyNotice(models.Model):
    """One version of the privacy notice. A draft can be edited; a published version never changes, so
    every acknowledgement points at exactly the words that were read."""

    version = models.PositiveIntegerField(unique=True)
    title = models.CharField(max_length=200)
    body = models.TextField(help_text="Plain text; a blank line starts a new paragraph")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    published_at = models.DateTimeField(null=True, blank=True, help_text="Empty while it is a draft")
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-version"]

    def __str__(self) -> str:
        return f"Privacy notice {self.version}{'' if self.published_at else ' (draft)'}"


class NoticeAcknowledgement(models.Model):
    """That a person read a version of the notice, and when."""

    notice = models.ForeignKey(PrivacyNotice, on_delete=models.PROTECT, related_name="acknowledgements")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    at = models.DateTimeField(auto_now_add=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-at"]
        constraints = [
            models.UniqueConstraint(fields=["notice", "user"], name="one_acknowledgement_per_notice")
        ]

    def __str__(self) -> str:
        return f"{self.user} read notice {self.notice.version}"


class CorrectionRequest(TimeStampedModel):
    """A person says something held about them is wrong. A course administrator corrects it, or says why not.

    Names, numbers and class lists come from the HRMS and the SRMS: those are corrected there, and the
    answer says so; the LMS corrects what it owns (memberships made here, submissions, marks, completions).
    """

    class Subject(models.TextChoices):
        PERSONAL = "personal", "Name, number or email"
        MEMBERSHIP = "membership", "Courses I belong to"
        SUBMISSION = "submission", "My submissions"
        MARK = "mark", "My marks or feedback"
        COMPLETION = "completion", "Courses completed"
        ACCOUNT = "account", "My account or roles"
        OTHER = "other", "Something else"

    class State(models.TextChoices):
        OPEN = "open", "With a course administrator"
        CORRECTED = "corrected", "Corrected"
        DECLINED = "declined", "Not changed"

    person = models.ForeignKey(
        "people.PersonRef", on_delete=models.CASCADE, related_name="correction_requests"
    )
    subject = models.CharField(max_length=20, choices=Subject.choices)
    wrong = models.TextField(max_length=1000, help_text="What is wrong")
    should_be = models.TextField(max_length=1000, help_text="What it should say")
    state = models.CharField(max_length=12, choices=State.choices, default=State.OPEN)
    due_by = models.DateField(help_text="When it should have been answered (PRIVACY_RESPONSE_DAYS after)")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(max_length=1000, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Correction {self.id} for {self.person}: {self.get_state_display()}"


class RetentionRule(models.Model):
    """How long one kind of record is kept, and what happens then (item 1.19).

    The system knows how to find and dispose of each kind (privacy.retention). The periods start as the
    proposals in the impact assessment, to be confirmed by GSA; the schedule shows which are confirmed.
    """

    class Action(models.TextChoices):
        DELETE = "delete", "Delete"
        REVIEW = "review", "Reviewed by GSA; the system removes nothing"

    code = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    keep_months = models.PositiveIntegerField(
        null=True, blank=True, help_text="Empty when each record carries its own date"
    )
    counted_from = models.CharField(max_length=160, help_text="What the period is counted from, in words")
    action = models.CharField(max_length=12, choices=Action.choices, default=Action.DELETE)
    automatic = models.BooleanField(
        default=False, help_text="Disposed of every night without review (logs, not records)"
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(
        max_length=300, blank=True, help_text="The source of the period, or why it differs"
    )

    class Meta:
        ordering = ["automatic", "name"]

    def __str__(self) -> str:
        return self.name


class DisposalRun(TimeStampedModel):
    """Records due under one rule, proposed by one person and disposed of only when a second approves."""

    class State(models.TextChoices):
        PROPOSED = "proposed", "Waiting for a second person"
        DONE = "done", "Disposed of"
        CANCELLED = "cancelled", "Cancelled"

    rule = models.ForeignKey(RetentionRule, on_delete=models.PROTECT, related_name="runs")
    state = models.CharField(max_length=12, choices=State.choices, default=State.PROPOSED)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["rule"], condition=models.Q(state="proposed"), name="one_proposed_run_per_rule"
            )
        ]

    def __str__(self) -> str:
        return f"Disposal of {self.rule} ({self.get_state_display()})"


class DisposalItem(models.Model):
    """One record in a run: disposed of on approval, unless someone keeps it, saying why (a legal hold)."""

    run = models.ForeignKey(DisposalRun, on_delete=models.CASCADE, related_name="items")
    entity = models.CharField(max_length=80)
    entity_id = models.BigIntegerField()
    person = models.ForeignKey(
        "people.PersonRef", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    description = models.CharField(max_length=300)
    due_since = models.DateField(help_text="When the period ran out")
    keep_reason = models.CharField(max_length=300, blank=True, help_text="Why it is kept after all")
    disposed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_since", "id"]

    def __str__(self) -> str:
        return self.description


class Breach(TimeStampedModel):
    """A personal data breach: what happened, to whose data, and what was done about it (item 1.19)."""

    class Risk(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    reference = models.CharField(max_length=20, unique=True)
    discovered_at = models.DateTimeField()
    happened = models.CharField(max_length=160, blank=True, help_text="When it happened, if known")
    summary = models.TextField(help_text="What happened")
    data_affected = models.TextField(help_text="What personal data, and whose")
    people_affected = models.PositiveIntegerField(null=True, blank=True, help_text="How many, if known")
    minors_affected = models.BooleanField(default=False, help_text="Students under 18 are among them")
    risk = models.CharField(max_length=10, choices=Risk.choices, default=Risk.MEDIUM)
    contained_at = models.DateTimeField(null=True, blank=True)
    commissioner_told_at = models.DateTimeField(null=True, blank=True)
    people_told_at = models.DateTimeField(null=True, blank=True)
    actions = models.TextField(blank=True, help_text="What has been done, and what will be")
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-discovered_at"]

    def __str__(self) -> str:
        return f"{self.reference}: {self.summary[:60]}"
