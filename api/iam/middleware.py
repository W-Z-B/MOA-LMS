"""Ends sessions that are idle or too old, and keeps the session list current.

A session ends after SESSION_IDLE_MINUTES without a request, or SESSION_COOKIE_AGE after sign-in,
whichever comes first (OWASP ASVS level 2 asks for at most 30 minutes idle and 12 hours in all). An API
call on an ended session answers 401 with the code "session_expired", so the web app can say why.
"""

import time
from datetime import UTC, datetime

from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse

from core.net import client_ip
from iam.models import UserSession
from iam.sessions import LAST_ACTIVITY, SIGNED_IN_AT

# Writing the session on every request would cost a database write each time; once a minute is enough
# for an idle limit measured in minutes.
TOUCH_EVERY_SECONDS = 60


class SessionActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        session = getattr(request, "session", None)
        if user is not None and user.is_authenticated and session is not None and session.session_key:
            ended = self._check(request, session)
            if ended is not None:
                return ended
        return self.get_response(request)

    def _check(self, request, session):
        now = time.time()
        last = session.get(LAST_ACTIVITY)
        started = session.get(SIGNED_IN_AT)
        idle_for = now - last if last else 0
        age = now - started if started else 0
        if idle_for > settings.SESSION_IDLE_MINUTES * 60 or age > settings.SESSION_COOKIE_AGE:
            reason = (
                f"You were signed out after {settings.SESSION_IDLE_MINUTES} minutes without activity."
                if idle_for > settings.SESSION_IDLE_MINUTES * 60
                else "You were signed out because your session reached its time limit."
            )
            logout(request)
            if request.path.startswith("/api/"):
                return JsonResponse({"code": "session_expired", "detail": reason}, status=401)
            return None
        if last is None or idle_for >= TOUCH_EVERY_SECONDS:
            session[LAST_ACTIVITY] = now
            if started is None:
                session[SIGNED_IN_AT] = now
            seen = datetime.fromtimestamp(now, tz=UTC)
            updated = UserSession.objects.filter(session_key=session.session_key).update(
                last_seen_at=seen, ip=client_ip(request)
            )
            if not updated:  # a session from before this list existed: add it rather than end it
                UserSession.objects.create(
                    user=request.user,
                    session_key=session.session_key,
                    last_seen_at=seen,
                    ip=client_ip(request),
                    user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:200],
                )
        return None
