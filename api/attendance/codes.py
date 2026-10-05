"""The rotating check-in code shown in the room (item 4.15).

The code is "<issued>-<signature>": the time it was made (seconds, in hexadecimal) and an HMAC-SHA256 of the
session and that time under a key derived from FIELD_ENCRYPTION_KEY, as core.crypto derives its keys, cut
to 12 hex characters. It is valid for ATTENDANCE_CODE_SECONDS (60) after it was made: the screen in the room
asks for a new one well before then. Nothing is stored: the server checks the signature and the age. A code
copied from the screen is useless a minute later, and a code for one session never checks in to another.
"""

import hashlib
import hmac
import time

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

SKEW_SECONDS = 5  # a code "from the future" by a few seconds is the server's own clock between requests


def _key() -> bytes:
    raw = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if not raw:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY is not set; check-in codes cannot be made")
    return hashlib.sha256(b"attendance-check-in:" + raw.encode("utf-8")).digest()


def _signature(session_id: int, issued: int) -> str:
    message = f"{session_id}:{issued}".encode()
    return hmac.new(_key(), message, hashlib.sha256).hexdigest()[:12]


def make(session_id: int, now: float | None = None) -> tuple[str, int]:
    """A fresh code for the session, and the seconds it stays valid."""
    issued = int(now if now is not None else time.time())
    return f"{issued:x}-{_signature(session_id, issued)}", settings.ATTENDANCE_CODE_SECONDS


def check(session_id: int, code: str, now: float | None = None) -> str | None:
    """None when the code is good for the session now; otherwise why not: 'invalid' or 'expired'."""
    now = now if now is not None else time.time()
    try:
        issued_hex, signature = (code or "").strip().lower().split("-", 1)
        issued = int(issued_hex, 16)
    except ValueError:
        return "invalid"
    if not hmac.compare_digest(signature, _signature(session_id, issued)):
        return "invalid"
    if issued > now + SKEW_SECONDS:
        return "invalid"
    if now - issued > settings.ATTENDANCE_CODE_SECONDS:
        return "expired"
    return None
