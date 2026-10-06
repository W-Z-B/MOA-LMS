"""Certificates as Open Badges 3.0 credentials (item 5.10).

Each certificate is also issued as an OpenBadgeCredential (a W3C verifiable credential), signed as a VC-JWT
with the installation's Ed25519 key, which the holder downloads and keeps in a wallet. Anyone shown it checks
it on the public certificate check page (or through the API), which verifies the signature against the LMS's
own keys and then says whether the certificate is still valid: a withdrawn certificate's credential is
answered as withdrawn, whatever its signature.

The JWT. Header: alg "EdDSA", typ "JWT", kid = the issuer's address and the key's id ("…/issuer.json#key-1").
Payload: the credential itself (with @context, id, type, issuer, validFrom, validUntil, credentialSubject),
with the registered claims iss (the issuer's id), jti (the credential's id), nbf, iat and, when the
certificate must be renewed, exp. The holder is named by an identity hash (OB 3.0 IdentityObject: their email
address, or failing that their number, salted and hashed), never in plain words.

Keys. The first credential creates the installation's key: an Ed25519 key pair whose private half is kept
encrypted with FIELD_ENCRYPTION_KEY (core.fields.EncryptedTextField). The public keys are published at a
stable address: the issuer profile (/api/badges/issuer.json, with each key as a JsonWebKey verification
method, in the manner of did:web) and a JWKS (/api/badges/jwks.json). `manage.py rotate_badge_key` retires the
current key and makes a new one; retired keys stay published so earlier credentials still verify
(docs/SETUP.md). The issuer's id is built from PUBLIC_URL, which is why issuing waits for OPEN_BADGES_ENABLED:
GSA's permanent address must be settled first, because every credential carries it.
"""

import base64
import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from certificates.models import BadgeCredential, Certificate, SigningKey

KEY_LOCK = 5_010_001
CONTEXTS = [
    "https://www.w3.org/ns/credentials/v2",
    "https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.3.json",
]
MAX_TOKEN = 32 * 1024


class BadgesOff(Exception):
    """OPEN_BADGES_ENABLED is off."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issuer_id() -> str:
    return f"{settings.PUBLIC_URL}/api/badges/issuer.json"


# ---------------------------------------------------------------------------------------------------------
# Keys


def _new_key(number: int) -> SigningKey:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    kid = f"key-{number}"
    jwk = {"kty": "OKP", "crv": "Ed25519", "x": _b64(public), "kid": kid, "alg": "EdDSA", "use": "sig"}
    return SigningKey.objects.create(kid=kid, public_jwk=jwk, private_pem=pem)


def current_key() -> SigningKey:
    """The key new credentials are signed with; made the first time one is needed."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [KEY_LOCK])
        key = SigningKey.objects.filter(retired_at__isnull=True).order_by("-id").first()
        return key or _new_key(SigningKey.objects.count() + 1)


