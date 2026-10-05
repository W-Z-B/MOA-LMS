"""Item 5.09: anyone shown a certificate checks it is genuine, by its reference and the code printed on it.
Ported from the HRMS letters/checking.py.

The answer says only what the certificate itself says: whom it is for, the course, when it was completed and
issued, and until when it is valid. A wrong code and an unknown reference get the same answer, so the page
never tells which references exist. Failures are limited for each network address and each reference, every
check is logged, and the holder is told when their certificate has been checked. A withdrawn certificate is
answered as withdrawn (item 5.11), only to someone who holds its right code.
"""

import hmac
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from audit.services import record_event
from core.net import client_ip
from notifications.services import notify

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford's: no I, L, O or U, so nothing is misread
LENGTH = 12  # 60 bits: out of reach of guessing at a few tries an hour
READ_AS = str.maketrans("OIL", "011")


class TooMany(Exception):
    """Too many wrong answers lately, from this address or for this reference."""


def new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    return "-".join(raw[i : i + 4] for i in range(0, LENGTH, 4))


def plain(code: str) -> str:
    """A code as it may be typed: any case, with spaces or dashes, O for 0 and I or L for 1."""
    return re.sub(r"[\s-]", "", code.upper()).translate(READ_AS)


def _blocked(address: str | None, reference: str) -> bool:
    from certificates.models import CertificateCheck

    since = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    failures = CertificateCheck.objects.filter(matched=False, at__gte=since)
    limit = settings.CERTIFICATE_CHECK_FAILURES
    if address is not None and failures.filter(source_ip=address).count() >= limit:
        return True
    return failures.filter(reference__iexact=reference).count() >= limit


def check(request, reference: str, code: str):
    """The certificate, when the reference and code match one; None otherwise. Raises TooMany when blocked."""
    from certificates.models import Certificate, CertificateCheck

    reference = reference.strip()[:40]
    address = client_ip(request)
    if _blocked(address, reference):
        raise TooMany
    certificate = (
        Certificate.objects.filter(reference__iexact=reference)
        .select_related("person", "person__user")
        .first()
    )
    given = plain(code).encode()
    matched = bool(
        certificate is not None
        and certificate.check_code
        and hmac.compare_digest(plain(certificate.check_code).encode(), given)
    )
    CertificateCheck.objects.create(
        reference=reference, certificate=certificate if matched else None, matched=matched, source_ip=address
    )
    if not matched:
        return None  # logged above with the address; the audit log records only checks that matched
    after = {"certificate": certificate.pk, "reference": certificate.reference}
    record_event(request, "certificate_checked", "certificates.certificate", after=after)
    user = certificate.person.user
    if user is not None and user.is_active:
        today = timezone.localdate()
        notify(
            [user],
            title=f"Your certificate {certificate.reference} was checked",
            body="Someone you showed it to checked that it is genuine. If you showed it to no one, "
            "tell the course administrator.",
            link="/certificates",
            email=False,
            dedupe_key=f"certificate-checked:{certificate.pk}:{today:%Y%m%d}",
        )
    return certificate


def answer(certificate) -> dict:
    """What the check says: the same for a wrong code and an unknown reference."""
    empty = dict.fromkeys(("reference", "holder", "course", "completed_on", "issued_on", "expires_on"))
    if certificate is None:
        return {
            "status": "no_match",
            "detail": "No certificate matches that reference and code. Check both against the certificate.",
            **empty,
            "withdrawn_on": None,
        }
    facts = {
        "reference": certificate.reference,
        "holder": certificate.values.get("full_name", ""),
        "course": certificate.values.get("course", ""),
        "completed_on": certificate.completed_on,
        "issued_on": certificate.issued_on,
        "expires_on": certificate.expires_on,
    }
    if certificate.is_withdrawn:
        return {
            "status": "withdrawn",
            "detail": "This certificate was issued but has since been withdrawn by the School. "
            "It is not valid.",
            **facts,
            "withdrawn_on": timezone.localdate(certificate.withdrawn_at),
        }
    expired = certificate.expires_on is not None and certificate.expires_on < timezone.localdate()
    detail = "This certificate is genuine. Compare the details with the certificate you hold."
    if expired:
        detail += " It is past the date it was valid until."
    return {"status": "genuine", "detail": detail, **facts, "withdrawn_on": None}
