"""Outside tools added to course sites over LTI 1.3 with Advantage (item 6.07). The LMS is the platform.

A course administrator registers a tool once (its addresses and its key); teaching staff place it in a
module of their site, either as a plain link or by choosing content inside the tool (Deep Linking 2.0). A
placement is an ordinary link item of the module whose address is the LMS's own launch address, so the
content screens need nothing new to list it. Tools may post scores back to line items (Assignment and Grade
Services), which become gradebook columns, and may read the class list (Names and Role Provisioning
Services).

A tool never learns who someone is unless the course administrator allows it for that tool: it receives an
opaque identifier per person (ToolUser), the person's role on the site and the course, and a name or an
email only when the tool's data-sharing settings say so. Both are off by default (docs/lti.md).
"""

import secrets
import uuid

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from core.fields import EncryptedTextField
from core.models import TimeStampedModel


def new_client_id() -> str:
    return secrets.token_hex(16)


def new_sub() -> str:
    return uuid.uuid4().hex


class PlatformKey(models.Model):
    """The LMS's own RSA key pair, which signs everything it sends to tools. The newest active key signs;
    retired keys stay in the published key set until removed, so tokens already issued can still be
    checked."""

    kid = models.CharField(max_length=64, unique=True)
    private_pem = EncryptedTextField(help_text="The private key, encrypted with the application key")
    public_jwk = models.JSONField(help_text="The public key as published at the JWKS address")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, help_text="Signs new messages")

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"Platform key {self.kid}"


class Tool(TimeStampedModel):
    """One outside tool, registered by a course administrator with the details the tool's maker gives."""

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    client_id = models.CharField(
        max_length=120, unique=True, default=new_client_id, help_text="Given to the tool's maker"
    )
    deployment_id = models.CharField(max_length=120, default="1", help_text="Given to the tool's maker")
    oidc_login_url = models.URLField(help_text="The tool's login initiation address")
    launch_url = models.URLField(help_text="Where a launch lands in the tool (target link)")
    deep_linking_url = models.URLField(
        blank=True, help_text="Where teaching staff choose content in the tool; empty if it has none"
    )
    redirect_urls = ArrayField(
        models.URLField(),
        default=list,
        blank=True,
        help_text="Further addresses the tool may ask launches to be sent to",
    )
    jwks_url = models.URLField(blank=True, help_text="The tool's public key set")
    public_key = models.TextField(blank=True, help_text="Or the tool's public key, as PEM or a JWK")
    share_name = models.BooleanField(default=False, help_text="Send people's names to the tool")
    share_email = models.BooleanField(default=False, help_text="Send people's email addresses to the tool")
    grades = models.BooleanField(default=True, help_text="The tool may post scores to the gradebook")
    class_list = models.BooleanField(default=False, help_text="The tool may read the class list")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(condition=~Q(jwks_url="") | ~Q(public_key=""), name="lti_tool_has_a_key")
        ]

    def __str__(self) -> str:
        return self.name

    def allowed_redirects(self) -> set[str]:
        return {u for u in [self.launch_url, self.deep_linking_url, *self.redirect_urls] if u}


class ToolUser(models.Model):
    """The identifier a tool knows a person by: random, different for every tool, never the student
    number or the account name."""

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="users")
    person = models.ForeignKey("people.PersonRef", on_delete=models.CASCADE, related_name="+")
    sub = models.CharField(max_length=64, unique=True, default=new_sub)

    class Meta:
        unique_together = [("tool", "person")]

    def __str__(self) -> str:
        return f"{self.person} in {self.tool}"


