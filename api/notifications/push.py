"""Push notices to the installed app (item 4.04; ADR 0011, point 5), by Web Push with VAPID.

pywebpush (MPL-2.0, a named exception under ADR 0002) signs each notice with GSA's VAPID key and encrypts
it for the one browser that subscribed, so the browser's push service carries it without being able to
read it. A notice says only its title and where it leads: the rest stays in the app, behind sign-in.

Push is off until VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY are set. A person turns it on per device (the
browser asks them) and per kind of notification (NotificationPreference.push). A subscription the push
service reports as gone (404 or 410) is removed; one that fails five times in a row is removed too.
"""

import json
import logging
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone

from notifications.models import Notification, NotificationPreference, PushSubscription

log = logging.getLogger(__name__)
GONE = {404, 410}
MAX_FAILURES = 5
TTL_SECONDS = 24 * 60 * 60  # a notice not delivered within a day is no longer worth a phone's attention


def configured() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def allowed_endpoint(endpoint: str) -> bool:
    """Whether an endpoint is an https address at one of the known push services (PUSH_SERVICE_HOSTS): the
    server sends requests to it, so it must never be an address of someone's choosing."""
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.port not in (None, 443):
        return False
    return any(host == known or host.endswith(f".{known}") for known in settings.PUSH_SERVICE_HOSTS)


def wanted(user, kind: str) -> bool:
    """Whether the person asked for this kind of notification by push, and has a device to receive it."""
    if not configured():
        return False
    chose = NotificationPreference.objects.filter(user=user, kind=kind, push=True).exists()
    return chose and PushSubscription.objects.filter(user=user).exists()


def payload(note: Notification) -> str:
    return json.dumps({"title": note.title[:120], "link": note.link or "/", "tag": f"gsa-lms-{note.id}"})


def send(note: Notification) -> int:
    """Push one notification to each of its recipient's devices. Returns how many took it."""
    from pywebpush import WebPushException, webpush
    from requests import RequestException

    if not configured():
        return 0
    delivered = 0
    for subscription in PushSubscription.objects.filter(user_id=note.recipient_id):
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload(note),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                ttl=TTL_SECONDS,
                timeout=10,
            )
        except (WebPushException, RequestException) as error:
            code = getattr(getattr(error, "response", None), "status_code", None)
            if code in GONE or subscription.failures + 1 >= MAX_FAILURES:
                log.info("push subscription %s removed (%s)", subscription.pk, code or "failing")
                subscription.delete()
            else:
                subscription.failures += 1
                subscription.save(update_fields=["failures"])
                log.warning("push to subscription %s failed: %s", subscription.pk, code)
            continue
        subscription.failures, subscription.last_sent_at = 0, timezone.now()
        subscription.save(update_fields=["failures", "last_sent_at"])
        delivered += 1
    return delivered
