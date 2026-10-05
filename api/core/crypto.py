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


def fingerprint(value: str) -> str:
    """A short keyed fingerprint of a sensitive value, for telling in the audit log that it changed.

    HMAC-SHA256 under a key derived from FIELD_ENCRYPTION_KEY, cut to 10 hex characters: equal values
    give equal fingerprints, and without the server key the value cannot be worked back from it.
    """
    import hmac

    raw = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    key = hashlib.sha256(b"audit-fingerprint:" + raw.encode("utf-8")).digest()
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:10]


def chain_key() -> bytes:
    """The key of the audit log's chained fingerprints (audit.chain), derived from FIELD_ENCRYPTION_KEY.

    It is never stored in the database, so changing a row there cannot be hidden by recomputing the chain.
    Rotating FIELD_ENCRYPTION_KEY starts a new key: verify the chain first, and keep the old key with the
    backups so that the earlier entries can still be checked.
    """
    raw = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if not raw:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY is not set; audit entries cannot be sealed")
    return hashlib.sha256(b"audit-chain:" + raw.encode("utf-8")).digest()
