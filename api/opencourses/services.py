"""Open short courses (item 5.07): the public catalogue, registration by email, and joining a course.

A registration answers the same whatever the address, so the page never tells whether someone has an
account. The address is proved by following the emailed link, where the person chooses a password. Rate
limits: OPEN_REGISTRATIONS_PER_ADDRESS requests an hour from one network address, and three a day for one
email address.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from audit.services import record
from core.net import client_ip
from courses.models import CourseSite
from iam.models import Role, RoleScope
from opencourses.models import OpenRegistration
from people.models import PersonRef

PER_EMAIL_PER_DAY = 3


class Refused(Exception):
    def __init__(self, code: str, detail: str, status: int = 409):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


def enabled() -> bool:
    return bool(getattr(settings, "OPEN_COURSES_ENABLED", False))


def require_enabled() -> None:
    if not enabled():
        raise Refused("open_courses_off", "GSA does not offer open short courses at present.", 404)


def open_sites():
    """Published open sites with a catalogue entry: what the public page lists."""
    return (
        CourseSite.objects.filter(kind=CourseSite.Kind.OPEN, is_published=True, catalogue__isnull=False)
        .select_related("catalogue")
        .order_by("title")
    )


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _send(to: str, subject: str, lines: list[str]) -> None:
    try:
        send_mail(f"[GSA] {subject}", "\n\n".join(lines), settings.DEFAULT_FROM_EMAIL, [to])
    except Exception:  # noqa: BLE001 - the answer is the same either way; the log has the failure
        import logging

        logging.getLogger(__name__).exception("open-course registration mail failed")


def register(request, *, email: str, first_name: str, last_name: str, site: CourseSite | None = None) -> None:
    """Ask to register. Refused only for the rate limits; otherwise the answer is the same for every
    address: a new address gets a link, a known one is told how to sign in instead."""
    from privacy.services import current_notice

    require_enabled()
    now, address = timezone.now(), client_ip(request)
    email = email.strip().lower()
    hour_ago = now - timedelta(hours=1)
    if (
        address
        and OpenRegistration.objects.filter(source_ip=address, asked_at__gte=hour_ago).count()
        >= settings.OPEN_REGISTRATIONS_PER_ADDRESS
    ):
        raise Refused(
            "too_many_requests", "Too many registrations from this network. Try again in an hour.", 429
        )
    if (
        OpenRegistration.objects.filter(email=email, asked_at__gte=now - timedelta(days=1)).count()
        >= PER_EMAIL_PER_DAY
    ):
        raise Refused(
            "too_many_requests", "Too many registrations for this address today. Try tomorrow.", 429
        )
    token = secrets.token_urlsafe(32)
    notice = current_notice()
    OpenRegistration.objects.create(
        email=email,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        site=site,
        token_hash=_hash(token),
        notice_version=notice.version if notice else None,
        source_ip=address,
    )
    known = (
        get_user_model().objects.filter(email__iexact=email).exists()
        or get_user_model().objects.filter(username__iexact=email).exists()
    )
    if known:
        _send(
            email,
            "You already have an account",
            [
                "Someone asked to register this address for GSA's open short courses.",
                "This address already has an account. Sign in with it, or ask for a new password on the "
                f"sign-in page: {settings.PUBLIC_URL}/",
                "If it was not you, you need do nothing.",
            ],
        )
        return
    hours = settings.OPEN_CONFIRM_HOURS
    _send(
        email,
        "Confirm your registration",
        [
            f"Dear {first_name.strip()},",
            "To finish registering for GSA's open short courses, follow this link and choose a password. "
            f"It works once, for {hours} hours:",
            f"{settings.PUBLIC_URL}/#/open-courses/confirm/{token}",
            "If you did not ask to register, you need do nothing: no account is made.",
        ],
    )


def _pending(token: str) -> OpenRegistration:
    found = OpenRegistration.objects.filter(token_hash=_hash(token or "")).select_related("site").first()
    expired = found is not None and found.asked_at < timezone.now() - timedelta(
        hours=settings.OPEN_CONFIRM_HOURS
    )
    if found is None or found.confirmed_at is not None or expired:
        raise Refused("link_not_valid", "This link has expired or has been used. Register again.", 400)
    return found


def check_link(token: str) -> OpenRegistration:
    require_enabled()
    return _pending(token)


def confirm(request, *, token: str, password: str):
    """Make the learner's account: the email address is its username. Returns the new user."""
    from privacy.models import NoticeAcknowledgement, PrivacyNotice

    require_enabled()
    User = get_user_model()
    with transaction.atomic():
        registration = OpenRegistration.objects.select_for_update().get(pk=_pending(token).pk)
        if User.objects.filter(username__iexact=registration.email).exists():
            raise Refused("already_registered", "This address already has an account. Sign in with it.", 409)
        user = User(username=registration.email, email=registration.email)
        try:
            validate_password(password, user)
        except ValidationError as error:
            raise Refused("weak_password", " ".join(error.messages), 400) from error
        user.set_password(password)
        user.save()
        person = PersonRef.objects.create(
            kind=PersonRef.Kind.LEARNER,
            external_id=f"OL{registration.pk:06d}",
            first_name=registration.first_name,
            last_name=registration.last_name,
            email=registration.email,
            user=user,
        )
        RoleScope.objects.create(user=user, role=Role.objects.get(code=Role.LEARNER))
        registration.confirmed_at, registration.user = timezone.now(), user
        registration.save(update_fields=["confirmed_at", "user"])
        if registration.notice_version is not None:
            notice = PrivacyNotice.objects.filter(version=registration.notice_version).first()
            if notice is not None:
                NoticeAcknowledgement.objects.get_or_create(
                    notice=notice, user=user, defaults={"source_ip": registration.source_ip}
                )
        record(request, "learner_registered", person, after={"external_id": person.external_id})
        if registration.site is not None and registration.site.kind == CourseSite.Kind.OPEN:
            try:
                join(request, registration.site, person)
            except Refused:
                pass  # full by now: they can choose another course once signed in
    return user


def join(request, site: CourseSite, person) -> None:
    """Put the person on an open course, if it has a place."""
    from staffdev.enrolment import add_learner, places_left

    require_enabled()
    if site.kind != CourseSite.Kind.OPEN or not site.is_published or not hasattr(site, "catalogue"):
        raise Refused("not_open", "That is not an open short course.", 404)
    left = places_left(site.catalogue)
    already = site.memberships.filter(person=person, is_active=True).exists()
    if left is not None and left <= 0 and not already:
        raise Refused("full", "The course is full.")
    add_learner(request, site, person, why="Joined an open short course")


def purge_expired(now=None) -> int:
    """Delete registrations whose link expired without being followed: their names and addresses go."""
    now = now or timezone.now()
    cutoff = now - timedelta(hours=settings.OPEN_CONFIRM_HOURS)
    deleted, _ = OpenRegistration.objects.filter(confirmed_at__isnull=True, asked_at__lt=cutoff).delete()
    return deleted