def rotate() -> SigningKey:
    """Retire the current key (it stays published for checking) and make the next."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [KEY_LOCK])
        SigningKey.objects.filter(retired_at__isnull=True).update(retired_at=timezone.now())
        return _new_key(SigningKey.objects.count() + 1)


def _private(key: SigningKey) -> Ed25519PrivateKey:
    return serialization.load_pem_private_key(key.private_pem.encode(), password=None)


def jwks() -> dict:
    return {"keys": [key.public_jwk for key in SigningKey.objects.order_by("id")]}


def issuer_profile() -> dict:
    issuer = issuer_id()
    return {
        "@context": CONTEXTS,
        "id": issuer,
        "type": ["Profile"],
        "name": settings.CERTIFICATE_ORGANISATION,
        "url": settings.PUBLIC_URL,
        "verificationMethod": [
            {
                "id": f"{issuer}#{key.kid}",
                "type": "JsonWebKey",
                "controller": issuer,
                "publicKeyJwk": {k: v for k, v in key.public_jwk.items() if k in ("kty", "crv", "x")},
            }
            for key in SigningKey.objects.order_by("id")
        ],
        "jwks": f"{settings.PUBLIC_URL}/api/badges/jwks.json",
    }


# ---------------------------------------------------------------------------------------------------------
# Credentials


def _instant(day, end=False) -> str:
    moment = timezone.make_aware(datetime.combine(day, time.max if end else time.min))
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _identity(certificate: Certificate) -> dict:
    person = certificate.person
    value, kind = (
        (person.email.strip().lower(), "emailAddress") if person.email else (person.external_id, "sourcedId")
    )
    salt = secrets.token_hex(8)
    return {
        "type": "IdentityObject",
        "identityHash": "sha256$" + hashlib.sha256(f"{value}{salt}".encode()).hexdigest(),
        "identityType": kind,
        "hashed": True,
        "salt": salt,
    }


def credential_for(certificate: Certificate, credential_id: uuid.UUID) -> dict:
    site = certificate.site
    values = certificate.values or {}
    course = values.get("course") or site.title
    achievement_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{settings.PUBLIC_URL}/courses/{site.code}")
    organisation = settings.CERTIFICATE_ORGANISATION
    credential = {
        "@context": CONTEXTS,
        "id": f"urn:uuid:{credential_id}",
        "type": ["VerifiableCredential", "OpenBadgeCredential"],
        "issuer": {
            "id": issuer_id(),
            "type": ["Profile"],
            "name": settings.CERTIFICATE_ORGANISATION,
            "url": settings.PUBLIC_URL,
        },
        "validFrom": _instant(certificate.issued_on),
        "name": course,
        "credentialSubject": {
            "type": ["AchievementSubject"],
            "identifier": [_identity(certificate)],
            "achievement": {
                "id": f"urn:uuid:{achievement_id}",
                "type": ["Achievement"],
                "achievementType": "Certificate",
                "name": course,
                "description": f"Completion of the course {course} ({site.code}) at {organisation}.",
                "criteria": {
                    "narrative": f"The holder completed the course on {values.get('completed_on', '')} and "
                    "was "
                    f"issued certificate {certificate.reference}, which can be checked at "
                    f"{settings.CERTIFICATE_CHECK_URL}."
                },
            },
        },
    }
    if certificate.expires_on:
        credential["validUntil"] = _instant(certificate.expires_on, end=True)
    return credential


def sign(payload: dict, key: SigningKey) -> str:
    header = {"alg": "EdDSA", "typ": "JWT", "kid": f"{issuer_id()}#{key.kid}"}

    def encoded(part: dict) -> str:
        return _b64(json.dumps(part, separators=(",", ":")).encode())

    signing_input = f"{encoded(header)}.{encoded(payload)}"
    return f"{signing_input}.{_b64(_private(key).sign(signing_input.encode()))}"


def issue(certificate: Certificate) -> BadgeCredential:
    """The certificate's credential, issued the first time it is asked for."""
    if not settings.OPEN_BADGES_ENABLED:
        raise BadgesOff
    existing = BadgeCredential.objects.filter(certificate=certificate).select_related("key").first()
    if existing is not None:
        return existing
    key = current_key()
    credential_id = uuid.uuid4()
    credential = credential_for(certificate, credential_id)
    now = int(timezone.now().timestamp())
    claims = {
        "iss": issuer_id(),
        "jti": credential["id"],
        "nbf": int(datetime.fromisoformat(credential["validFrom"].replace("Z", "+00:00")).timestamp()),
        "iat": now,
    }
    if "validUntil" in credential:
        claims["exp"] = int(
            datetime.fromisoformat(credential["validUntil"].replace("Z", "+00:00")).timestamp()
        )
    token = sign({**credential, **claims}, key)
    return BadgeCredential.objects.create(
        certificate=certificate, credential_id=credential_id, jwt=token, key=key
    )


# ---------------------------------------------------------------------------------------------------------
# Checking a credential someone presents


def _no_match(detail: str) -> dict:
    return {
        "status": "no_match",
        "detail": detail,
        "reference": None,
        "holder": None,
        "course": None,
        "completed_on": None,
        "issued_on": None,
        "expires_on": None,
        "withdrawn_on": None,
    }


def verify(token: str) -> tuple[dict, Certificate | None]:
    """Whether a presented credential is one this LMS issued and still stands by. Returns the answer, in the
    shape of the certificate check (certificates.checking.answer), and the certificate when it matched."""
    from certificates.checking import answer

    token = "".join((token or "").split())
    if token.startswith("{"):
        try:
            token = json.loads(token).get("jwt", "") or json.loads(token).get("proof", {}).get("jwt", "")
        except (ValueError, AttributeError):
            token = ""
    parts = token.split(".")
    if len(token) > MAX_TOKEN or len(parts) != 3:
        refusal = (
            "This is not a credential the LMS issued: paste the whole credential (a long line of letters "
            "and dots)."
        )
        return _no_match(refusal), None
    try:
        header = json.loads(_unb64(parts[0]))
        payload = json.loads(_unb64(parts[1]))
        signature = _unb64(parts[2])
    except (ValueError, TypeError):
        return _no_match("The credential cannot be read; it may have been changed or cut short."), None
    kid = str(header.get("kid", ""))
    issuer = issuer_id()
    if header.get("alg") != "EdDSA" or not kid.startswith(f"{issuer}#") or payload.get("iss") != issuer:
        return _no_match("This credential was not issued by this LMS."), None
    key = SigningKey.objects.filter(kid=kid.split("#", 1)[1]).first()
    if key is None:
        return _no_match("This credential was not issued by this LMS."), None
    public = Ed25519PublicKey.from_public_bytes(_unb64(key.public_jwk["x"]))
    try:
        public.verify(signature, f"{parts[0]}.{parts[1]}".encode())
    except InvalidSignature:
        return _no_match(
            "The credential's signature does not match: it has been changed since it was issued."
        ), None
    jti = str(payload.get("jti", ""))
    stored = (
        BadgeCredential.objects.filter(credential_id=jti.removeprefix("urn:uuid:"))
        .select_related("certificate__person")
        .first()
        if jti.startswith("urn:uuid:") and _is_uuid(jti.removeprefix("urn:uuid:"))
        else None
    )
    if stored is None:
        return _no_match("This LMS has no record of that credential."), None
    return answer(stored.certificate), stored.certificate


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
