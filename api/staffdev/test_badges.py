"""Item 5.10: certificates also as Open Badges 3.0 credentials, signed as VC-JWTs with the installation's
Ed25519 key, the issuer and its keys published, and a presented credential checked on the public page."""

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.core.management import call_command
from rest_framework.test import APIClient

from audit.models import AuditLog
from certificates import badges
from certificates.models import BadgeCredential, Certificate, SigningKey
from staffdev import completion
from staffdev.models import CatalogueEntry

CHECK = "/api/v1/certificates/check-badge/"


def part(token: str, index: int) -> dict:
    piece = token.split(".")[index]
    return json.loads(base64.urlsafe_b64decode(piece + "=" * (-len(piece) % 4)))


@pytest.fixture
def badges_on(settings):
    settings.OPEN_BADGES_ENABLED = True
    settings.PUBLIC_URL = "https://lms.gsa.example"


@pytest.fixture
def certificate(staff, course, badges_on):
    entry = CatalogueEntry.objects.get(site=course)
    done = completion.record_completion(entry, staff, how="recorded")
    return Certificate.objects.get(completion=done)


def check(token: str):
    return APIClient().post(CHECK, {"credential": token}, format="json", REMOTE_ADDR="203.0.113.9")


@pytest.mark.django_db
def test_a_certificate_is_issued_as_a_signed_open_badge(certificate, staff):
    badge = BadgeCredential.objects.get(certificate=certificate)  # issued with the certificate
    header, payload = part(badge.jwt, 0), part(badge.jwt, 1)
    assert header == {
        "alg": "EdDSA",
        "typ": "JWT",
        "kid": "https://lms.gsa.example/api/badges/issuer.json#key-1",
    }
    assert payload["type"] == ["VerifiableCredential", "OpenBadgeCredential"]
    assert payload["@context"][1].endswith("context-3.0.3.json")
    assert payload["iss"] == payload["issuer"]["id"] == "https://lms.gsa.example/api/badges/issuer.json"
    assert payload["jti"] == payload["id"] == f"urn:uuid:{badge.credential_id}"
    assert payload["validFrom"].endswith("Z") and payload["nbf"] <= payload["iat"]
    subject = payload["credentialSubject"]
    identity = subject["identifier"][0]
    assert identity["identityType"] == "emailAddress" and identity["hashed"] is True
    assert identity["identityHash"].startswith("sha256$") and "joy@gsa.edu.gy" not in badge.jwt
    assert subject["achievement"]["name"] == certificate.values["course"]
    key = SigningKey.objects.get()
    public = Ed25519PublicKey.from_public_bytes(badges._unb64(key.public_jwk["x"]))
    signed = badge.jwt.rsplit(".", 1)
    public.verify(badges._unb64(signed[1]), signed[0].encode())  # raises if the signature is wrong
    assert "PRIVATE KEY" not in str(SigningKey.objects.values_list("private_pem", flat=True).query)


@pytest.mark.django_db
def test_the_private_key_is_stored_encrypted(certificate):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT private_pem FROM certificates_signingkey")
        stored = bytes(cursor.fetchone()[0])
    assert b"PRIVATE KEY" not in stored
    assert "PRIVATE KEY" in SigningKey.objects.get().private_pem


@pytest.mark.django_db
def test_the_holder_downloads_the_credential(certificate, staff, client_for, make_person):
    holder = client_for(staff.user)
    listed = holder.get("/api/v1/certificates/").json()["results"][0]
    assert listed["badge_url"] == f"/api/v1/certificates/{certificate.id}/badge/"
    download = holder.get(listed["badge_url"])
    assert download.status_code == 200 and download["Content-Type"] == "application/vc+jwt"
    assert download.content.decode() == certificate.badge.jwt
    assert "-badge.jwt" in download["Content-Disposition"]
    assert AuditLog.objects.filter(entity="certificates.badgecredential", action="download").exists()
    stranger = client_for(make_person("staff", "E0999", "Some", "One").user)
    assert stranger.get(listed["badge_url"]).status_code == 404


