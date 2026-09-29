import pyotp
import pytest
from rest_framework.test import APIClient

from conftest import PASSWORD
from iam.models import TotpDevice


@pytest.mark.django_db
def test_student_login_links_to_the_person_record(student):
    client = APIClient()
    assert (
        client.post(
            "/api/v1/auth/login/", {"username": "26MRP0001", "password": "wrong"}, format="json"
        ).status_code
        == 401
    )
    ok = client.post("/api/v1/auth/login/", {"username": "26MRP0001", "password": PASSWORD}, format="json")
    body = ok.json()
    assert ok.status_code == 200 and body["roles"] == ["student"] and body["mfa_required"] is False
    assert (body["person_kind"], body["external_id"]) == ("student", "26MRP0001")
    assert client.post("/api/v1/auth/logout/").status_code == 204
    assert client.get("/api/v1/auth/me/").status_code == 403


@pytest.mark.django_db
def test_course_admin_must_verify_totp(course_admin):
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/", {"username": "course.admin", "password": PASSWORD}, format="json"
    )
    assert login.json()["mfa_required"] is True and login.json()["mfa_verified"] is False
    assert client.get("/api/v1/sites/").status_code == 403
    assert "otpauth://" in client.post("/api/v1/auth/mfa/enrol/").json()["provisioning_uri"]
    secret = TotpDevice.objects.get(user=course_admin).secret
    good = client.post("/api/v1/auth/mfa/verify/", {"code": pyotp.TOTP(secret).now()}, format="json")
    assert good.status_code == 200 and client.get("/api/v1/sites/").status_code == 200


@pytest.mark.django_db
def test_account_locks_after_repeated_failures(student, settings):
    settings.LOGIN_MAX_FAILURES = 3
    client = APIClient()
    for _ in range(3):
        client.post("/api/v1/auth/login/", {"username": "26MRP0001", "password": "wrong"}, format="json")
    locked = client.post(
        "/api/v1/auth/login/", {"username": "26MRP0001", "password": PASSWORD}, format="json"
    )
    assert locked.status_code == 423 and locked.json()["code"] == "locked_out"
