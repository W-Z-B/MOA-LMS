"""Create notifications and deliver them by email. Synchronous for now; a worker task can take over later.

Each person chooses, kind by kind, whether a notification also comes by email at once, in a daily summary,
or not by email at all (item 2.33), and whether it is pushed to their installed app (item 4.04). The
notification itself always appears in the app.
"""

import logging
from collections.abc import Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from notifications import push
from notifications.models import Notification, NotificationPreference

log = logging.getLogger(__name__)
SUMMARY_LISTED = 50  # notifications listed in one summary email; the rest are counted


def users_with_role(role_code: str, *, campus_code: str | None = None):
    """Users holding a role; a campus limits campus-scoped grants (unscoped grants always match)."""
    qs = get_user_model().objects.filter(is_active=True, role_scopes__role__code=role_code)
    if campus_code:
        qs = qs.filter(Q(role_scopes__campus_code=campus_code) | Q(role_scopes__campus_code=""))
    return qs.distinct()


def email_choice(user, kind: str) -> str:
    """How the person wants this kind by email: instant (the default), daily or off."""
    choice = (
        NotificationPreference.objects.filter(user=user, kind=kind).values_list("email", flat=True).first()
    )
    return choice or NotificationPreference.Email.INSTANT


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
    """Create one notification per recipient (once per dedupe_key) and email those with an address, as
    each person has chosen for this kind."""
    created: list[Notification] = []
    for user in recipients:
        if user is None:
            continue
        choice = email_choice(user, kind) if email and user.email else NotificationPreference.Email.OFF
        try:
            with transaction.atomic():
                note = Notification.objects.create(
                    recipient=user,
                    kind=kind,
                    title=title,
                    body=body,
                    link=link,
                    dedupe_key=dedupe_key,
                    in_summary=choice == NotificationPreference.Email.DAILY,
                )
        except IntegrityError:
            continue  # already sent for this key
        if choice == NotificationPreference.Email.INSTANT:
            note.emailed = _send_email(user.email, title, body, link)
            if note.emailed:
                note.save(update_fields=["emailed"])
        if push.wanted(user, kind):
            _push_later(note.id)
        created.append(note)
    return created


def _push_later(notification_id: int) -> None:
    """Push is sent by the job worker once the notification is committed, never inside the request."""
    from notifications.tasks import send_push

    transaction.on_commit(lambda: send_push.defer(notification_id=notification_id))


def send_daily_summaries(now=None) -> int:
    """One email to each person with notifications held for their summary; returns how many were sent."""
    now = now or timezone.now()
    held = Notification.objects.filter(in_summary=True, summarised_at__isnull=True).select_related(
        "recipient"
    )
    by_user: dict = {}
    for note in held.order_by("recipient_id", "created_at"):
        by_user.setdefault(note.recipient, []).append(note)
    sent = 0
    for user, notes in by_user.items():
        lines = [f"- {n.title}" + (f": {n.body}" if n.body else "") for n in notes[:SUMMARY_LISTED]]
        if len(notes) > SUMMARY_LISTED:
            lines.append(f"... and {len(notes) - SUMMARY_LISTED} more in the app.")
        title = f"Your daily summary: {len(notes)} notification{'s' if len(notes) != 1 else ''}"
        emailed = bool(user.email) and _send_email(user.email, title, "\n".join(lines), "/notifications")
        Notification.objects.filter(id__in=[n.id for n in notes]).update(summarised_at=now, emailed=emailed)
        sent += int(emailed)
    return sent


def _send_email(address: str, title: str, body: str, link: str) -> bool:
    origin = (settings.PUBLIC_ORIGINS or [f"https://{settings.ALLOWED_HOSTS[0]}"])[0]
    message = body if not link else f"{body}\n\nOpen in GSA LMS: {origin}/#{link}"
    try:
        return send_mail(f"[GSA LMS] {title}", message, settings.DEFAULT_FROM_EMAIL, [address]) == 1
    except Exception:  # noqa: BLE001 - mail failures must never break the business transaction
        log.exception("notification email to %s failed", address)
        return False
