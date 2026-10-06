"""Keys: the LMS's own key pair and published key set, and the keys tools sign with (item 6.07).

Every message between the LMS and a tool is a JSON Web Token signed with RS256, as LTI 1.3 requires. The
LMS makes its key pair the first time it needs one and keeps the private key encrypted with the
application key. A tool's public key is either pasted in at registration or read from the tool's key set
address (fetched over HTTPS, cached for LTI_JWKS_CACHE_SECONDS).
"""

import json
import secrets
import urllib.request
from urllib.parse import urlparse

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from lti.models import PlatformKey, Tool

ALGORITHM = "RS256"


class ToolKeyError(Exception):
    """A tool's key could not be found or read."""


def make_key() -> PlatformKey:
    """A new RSA key pair for the LMS. Earlier keys stop signing but stay published."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    kid = secrets.token_hex(8)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    public.update({"kid": kid, "alg": ALGORITHM, "use": "sig"})
    with transaction.atomic():
        PlatformKey.objects.filter(is_active=True).update(is_active=False)
        return PlatformKey.objects.create(kid=kid, private_pem=pem, public_jwk=public)


def signing_key() -> PlatformKey:
    key = PlatformKey.objects.filter(is_active=True).first()
    return key or make_key()


def key_set() -> dict:
    """The LMS's published key set: every key not yet removed."""
    if not PlatformKey.objects.exists():
        make_key()
    return {"keys": [k.public_jwk for k in PlatformKey.objects.all()]}


def sign(claims: dict) -> str:
    key = signing_key()
    return jwt.encode(claims, key.private_pem, algorithm=ALGORITHM, headers={"kid": key.kid})


def fetch_json(url: str) -> dict:
    """GET a JSON document from an address a course administrator registered."""
    if urlparse(url).scheme not in ("https", "http" if settings.DEBUG else "https"):
        raise ValueError("A key set address must start https://.")
    request = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310 - checked
    with urllib.request.urlopen(request, timeout=settings.INTEGRATION_TIMEOUT_SECONDS) as response:  # noqa: S310
        return json.loads(response.read(1_000_000).decode("utf-8"))


def _from_jwk(jwk: dict):
    return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))


def parse_public_key(text: str):
    """A tool's public key pasted in at registration: PEM, or one JWK as JSON. Raises ValueError."""
    text = (text or "").strip()
    if text.startswith("{"):
        try:
            return _from_jwk(json.loads(text))
        except (ValueError, jwt.InvalidKeyError) as error:
            raise ValueError("The key is not a readable RSA JSON Web Key.") from error
    try:
        key = serialization.load_pem_public_key(text.encode())
    except ValueError as error:
        raise ValueError("The key is not a readable PEM public key.") from error
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError("LTI 1.3 needs an RSA key.")
    return key


def tool_key(tool: Tool, kid: str | None):
    """The public key the tool signed with: its pasted key, or the one named kid in its key set."""
    if tool.public_key:
        return parse_public_key(tool.public_key)
    cache_key = f"lti-jwks-{tool.pk}"
    keys = cache.get(cache_key)
    if keys is None:
        try:
            keys = fetch_json(tool.jwks_url).get("keys", [])
        except (OSError, ValueError) as error:
            raise ToolKeyError("The tool's key set could not be read.") from error
        cache.set(cache_key, keys, settings.LTI_JWKS_CACHE_SECONDS)
    for jwk in keys:
        if kid is None or jwk.get("kid") == kid:
            try:
                return _from_jwk(jwk)
            except (ValueError, jwt.InvalidKeyError) as error:
                raise ToolKeyError("The tool's key could not be read.") from error
    raise ToolKeyError("The tool's key set has no key for this message.")


def verify_from_tool(tool: Tool, token: str, *, audience: str | list[str]) -> dict:
    """Check a token the tool signed: its signature, its audience and its times. Raises jwt errors or
    ToolKeyError; the caller checks the claims that depend on the message."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError as error:
        raise jwt.InvalidTokenError("The message is not a signed token.") from error
    if header.get("alg") != ALGORITHM:
        raise jwt.InvalidAlgorithmError("Only RS256 is accepted.")
    return jwt.decode(
        token,
        tool_key(tool, header.get("kid")),
        algorithms=[ALGORITHM],
        audience=audience,
        options={"require": ["exp", "iat", "iss"]},
        leeway=settings.LTI_CLOCK_LEEWAY_SECONDS,
    )
