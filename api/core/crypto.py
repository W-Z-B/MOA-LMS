"""Application-layer encryption for sensitive identifiers (NIS number, TIN, national ID).

The key is FIELD_ENCRYPTION_KEY from the environment. Any string is accepted; it is hashed
to a 32-byte Fernet key so the value never has to be a specific format. Rotating the key
requires re-encrypting stored values (see docs/SETUP.md, key rotation).
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    raw = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if not raw:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY is not set; sensitive fields cannot be stored")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
    return Fernet(key)


def encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode("utf-8"))


def decrypt(token: bytes) -> str:
    try:
        return _fernet().decrypt(bytes(token)).decode("utf-8")
    except InvalidToken as exc:  # wrong key or corrupted value
        raise ValueError("stored value cannot be decrypted with the configured key") from exc


def mask(value: str | None, visible: int = 3) -> str | None:
    """Return a display form that shows only the last few characters."""
    if not value:
        return None
    return "•" * max(len(value) - visible, 4) + value[-visible:]
