"""Signed-in sessions: listed, ended from another device, and ended when idle or too old (item 1.07)."""

import time

import pytest
from rest_framework.test import APIClient

from audit.models import AuditLog
from conftest import PASSWORD
from iam.models import UserSession
from iam.sessions import LAST_ACTIVITY, SIGNED_IN_AT, describe_device

ANDROID_CHROME = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Chrome/126.0 Mobile Safari/537.36"
)
WINDOWS_EDGE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36 Edg/126.0"
)


def device(username: str, agent: str = ANDROID_CHROME, address: str = "190.80.1.2") -> APIClient:
    client = APIClient(HTTP_USER_AGENT=agent, HTTP_X_REAL_IP=address)
    response = client.post("/api/v1/auth/login/", {"username": username, "password": PASSWORD}, format="json")
    assert response.status_code == 200
    return client


def age_session(client: APIClient, **seconds_ago: float) -> None:
    session = client.session
    for key, ago in seconds_ago.items():
        session[key] = time.time() - ago
    session.save()


@pytest.mark.django_db
def test_sign_in_records_the_session_and_lists_it_as_this_device(student):
    phone = device("26MRP0001")
    rows = phone.get("/api/v1/auth/sessions/").json()
    assert len(rows) == 1
    assert rows[0]["current"] is True
    assert rows[0]["device"] == "Chrome on Android"
    assert rows[0]["ip"] == "190.80.1.2"


@pytest.mark.django_db
def test_ending_another_session_signs_that_device_out(student):
    phone = device("26MRP0001")
    laptop = device("26MRP0001", WINDOWS_EDGE, "190.80.9.9")
    rows = phone.get("/api/v1/auth/sessions/").json()
    other = next(row for row in rows if not row["current"])
    assert other["device"] == "Edge on Windows"

    assert phone.delete(f"/api/v1/auth/sessions/{other['id']}/").status_code == 204
    refused = laptop.get("/api/v1/auth/me/")
    assert refused.status_code == 403 and refused.json()["code"] == "not_authenticated"
    assert phone.get("/api/v1/auth/me/").status_code == 200
    assert AuditLog.objects.filter(action="session_ended", actor=student.user).exists()


@pytest.mark.django_db
def test_people_cannot_end_someone_elses_session_or_their_own_here(student, other_student):
    mine = device("26MRP0001")
    theirs = device("26MRP0002")
    their_id = theirs.get("/api/v1/auth/sessions/").json()[0]["id"]
    my_id = mine.get("/api/v1/auth/sessions/").json()[0]["id"]

    refused = mine.delete(f"/api/v1/auth/sessions/{their_id}/")
    assert refused.status_code == 404 and refused.json()["code"] == "not_found"
    own = mine.delete(f"/api/v1/auth/sessions/{my_id}/")
    assert own.status_code == 409 and own.json()["code"] == "current_session"
    assert theirs.get("/api/v1/auth/me/").status_code == 200


@pytest.mark.django_db
def test_sign_out_everywhere_else(student):
    phone = device("26MRP0001")
    laptop = device("26MRP0001", WINDOWS_EDGE)
    tablet = device("26MRP0001")
    assert phone.post("/api/v1/auth/sessions/end-others/").json() == {"ended": 2}
    assert laptop.get("/api/v1/auth/me/").status_code == 403
    assert tablet.get("/api/v1/auth/me/").status_code == 403
    assert phone.get("/api/v1/auth/me/").status_code == 200
    assert UserSession.objects.filter(user=student.user).count() == 1
    assert AuditLog.objects.filter(action="sessions_ended", actor=student.user).exists()


@pytest.mark.django_db
def test_an_idle_session_ends_with_the_reason(student, settings):
    settings.SESSION_IDLE_MINUTES = 30
    phone = device("26MRP0001")
    age_session(phone, **{LAST_ACTIVITY: 31 * 60})
    ended = phone.get("/api/v1/sites/")
    assert ended.status_code == 401
    assert ended.json() == {
        "code": "session_expired",
        "detail": "You were signed out after 30 minutes without activity.",
    }
    assert not UserSession.objects.filter(user=student.user).exists()
    assert phone.get("/api/v1/auth/me/").status_code == 403


@pytest.mark.django_db
def test_a_busy_session_still_ends_at_the_absolute_limit(student, settings):
    settings.SESSION_COOKIE_AGE = 8 * 60 * 60
    phone = device("26MRP0001")
    age_session(phone, **{SIGNED_IN_AT: 8 * 60 * 60 + 5, LAST_ACTIVITY: 10})
    ended = phone.get("/api/v1/sites/")
    assert ended.status_code == 401
    assert "time limit" in ended.json()["detail"]


@pytest.mark.django_db
def test_activity_keeps_a_session_alive_and_older_sessions_join_the_list(student):
    phone = device("26MRP0001")
    UserSession.objects.all().delete()  # as for a session that signed in before the list existed
    session = phone.session
    del session[LAST_ACTIVITY]
    session.save()
    assert phone.get("/api/v1/sites/").status_code == 200
    assert UserSession.objects.filter(user=student.user).count() == 1


@pytest.mark.django_db
def test_signing_out_removes_the_session_from_the_list(student):
    phone = device("26MRP0001")
    assert phone.post("/api/v1/auth/logout/").status_code == 204
    assert not UserSession.objects.exists()


@pytest.mark.django_db
def test_a_role_given_or_taken_away_signs_the_person_out_everywhere(student):
    from iam.models import Role, RoleScope

    phone = device("26MRP0001")
    laptop = device("26MRP0001", WINDOWS_EDGE)
    grant = RoleScope.objects.create(user=student.user, role=Role.objects.get(code=Role.AUDITOR))
    assert phone.get("/api/v1/auth/me/").status_code == 403
    assert laptop.get("/api/v1/auth/me/").status_code == 403

    again = device("26MRP0001")
    grant.delete()
    assert again.get("/api/v1/auth/me/").status_code == 403
    assert not UserSession.objects.filter(user=student.user).exists()


def test_devices_are_described_in_plain_words():
    assert describe_device(ANDROID_CHROME) == "Chrome on Android"
    assert describe_device(WINDOWS_EDGE) == "Edge on Windows"
    assert describe_device("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1") == (
        "Safari on iPhone or iPad"
    )
    assert describe_device("Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0") == (
        "Firefox on Linux"
    )
    assert describe_device("") == "Unknown device"
