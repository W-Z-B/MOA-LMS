"""Fixes from the ASVS Level 2 review (item 7.01, docs/security/asvs-l2.md) on signing in."""

import time

import pyotp
import pytest
from django.core import mail
from rest_framework.test import APIClient

from audit.models import AuditLog
from conftest import PASSWORD
from iam.models import TotpDevice
from notifications.models import Notification


def signed_in(username):
    client = APIClient()
    client.post("/api/v1/auth/login/", {"username": username, "password": PASSWORD}, format="json")
    return client


def code(user, offset=0):
    totp = pyotp.TOTP(TotpDevice.objects.get(user=user).secret)
    return totp.at(time.time() + offset * totp.interval)


@pytest.mark.django_db
def test_wrong_authenticator_codes_lock_the_account_and_end_the_session(course_admin, settings):
    """ASVS 2.2.1: guessing codes is limited like guessing passwords."""
    settings.LOGIN_MAX_FAILURES = 3
    client = signed_in("course.admin")
    client.post("/api/v1/auth/mfa/enrol/")
    for _ in range(2):
        wrong = client.post("/api/v1/auth/mfa/verify/", {"code": "000000"}, format="json")
        assert wrong.status_code == 400 and wrong.json()["code"] == "invalid_code"
    locked = client.post("/api/v1/auth/mfa/verify/", {"code": "000000"}, format="json")
    assert locked.status_code == 423 and locked.json()["code"] == "locked_out"
    assert client.get("/api/v1/auth/me/").status_code == 403  # signed out
    assert AuditLog.objects.filter(action="locked_out").exists()
    # Even the right code and password wait out the lockout.
    again = APIClient().post(
        "/api/v1/auth/login/", {"username": "course.admin", "password": PASSWORD}, format="json"
    )
    assert again.status_code == 423


@pytest.mark.django_db
def test_an_authenticator_code_is_accepted_once(course_admin, settings):
    """ASVS 2.8.4: a code seen by someone else cannot be used again, in this session or another."""
    first = signed_in("course.admin")
    first.post("/api/v1/auth/mfa/enrol/")
    now_code = code(course_admin)
    assert first.post("/api/v1/auth/mfa/verify/", {"code": now_code}, format="json").status_code == 200
    second = signed_in("course.admin")
    reused = second.post("/api/v1/auth/mfa/verify/", {"code": now_code}, format="json")
    assert reused.status_code == 400 and reused.json()["code"] == "code_used"
    assert (
        second.post("/api/v1/auth/mfa/verify/", {"code": code(course_admin, 1)}, format="json").status_code
        == 200
    )
    # On a test stack where two runs share one fictional account, reuse can be allowed.
    settings.MFA_REFUSE_REUSED_CODES = False
    third = signed_in("course.admin")
    assert (
        third.post("/api/v1/auth/mfa/verify/", {"code": code(course_admin, 1)}, format="json").status_code
        == 200
    )


@pytest.mark.django_db
def test_setting_up_an_authenticator_and_changing_a_password_are_told_to_the_person(course_admin):
    """ASVS 2.2.3, 2.5.5: the person learns of every change to how they sign in."""
    course_admin.email = "admin@gsa.example"
    course_admin.save()
    client = signed_in("course.admin")
    client.post("/api/v1/auth/mfa/enrol/")
    client.post("/api/v1/auth/mfa/verify/", {"code": code(course_admin)}, format="json")
    changed = client.post(
        "/api/v1/auth/password/change/",
        {"current_password": PASSWORD, "new_password": "An0ther-Long-Passphrase-77"},
        format="json",
    )
    assert changed.status_code == 200
    titles = set(Notification.objects.filter(recipient=course_admin).values_list("title", flat=True))
    assert {"An authenticator was set up on your account", "Your password was changed"} <= titles
    assert any("Your password was changed" in m.subject for m in mail.outbox)


@pytest.mark.django_db
def test_failed_sign_ins_reach_the_chained_audit_log_without_unknown_names(student, settings):
    """ASVS 7.2.1: kept with the audit log, not only in the attempts purged after a year."""
    settings.LOGIN_MAX_FAILURES = 2
    client = APIClient()
    for _ in range(2):
        client.post("/api/v1/auth/login/", {"username": "26MRP0001", "password": "wrong"}, format="json")
    client.post("/api/v1/auth/login/", {"username": "maybe-a-password", "password": "x"}, format="json")
    assert AuditLog.objects.filter(action="login_failed", entity="auth.user").count() == 2
    assert AuditLog.objects.filter(action="locked_out").count() == 1
    assert "maybe-a-password" not in str(list(AuditLog.objects.values_list("after", "before")))


@pytest.mark.django_db
def test_roles_and_authenticators_changed_in_the_django_admin_are_audited(course_admin, make_user, rf):
    """ASVS 7.1.3, 4.3.3: the admin is no way round the audit log."""
    from django.contrib.admin.sites import site as admin_site

    from iam.admin import RoleScopeAdmin, TotpDeviceAdmin
    from iam.models import Role, RoleScope

    superuser = make_user("root.admin", "administrator")
    request = rf.post("/admin/")
    request.user = superuser
    scope = RoleScope(user=course_admin, role=Role.objects.get(code="auditor"))
    roles = RoleScopeAdmin(RoleScope, admin_site)
    roles.save_model(request, scope, form=None, change=False)
    scope.campus_code = "MRP"
    roles.save_model(request, scope, form=None, change=True)
    roles.delete_queryset(request, RoleScope.objects.filter(pk=scope.pk))
    device = TotpDevice.objects.create(user=course_admin, secret="JBSWY3DPEHPK3PXP")
    TotpDeviceAdmin(TotpDevice, admin_site).delete_model(request, device)
    actions = list(AuditLog.objects.filter(actor=superuser).order_by("id").values_list("action", flat=True))
    assert actions == ["role_given", "role_changed", "role_taken", "authenticator_reset"]
    assert AuditLog.objects.get(action="role_changed").before["campus_code"] == ""


@pytest.mark.django_db
def test_an_accommodations_reason_is_encrypted_at_rest(course_admin, student, client_for):
    """ASVS 6.1.2: a reason is often a health matter."""
    from django.db import connection

    admin = client_for(course_admin)
    made = admin.post(
        "/api/v1/accommodations/",
        {"person": student.id, "extra_days": 2, "reason": "Dyslexia"},
        format="json",
    )
    assert made.status_code == 201 and made.json()["reason"] == "Dyslexia"
    with connection.cursor() as cursor:
        cursor.execute("SELECT reason FROM assessments_accommodation")
        stored = bytes(cursor.fetchone()[0])
    assert b"Dyslexia" not in stored
    blank = admin.patch(f"/api/v1/accommodations/{made.json()['id']}/", {"reason": ""}, format="json")
    assert blank.json()["reason"] == ""
    assert "Dyslexia" not in str(list(AuditLog.objects.values_list("before", "after")))
