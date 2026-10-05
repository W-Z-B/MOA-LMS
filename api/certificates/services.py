"""Issuing certificates (item 5.08) and withdrawing them (item 5.11). Ported from the HRMS
letters/services.py."""

import hashlib
from datetime import date

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.utils import timezone

from audit.services import record
from certificates import checking, markup, pdf
from certificates.models import Certificate, CertificateTemplate
from notifications.services import notify

REFERENCE_LOCK = 5_008_001  # one reference at a time (the audit chain holds its own lock)
# The fields a template may use, with the words the template editor shows for each.
FIELDS: dict[str, str] = {
    "full_name": "Full name",
    "first_name": "First name",
    "last_name": "Last name",
    "number": "Employee or student number",
    "course": "Course title",
    "course_code": "Course code",
    "length_hours": "Length in hours",
    "completed_on": "Date completed",
    "expires_on": "Date it must be renewed by",
    "today": "Date issued",
    "reference": "Certificate reference",
}
DEFAULT_BODY = (
    "This is to certify that the person named above completed the course\n\n"
    "**{{course}}**\n\n"
    "on {{completed_on}}."
)


class Refused(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def long_date(day: date | None) -> str:
    return f"{day.day} {day:%B %Y}" if day else ""


def current(code: str) -> CertificateTemplate | None:
    """The newest version of a template, whether or not it is in use."""
    return CertificateTemplate.objects.filter(code=code).order_by("-version").first()


def template_for(code: str) -> CertificateTemplate:
    """The newest version of the template; the School's plain completion certificate when there is none."""
    found = current(code) or current("completion")
    if found is not None:
        return found
    return CertificateTemplate.objects.create(
        code="completion", name="Certificate of completion", body=DEFAULT_BODY, signatory_title="Principal"
    )


def new_version(request, template: CertificateTemplate, changes: dict) -> CertificateTemplate:
    """Save a change to a template as its next version; certificates already issued keep theirs."""
    newest = current(template.code)
    fields = ("name", "heading", "body", "signatory_name", "signatory_title", "is_active")
    values = {field: changes.get(field, getattr(newest, field)) for field in fields}
    with transaction.atomic():
        made = CertificateTemplate.objects.create(
            code=newest.code, version=newest.version + 1, created_by=request.user, **values
        )
        record(request, "template_versioned", made, after={"code": made.code, "version": made.version})
    return made


def _values(completion, reference: str, today: date) -> dict[str, str]:
    person, site = completion.person, completion.site
    entry = getattr(site, "catalogue", None)
    hours = entry.length_hours if entry is not None and entry.length_hours is not None else None
    return {
        "full_name": person.full_name,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "number": person.external_id,
        "course": site.title,
        "course_code": site.code,
        "length_hours": f"{hours.normalize():f}" if hours is not None else "",
        "completed_on": long_date(completion.completed_on),
        "expires_on": long_date(completion.expires_on),
        "today": long_date(today),
        "reference": reference,
    }


def _next_reference(year: int) -> str:
    prefix = f"{settings.CERTIFICATE_REFERENCE_PREFIX}/{year}/"
    last = (
        Certificate.objects.filter(reference__startswith=prefix)
        .order_by("-id")
        .values_list("reference", flat=True)
        .first()
    )
    number = int(last.rsplit("/", 1)[1]) + 1 if last else 1
    return f"{prefix}{number:04d}"


def issue(request, completion, *, template_code: str = "completion") -> Certificate:
    """Issue the certificate for a completion: a reference, a code, the PDF and its fingerprint, and word to
    the person. Issued again for a renewal; each keeps its own dates."""
    template = template_for(template_code)
    if not template.is_active:
        raise Refused("retired", "That certificate template is no longer in use.")
    today = timezone.localdate()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [REFERENCE_LOCK])
        reference = _next_reference(today.year)
        values = _values(completion, reference, today)
        code = checking.new_code()
        body = markup.to_html(markup.merge(markup.parse(template.body), values))
        content = pdf.render(pdf.page(template=template, values=values, body_html=body, check_code=code))
        certificate = Certificate.objects.create(
            reference=reference,
            completion=completion,
            site=completion.site,
            person=completion.person,
            template=template,
            issued_on=today,
            completed_on=completion.completed_on,
            expires_on=completion.expires_on,
            values=values,
            file=ContentFile(content, name=f"{reference.replace('/', '-')}.pdf"),
            sha256=hashlib.sha256(content).hexdigest(),
            check_code=code,
        )
        completion.certificate = reference
        completion.save(update_fields=["certificate", "updated_at"])
        record(
            request,
            "certificate_issued",
            certificate,
            after={
                "reference": reference,
                "template": template.code,
                "version": template.version,
                "sha256": certificate.sha256,
            },
        )
    user = completion.person.user
    if user is not None and user.is_active:
        notify(
            [user],
            title=f"Your certificate for {completion.site.title}",
            body=f"Reference {reference}. Download it under My certificates.",
            link="/certificates",
            dedupe_key=f"certificate:{certificate.pk}",
        )
    return certificate


def withdraw(request, certificate: Certificate, reason: str) -> Certificate:
    """Withdraw a certificate issued in error (item 5.11). The check then says it is withdrawn."""
    if certificate.is_withdrawn:
        raise Refused("already_withdrawn", "This certificate has already been withdrawn.")
    if not reason.strip():
        raise Refused("reason_required", "Say why the certificate is withdrawn.")
    with transaction.atomic():
        certificate.withdrawn_at = timezone.now()
        certificate.withdrawn_by = request.user
        certificate.withdrawal_reason = reason.strip()
        certificate.save(update_fields=["withdrawn_at", "withdrawn_by", "withdrawal_reason", "updated_at"])
        record(
            request,
            "certificate_withdrawn",
            certificate,
            before={"withdrawn": False},
            after={"withdrawn": True, "reference": certificate.reference},
            reason=reason,
        )
    user = certificate.person.user
    if user is not None and user.is_active:
        notify(
            [user],
            title=f"Your certificate {certificate.reference} was withdrawn",
            body=f"Reason: {certificate.withdrawal_reason}",
            link="/certificates",
            kind="alert",
            dedupe_key=f"certificate-withdrawn:{certificate.pk}",
        )
    return certificate
