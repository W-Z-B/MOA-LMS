"""Application-layer encryption for sensitive values (authenticator secrets, accommodation reasons, keys).

The keys come from the environment: FIELD_ENCRYPTION_KEYS, a comma-separated list with the newest key first,
or FIELD_ENCRYPTION_KEY for a single key. Any string is accepted; each is hashed to a 32-byte Fernet key so
the value never has to be a specific format.

Changing the key (ASVS 1.6.3, 6.2.4; docs/runbook.md, "Changing the encryption key"):
1. put the new key first and keep the old one after it: FIELD_ENCRYPTION_KEYS=new,old. New values are
   encrypted with the new key; stored values are read with whichever key opens them;
2. run `python manage.py rotate_field_key`, which encrypts every stored value again with the new key;
3. move the old key out of FIELD_ENCRYPTION_KEYS into AUDIT_CHAIN_RETIRED_KEYS. It no longer opens
   anything, but the audit log's earlier entries were sealed with a key derived from it (chain_keys), and
   the nightly check needs it to verify them. Keep it with the backups too: a backup made before the
   change needs it to be read.
"""

import base64
import hashlib
import hmac
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _split(value) -> list[str]:
    if isinstance(value, list | tuple):
        return [str(v) for v in value if str(v).strip()]
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def keys() -> list[str]:
    """The encryption keys, newest first: FIELD_ENCRYPTION_KEYS, or FIELD_ENCRYPTION_KEY alone."""
    found = _split(getattr(settings, "FIELD_ENCRYPTION_KEYS", None)) or _split(
        [getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""]
    )
    return found


def current_key() -> str:
    """The newest key: the one new values are encrypted, and other keys derived, with."""
    found = keys()
    if not found:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY is not set; sensitive fields cannot be stored")
    return found[0]


def _fernet_of(raw: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest()))


@lru_cache(maxsize=1)
def _fernet() -> MultiFernet:
    current_key()  # refuses when no key is set
    return MultiFernet([_fernet_of(raw) for raw in keys()])


def encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode("utf-8"))


def decrypt(token: bytes) -> str:
    try:
        return _fernet().decrypt(bytes(token)).decode("utf-8")
    except InvalidToken as exc:  # wrong key or corrupted value
        raise ValueError("stored value cannot be decrypted with the configured keys") from exc


def is_current(token: bytes) -> bool:
    """Whether a stored value is already encrypted with the newest key."""
    try:
        _fernet_of(current_key()).decrypt(bytes(token))
    except InvalidToken:
        return False
    return True


def mask(value: str | None, visible: int = 3) -> str | None:
    """Return a display form that shows only the last few characters."""
    if not value:
        return None
    return "•" * max(len(value) - visible, 4) + value[-visible:]


def fingerprint(value: str) -> str:
    """A short keyed fingerprint of a sensitive value, for telling in the audit log that it changed.

    HMAC-SHA256 under a key derived from the newest encryption key, cut to 10 hex characters: equal values
    give equal fingerprints, and without the server key the value cannot be worked back from it. After the
    key is changed the same value has a new fingerprint; compare entries on either side of the change with
    care.
    """
    raw = keys()[0] if keys() else ""
    key = hashlib.sha256(b"audit-fingerprint:" + raw.encode("utf-8")).digest()
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:10]


def _chain_key_of(raw: str) -> bytes:
    return hashlib.sha256(b"audit-chain:" + raw.encode("utf-8")).digest()


def chain_key() -> bytes:
    """The key that seals new audit entries (audit.chain), derived from the newest encryption key.

    It is never stored in the database, so changing a row there cannot be hidden by recomputing the chain.
    """
    try:
        return _chain_key_of(current_key())
    except ImproperlyConfigured as exc:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY is not set; audit entries cannot be sealed") from exc


def chain_keys() -> list[bytes]:
    """Every key an audit entry may have been sealed with, newest first: one derived from each encryption key
    in use, then from each retired key in AUDIT_CHAIN_RETIRED_KEYS. A retired key opens no stored value; it
    is kept only so that entries sealed before the key was changed still verify."""
    retired = _split(getattr(settings, "AUDIT_CHAIN_RETIRED_KEYS", None))
    seen, found = set(), []
    for raw in [*keys(), *retired]:
        if raw not in seen:
            seen.add(raw)
            found.append(_chain_key_of(raw))
    if not found:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY is not set; audit entries cannot be checked")
    return found