class Placement(TimeStampedModel):
    """A tool placed in a module (an LTI resource link). Its item is a link item of the module."""

    item = models.OneToOneField("courses.ContentItem", on_delete=models.CASCADE, related_name="tool_link")
    tool = models.ForeignKey(Tool, on_delete=models.PROTECT, related_name="placements")
    resource_link_id = models.UUIDField(default=uuid.uuid4, unique=True)
    target_url = models.URLField(
        blank=True, help_text="Where in the tool it opens; the tool's launch address"
    )
    custom = models.JSONField(default=dict, blank=True, help_text="Custom values the tool asked for")

    def __str__(self) -> str:
        return f"{self.tool} as {self.item}"

    @property
    def site(self):
        return self.item.module.site


class LineItem(TimeStampedModel):
    """A gradebook column that a tool posts scores to (Assignment and Grade Services)."""

    site = models.ForeignKey("courses.CourseSite", on_delete=models.CASCADE, related_name="tool_line_items")
    tool = models.ForeignKey(Tool, on_delete=models.PROTECT, related_name="line_items")
    placement = models.ForeignKey(
        Placement, null=True, blank=True, on_delete=models.SET_NULL, related_name="line_items"
    )
    label = models.CharField(max_length=160)
    score_maximum = models.DecimalField(max_digits=9, decimal_places=2)
    resource_id = models.CharField(max_length=255, blank=True)
    tag = models.CharField(max_length=255, blank=True)
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Relative weight in the coursework; 0 shows the column without counting it",
    )
    grade_category = models.ForeignKey(
        "assessments.GradeCategory", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["site", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(score_maximum__gt=0), name="lti_line_item_maximum_positive"),
            models.CheckConstraint(condition=Q(weight__gte=0), name="lti_line_item_weight_not_negative"),
        ]

    def __str__(self) -> str:
        return f"{self.site.code}: {self.label}"


class Score(models.Model):
    """The latest score a tool posted for one person on one line item."""

    line_item = models.ForeignKey(LineItem, on_delete=models.CASCADE, related_name="scores")
    person = models.ForeignKey("people.PersonRef", on_delete=models.PROTECT, related_name="tool_scores")
    score_given = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    score_maximum = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    activity_progress = models.CharField(max_length=20)
    grading_progress = models.CharField(max_length=20)
    comment = models.TextField(blank=True)
    timestamp = models.DateTimeField(help_text="When the tool says the score was given")
    received_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("line_item", "person")]

    def __str__(self) -> str:
        return f"{self.person} on {self.line_item}: {self.score_given}"

    @property
    def graded(self) -> bool:
        return self.grading_progress == "FullyGraded" and self.score_given is not None


class Launch(models.Model):
    """One launch the LMS began for a signed-in person: the login hint sent to the tool comes back with
    the tool's authentication request and must match, once, within LTI_LAUNCH_SECONDS. For content
    selection it also travels as the deep-linking "data" and is checked again when the tool returns."""

    class Kind(models.TextChoices):
        RESOURCE_LINK = "resource_link", "Open a placed tool"
        DEEP_LINKING = "deep_linking", "Choose content in a tool"

    hint = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    kind = models.CharField(max_length=14, choices=Kind.choices)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="+")
    placement = models.ForeignKey(
        Placement, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    module = models.ForeignKey(
        "courses.Module", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    authenticated_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True, help_text="Deep linking: content came back")

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.tool} for {self.user}"


class UsedValue(models.Model):
    """A nonce or token identifier a tool has already used, so a message cannot be replayed."""

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=12)  # auth_nonce, link_nonce, assertion
    value = models.CharField(max_length=255)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tool", "kind", "value"], name="lti_value_used_once")]

    def __str__(self) -> str:
        return f"{self.kind} {self.value}"


class AccessToken(models.Model):
    """A bearer token issued to a tool for the services; only its hash is kept."""

    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, related_name="+")
    token_hash = models.CharField(max_length=64, unique=True)
    scopes = ArrayField(models.CharField(max_length=120), default=list)
    expires_at = models.DateTimeField()

    def __str__(self) -> str:
        return f"Token for {self.tool} until {self.expires_at:%Y-%m-%d %H:%M}"
