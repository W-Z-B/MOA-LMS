"""Create notifications and deliver them by email. Synchronous for now; a worker task can take over later."""

import logging
from collections.abc import Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q

from notifications.models import Notification

log = logging.getLogger(__name__)


def users_with_role(role_code: str, *, campus_code: str | None = None):
    """Users holding a role; a campus limits campus-scoped grants (unscoped grants always match)."""
    qs = get_user_model().objects.filter(is_active=True, role_scopes__role__code=role_code)
    if campus_code:
        qs = qs.filter(Q(role_scopes__campus_code=campus_code) | Q(role_scopes__campus_code=""))
    return qs.distinct()


def notify(
    recipients: Iterable,
    *,
    title: str,
    body: str = "",
    link: str = "",
    kind: str = Notification.Kind.INFO,
    dedupe_key: str = "",
    email: bool = True,
) -> list[Notification]:
    """Create one notification per recipient (once per dedupe_key) and email those with an address."""
    created: list[Notification] = []
    for user in recipients:
        if user is None:
            continue
        try:
            with transaction.atomic():
                note = Notification.objects.create(
                    recipient=user, kind=kind, title=title, body=body, link=link, dedupe_key=dedupe_key
                )
        except IntegrityError:
            continue  # already sent for this key
        if email and user.email:
            note.emailed = _send_email(user.email, title, body, link)
            if note.emailed:
                note.save(update_fields=["emailed"])
        created.append(note)
    return created


def _send_email(address: str, title: str, body: str, link: str) -> bool:
    origin = (settings.PUBLIC_ORIGINS or [f"https://{settings.ALLOWED_HOSTS[0]}"])[0]
    message = body if not link else f"{body}\n\nOpen in GSA LMS: {origin}/#{link}"
    try:
        return send_mail(f"[GSA LMS] {title}", message, settings.DEFAULT_FROM_EMAIL, [address]) == 1
    except Exception:  # noqa: BLE001 - mail failures must never break the business transaction
        log.exception("notification email to %s failed", address)
        return False
