"""The rotating check-in code shown in the room (item 4.15).

The code is "<issued>-<signature>": the time it was made (seconds, in hexadecimal) and an HMAC-SHA256 of the
session and that time under a key derived from FIELD_ENCRYPTION_KEY, as core.crypto derives its keys, cut
to 12 hex characters. It is valid for ATTENDANCE_CODE_SECONDS (60) after it was made: the screen in the room
asks for a new one well before then. Nothing is stored: the server checks the signature and the age. A code
copied from the screen is useless a minute later, and a code for one session never checks in to another.

The screen in the room also shows a short code of six characters, for students to type where no camera reads
a QR code: an HMAC of the session and the minute (ATTENDANCE_CODE_SECONDS windows) written in an alphabet
without the characters people confuse (no I, O, 0 or 1), large enough to read from the back of the room. It
is good in its own minute and the next, so a student who reads it as the minute turns still has a minute to
type it. Thirty bits against a rate-limited API cannot be guessed in two minutes.
"""

import hashlib
import hmac
import re
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


ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 32 characters: no I, O, 0 or 1
SHORT_LENGTH = 6


def _short(session_id: int, window: int) -> str:
    digest = hmac.new(_key(), f"short:{session_id}:{window}".encode(), hashlib.sha256).digest()
    number = int.from_bytes(digest[:8], "big")
    return "".join(ALPHABET[(number >> (5 * i)) & 31] for i in range(SHORT_LENGTH))


def make_short(session_id: int, now: float | None = None) -> tuple[str, int]:
    """The six-character code of this minute, and the seconds until the next one is due on the screen."""
    now = now if now is not None else time.time()
    seconds = settings.ATTENDANCE_CODE_SECONDS
    window = int(now // seconds)
    return _short(session_id, window), max(int((window + 1) * seconds - now), 1)


def _check_short(session_id: int, typed: str, now: float) -> str | None:
    window = int(now // settings.ATTENDANCE_CODE_SECONDS)
    if any(hmac.compare_digest(typed, _short(session_id, window - back)) for back in (0, 1)):
        return None
    if any(hmac.compare_digest(typed, _short(session_id, window - back)) for back in (2, 3, 4, 5)):
        return "expired"
    return "invalid"


def check(session_id: int, code: str, now: float | None = None) -> str | None:
    """None when the code (long or short) is good for the session now; otherwise 'invalid' or 'expired'."""
    now = now if now is not None else time.time()
    if "-" not in (code or "").strip():
        typed = re.sub(r"\s", "", code or "").upper()
        return _check_short(session_id, typed, now) if len(typed) == SHORT_LENGTH else "invalid"
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
