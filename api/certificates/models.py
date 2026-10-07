"""Certificates of completion (items 5.08 to 5.11), built on the HRMS letters and checking modules.

A certificate is issued as a PDF from a versioned template, with a reference and a check code printed on it;
anyone shown it checks it on the public page without signing in. A certificate issued in error is withdrawn,
and the check then says so.
"""

from django.conf import settings
from django.db import models

from core.fields import EncryptedTextField
from core.models import TimeStampedModel
from core.uploads import _stored


def certificate_name(instance, filename: str) -> str:
    return _stored("certificates", filename)


class CertificateTemplate(TimeStampedModel):
    """One version of a certificate's wording. A change is saved as the next version; a certificate keeps
    the version it was issued from."""

    code = models.SlugField(max_length=40, help_text="The same in every version")
    version = models.PositiveSmallIntegerField(default=1)
    name = models.CharField(max_length=120)
    heading = models.CharField(max_length=160, default="Certificate of Completion")
    body = models.TextField(
        help_text="Paragraphs apart by a blank line, **bold**, fields in double braces such as {{full_name}}"
    )
    signatory_name = models.CharField(max_length=120, blank=True)
    signatory_title = models.CharField(max_length=120, default="Principal")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["name", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="one_certificate_template_version")
        ]

    def __str__(self) -> str:
        return f"{self.name}, version {self.version}"


class Certificate(TimeStampedModel):
    """A certificate issued to a person for completing a course. What went into it is kept with it."""

    reference = models.CharField(max_length=30, unique=True)
    completion = models.ForeignKey(
        "courses.Completion", null=True, blank=True, on_delete=models.SET_NULL, related_name="certificates"
    )
    site = models.ForeignKey("courses.CourseSite", on_delete=models.PROTECT, related_name="certificates")
    person = models.ForeignKey("people.PersonRef", on_delete=models.PROTECT, related_name="certificates")
    template = models.ForeignKey(CertificateTemplate, on_delete=models.PROTECT, related_name="certificates")
    issued_on = models.DateField()
    completed_on = models.DateField()
    expires_on = models.DateField(null=True, blank=True)
    values = models.JSONField(help_text="Every field as it went into the certificate")
    file = models.FileField(upload_to=certificate_name)
    sha256 = models.CharField(max_length=64, help_text="Fingerprint of the PDF as issued")
    check_code = EncryptedTextField(help_text="Printed on the certificate for checking it")
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawn_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    withdrawal_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-issued_on", "-id"]

    def __str__(self) -> str:
        return self.reference

    @property
    def is_withdrawn(self) -> bool:
        return self.withdrawn_at is not None


class CertificateCheck(models.Model):
    """One use of the page that checks a certificate: the reference asked about, whether the code matched,
    and the network address it came from. Kept like sign-in attempts."""

    at = models.DateTimeField(auto_now_add=True, db_index=True)
    reference = models.CharField(max_length=40)
    certificate = models.ForeignKey(
        Certificate, null=True, blank=True, on_delete=models.CASCADE, related_name="checks"
    )
    matched = models.BooleanField()
    source_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-at"]
        indexes = [models.Index(fields=["source_ip", "at"], name="certcheck_ip_at")]

    def __str__(self) -> str:
        return f"{self.reference} checked at {self.at:%d/%m/%Y %H:%M}"


class SigningKey(models.Model):
    """The installation's Ed25519 key for signing Open Badges credentials (item 5.10). The private half is
    encrypted at rest; retired keys stay so that credentials signed with them can still be checked."""

    kid = models.CharField(max_length=40, unique=True)
    public_jwk = models.JSONField(help_text="The public key as a JSON Web Key, as published")
    private_pem = EncryptedTextField(
        help_text="The private key (PKCS #8), encrypted with FIELD_ENCRYPTION_KEY"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    retired_at = models.DateTimeField(null=True, blank=True, help_text="No longer signs; still checks")

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.kid


class BadgeCredential(models.Model):
    """A certificate as an Open Badges 3.0 credential, signed as a VC-JWT (item 5.10)."""

    certificate = models.OneToOneField(Certificate, on_delete=models.CASCADE, related_name="badge")
    credential_id = models.UUIDField(unique=True, help_text="The credential's id is urn:uuid:<this>")
    jwt = models.TextField(help_text="The signed credential, as the holder downloads it")
    key = models.ForeignKey(SigningKey, on_delete=models.PROTECT, related_name="credentials")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Badge for {self.certificate}"
