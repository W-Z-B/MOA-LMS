"""Signed-in sessions: recorded at sign-in, ended at sign-out, on time-out, or from another device.

Each sign-in creates a UserSession beside Django's own session. Ending one deletes both, so the browser
that held it is signed out on its next request.
"""

import re

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.sessions.models import Session
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from core.net import client_ip
from iam.models import RoleScope, UserSession

# Keys kept in the session by the sign-in view and the activity middleware.
SIGNED_IN_AT = "signed_in_at"
LAST_ACTIVITY = "last_activity"


def describe_device(user_agent: str) -> str:
    """'Chrome on Android' from a user-agent string; plain words, no version numbers."""
    agent = user_agent or ""
    system = next(
        (
            name
            for pattern, name in (
                (r"Android", "Android"),
                (r"iPhone|iPad|iPod", "iPhone or iPad"),
                (r"Windows", "Windows"),
                (r"Mac OS X|Macintosh", "Mac"),
                (r"CrOS", "Chromebook"),
                (r"Linux", "Linux"),
            )
            if re.search(pattern, agent)
        ),
        None,
    )
    browser = next(
        (
            name
            for pattern, name in (
                (r"Edg/", "Edge"),
                (r"OPR/|Opera", "Opera"),
                (r"Firefox/|FxiOS/", "Firefox"),
                (r"Chrome/|CriOS/", "Chrome"),
                (r"Safari/", "Safari"),
            )
            if re.search(pattern, agent)
        ),
        None,
    )
    if browser and system:
        return f"{browser} on {system}"
    return browser or system or "Unknown device"


@receiver(user_logged_in)
def record_session(sender, request, user, **kwargs):
    if request is None or not getattr(request, "session", None) or not request.session.session_key:
        return
    now = timezone.now()
    request.session[SIGNED_IN_AT] = now.timestamp()
    request.session[LAST_ACTIVITY] = now.timestamp()
    UserSession.objects.update_or_create(
        session_key=request.session.session_key,
        defaults={
            "user": user,
            "last_seen_at": now,
            "ip": client_ip(request),
            "user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:200],
        },
    )


@receiver(user_logged_out)
def forget_session(sender, request, user, **kwargs):
    if request is not None and getattr(request, "session", None) and request.session.session_key:
        UserSession.objects.filter(session_key=request.session.session_key).delete()


def end_sessions(sessions) -> int:
    """End the given UserSession rows: the Django sessions go too, so those browsers are signed out."""
    keys = list(sessions.values_list("session_key", flat=True))
    Session.objects.filter(session_key__in=keys).delete()
    UserSession.objects.filter(session_key__in=keys).delete()
    return len(keys)


def close_sessions(user) -> int:
    """Sign the person out everywhere."""
    return end_sessions(UserSession.objects.filter(user=user))


@receiver(post_save, sender=RoleScope)
@receiver(post_delete, sender=RoleScope)
def roles_changed(sender, instance, **kwargs):
    """A role given or taken away signs the person out everywhere, so the change applies from their next
    sign-in, and a role that needs an authenticator code asks for one then."""
    close_sessions(instance.user_id)