@pytest.mark.django_db
def test_badges_wait_for_the_setting(staff, course, client_for, settings):
    settings.OPEN_BADGES_ENABLED = False
    entry = CatalogueEntry.objects.get(site=course)
    certificate = Certificate.objects.get(
        completion=completion.record_completion(entry, staff, how="recorded")
    )
    assert not BadgeCredential.objects.exists()
    holder = client_for(staff.user)
    assert holder.get("/api/v1/certificates/").json()["results"][0]["badge_url"] is None
    refused = holder.get(f"/api/v1/certificates/{certificate.id}/badge/")
    assert refused.status_code == 404 and refused.json()["code"] == "badges_off"
    assert "Check a digital badge" not in APIClient().get("/api/check-certificate/").content.decode()


@pytest.mark.django_db
def test_the_issuer_and_its_keys_are_published(certificate):
    profile = APIClient().get("/api/badges/issuer.json")
    assert profile.status_code == 200 and profile["Access-Control-Allow-Origin"] == "*"
    body = profile.json()
    assert body["type"] == ["Profile"] and body["id"] == "https://lms.gsa.example/api/badges/issuer.json"
    method = body["verificationMethod"][0]
    assert method["id"].endswith("#key-1") and method["publicKeyJwk"]["crv"] == "Ed25519"
    keys = APIClient().get("/api/badges/jwks.json").json()["keys"]
    assert keys[0]["kid"] == "key-1" and "d" not in keys[0]


@pytest.mark.django_db
def test_a_presented_credential_is_checked(certificate, course_admin, client_for):
    token = certificate.badge.jwt
    genuine = check(token).json()
    assert genuine["status"] == "genuine" and genuine["reference"] == certificate.reference
    assert AuditLog.objects.filter(action="badge_checked").exists()
    header, payload, signature = token.split(".")
    forged = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    forged["name"] = "Something else"
    changed = base64.urlsafe_b64encode(json.dumps(forged).encode()).rstrip(b"=").decode()
    assert "signature does not match" in check(f"{header}.{changed}.{signature}").json()["detail"]
    assert check("not a token").json()["status"] == "no_match"
    assert check("a.b.c").json()["status"] == "no_match"
    stranger = (
        base64.urlsafe_b64encode(b'{"alg":"EdDSA","kid":"https://evil.example/i#k"}').rstrip(b"=").decode()
    )
    assert "not issued by this LMS" in check(f"{stranger}.{payload}.{signature}").json()["detail"]
    client_for(course_admin).post(
        f"/api/v1/certificates/{certificate.id}/withdraw/", {"reason": "Issued in error"}, format="json"
    )
    withdrawn = check(json.dumps({"jwt": token})).json()
    assert withdrawn["status"] == "withdrawn"
    assert (
        client_for(certificate.person.user).get(f"/api/v1/certificates/{certificate.id}/badge/").status_code
        == 409
    )


@pytest.mark.django_db
def test_the_public_page_checks_a_badge_without_script(certificate):
    page = APIClient().get("/api/check-certificate/").content.decode()
    assert "Check a digital badge" in page and "<script" not in page
    answered = APIClient().post(
        "/api/check-certificate/", {"credential": certificate.badge.jwt}, REMOTE_ADDR="203.0.113.7"
    )
    assert "This certificate is genuine" in answered.content.decode()
    forged = APIClient().post("/api/check-certificate/", {"credential": certificate.badge.jwt[:-4] + "AAAA"})
    assert "signature does not match" in forged.content.decode()


@pytest.mark.django_db
def test_rotating_the_key_keeps_earlier_credentials_checking(certificate, staff, course):
    old = certificate.badge.jwt
    call_command("rotate_badge_key", stdout=__import__("io").StringIO())
    assert SigningKey.objects.filter(retired_at__isnull=True).get().kid == "key-2"
    assert check(old).json()["status"] == "genuine"
    assert AuditLog.objects.filter(action="badge_key_rotated").exists()
    renewed = Certificate.objects.create(
        reference="GSA/LMS/2026/9999",
        site=certificate.site,
        person=certificate.person,
        template=certificate.template,
        issued_on=certificate.issued_on,
        completed_on=certificate.completed_on,
        values=certificate.values,
        file=certificate.file.name,
        sha256=certificate.sha256,
        check_code="ABCD-EFGH-JKMN",
    )
    assert part(badges.issue(renewed).jwt, 0)["kid"].endswith("#key-2")
    assert len(APIClient().get("/api/badges/jwks.json").json()["keys"]) == 2
