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


def verify(client, user):
    """Give the authenticator code, enrolling first if need be."""
    if not TotpDevice.objects.filter(user=user).exists():
        client.post("/api/v1/auth/mfa/enrol/")
    secret = TotpDevice.objects.get(user=user).secret
    return client.post("/api/v1/auth/mfa/verify/", {"code": pyotp.TOTP(secret).now()}, format="json")


@pytest.mark.django_db
def test_lecturers_must_verify_an_authenticator_code_too(lecturer, site):
    """Decision D14: lecturers release marks that become results (item 1.11)."""
    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": "E0001", "password": PASSWORD}, format="json")
    assert login.json()["mfa_required"] is True and login.json()["mfa_verified"] is False
    refused = client.get("/api/v1/sites/")
    assert refused.status_code == 403 and refused.json()["code"] == "mfa_required"
    assert verify(client, lecturer.user).status_code == 200
    assert client.get("/api/v1/sites/").json()["count"] == 1


@pytest.mark.django_db
def test_teaching_on_a_site_needs_a_code_whatever_the_system_roles(make_person, site):
    from courses.models import Membership

    assistant = make_person("staff", "E0009", "Vic", "Ally")  # no system role at all
    Membership.objects.create(site=site, person=assistant, role="assistant")
    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": "E0009", "password": PASSWORD}, format="json")
    assert login.json()["mfa_required"] is True
    assert client.get(f"/api/v1/sites/{site.id}/gradebook/").json()["code"] == "mfa_required"


@pytest.mark.django_db
def test_a_session_is_verified_only_by_a_code(student):
    """A session that needed no code at sign-in does not count as verified (item 1.06)."""
    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"username": "26MRP0001", "password": PASSWORD}, format="json")
    assert login.json()["mfa_required"] is False and login.json()["mfa_verified"] is False
    assert client.session["mfa_verified"] is False
    assert client.get("/api/v1/sites/").status_code == 200  # a student needs no code


@pytest.mark.django_db
def test_a_role_that_needs_a_code_asks_for_one_at_the_next_sign_in(student):
    from iam.models import Role, RoleScope

    client = APIClient()
    client.post("/api/v1/auth/login/", {"username": "26MRP0001", "password": PASSWORD}, format="json")
    RoleScope.objects.create(user=student.user, role=Role.objects.get(code=Role.COURSE_ADMIN))
    assert client.get("/api/v1/sites/").json()["code"] == "not_authenticated"  # signed out by the change
    again = client.post("/api/v1/auth/login/", {"username": "26MRP0001", "password": PASSWORD}, format="json")
    assert again.json()["mfa_required"] is True and again.json()["mfa_verified"] is False
    assert client.get("/api/v1/sites/").json()["code"] == "mfa_required"


@pytest.mark.django_db
def test_admin_needs_the_verified_web_sign_in(seeded):
    """The admin has no password form of its own and refuses a session no code has verified (item 1.05)."""
    from django.contrib.auth import get_user_model

    root = get_user_model().objects.create_superuser("root.admin", "root@gsa.edu.gy", PASSWORD)
    client = APIClient()
    client.force_login(root)
    assert client.get("/admin/").status_code == 302  # signed in, but no authenticator code yet

    login_form = client.get("/admin/login/")
    assert login_form.status_code == 302 and login_form["Location"] == "/"
    assert client.post("/admin/login/", {"username": "root.admin", "password": PASSWORD}).status_code == 302

    session = client.session
    session["mfa_verified"] = True
    session.save()
    assert client.get("/admin/").status_code == 200


@pytest.mark.django_db
def test_admin_asks_staff_for_a_code_even_when_their_roles_do_not(seeded):
    from django.contrib.auth import get_user_model

    clerk = get_user_model().objects.create_user("clerk", password=PASSWORD, is_staff=True)
    client = APIClient()
    client.post("/api/v1/auth/login/", {"username": "clerk", "password": PASSWORD}, format="json")
    assert client.get("/admin/").status_code == 302
    assert verify(client, clerk).status_code == 200
    assert client.get("/admin/").status_code == 200


@pytest.mark.django_db
def test_one_address_failing_across_many_accounts_is_held_back(student, settings):
    """Password spraying: few failures per account, many from one address (item 1.08)."""
    settings.LOGIN_MAX_FAILURES_PER_ADDRESS = 3
    sprayer = APIClient(HTTP_X_REAL_IP="203.0.113.7")
    for name in ("someone.one", "someone.two", "someone.three"):
        attempt = {"username": name, "password": "Summer2026!"}
        failed = sprayer.post("/api/v1/auth/login/", attempt, format="json")
        assert failed.status_code == 401
    held = sprayer.post("/api/v1/auth/login/", {"username": "26MRP0001", "password": PASSWORD}, format="json")
    assert held.status_code == 429 and held.json()["code"] == "too_many_attempts"

    elsewhere = APIClient(HTTP_X_REAL_IP="190.80.1.2")
    ok = elsewhere.post("/api/v1/auth/login/", {"username": "26MRP0001", "password": PASSWORD}, format="json")
    assert ok.status_code == 200


@pytest.mark.django_db
def test_a_forged_forwarded_for_header_does_not_reach_the_records(student):
    """The address is the one Caddy saw (item 1.09)."""
    from audit.models import AuditLog
    from iam.models import LoginAttempt

    client = APIClient(HTTP_X_FORWARDED_FOR="6.6.6.6", HTTP_X_REAL_IP="190.80.1.2")
    client.post("/api/v1/auth/login/", {"username": "26MRP0001", "password": PASSWORD}, format="json")
    assert LoginAttempt.objects.get().source_ip == "190.80.1.2"
    assert AuditLog.objects.filter(action="login").latest("at").source_ip == "190.80.1.2"
