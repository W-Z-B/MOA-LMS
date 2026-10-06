"""Open short courses for farmers and extension officers (item 5.07; needs GSA's decision D0, ADR 0021).

Off unless OPEN_COURSES_ENABLED is set. When on, the published open sites are listed on a public page and
anyone may register with their email address. Registration only asks: the account is made when the person
follows the link sent to that address and chooses a password. They become a learner, who sees open sites
only, never an academic site.
"""

from django.conf import settings
from django.db import models


class OpenRegistration(models.Model):
    """A request to register, waiting for its emailed link to be followed. Only a fingerprint of the link's
    token is kept; an unconfirmed request is deleted once its link has expired (opencourses.tasks)."""

    email = models.EmailField()
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    site = models.ForeignKey(
        "courses.CourseSite", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    notice_version = models.PositiveIntegerField(
        null=True, blank=True, help_text="The privacy notice shown and accepted when registering"
    )
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    asked_at = models.DateTimeField(auto_now_add=True, db_index=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Once made",
    )

    class Meta:
        ordering = ["-asked_at"]
        indexes = [
            models.Index(fields=["source_ip", "asked_at"], name="openreg_ip_at"),
            models.Index(fields=["email", "asked_at"], name="openreg_email_at"),
        ]

    def __str__(self) -> str:
        return f"Registration of {self.email} at {self.asked_at:%Y-%m-%d %H:%M}"
