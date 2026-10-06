"""Item 1.22: accounts opened from the person records, one-use links to choose a password, closure when the
record goes inactive."""

import re
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from conftest import PASSWORD
from courses.models import CourseSite, Membership
from iam import accounts
from iam.models import RoleScope, UserSession
from people.models import PersonRef

NEW_PASSWORD = "Fresh-Crop-Rotation-42"


@pytest.fixture
def people(seeded):
    site = CourseSite.objects.create(
        code="AGR201-T2", title="Soils", term_code="2026-27-S2", campus_code="MRP"
    )
    student = PersonRef.objects.create(
        kind="student",
        external_id="26MRP0101",
        first_name="Kamla",
        last_name="Das",
        email="k@x.gy",
        campus_code="MRP",
    )
    teacher = PersonRef.objects.create(
        kind="staff",
        external_id="E0101",
        first_name="Neil",
        last_name="Ram",
        email="n@x.gy",
        campus_code="MRP",
    )
    clerk = PersonRef.objects.create(
        kind="staff",
        external_id="E0102",
        first_name="Joy",
        last_name="Lall",
        email="j@x.gy",
        campus_code="MRP",
    )
    PersonRef.objects.create(
        kind="staff", external_id="E0103", first_name="No", last_name="Mail", campus_code="MRP"
    )
    PersonRef.objects.create(
        kind="student",
        external_id="26COR0001",
        first_name="Other",
        last_name="Campus",
        email="o@x.gy",
        campus_code="COR",
    )
    Membership.objects.create(site=site, person=teacher, role="lecturer")
    Membership.objects.create(site=site, person=student, role="student")
    return {"student": student, "teacher": teacher, "clerk": clerk, "site": site}


def link_from(message) -> tuple[str, str]:
    uid, token = re.search(r"/#/set-password/([^/\s]+)/(\S+)", message.body).groups()
    return uid, token


@pytest.mark.django_db
def test_everyone_uninvited_on_a_campus_gets_an_account_and_a_link(people, mailoutbox):
    counts = accounts.invite_all(None, campus_code="MRP")
    assert counts == {"invited": 3, "emailed": 3, "in_use": 0}
    student = PersonRef.objects.get(external_id="26MRP0101")
    assert student.user.username == "26MRP0101" and not student.user.has_usable_password()
    assert student.invited_at is not None
    roles = {
        p.external_id: sorted(RoleScope.objects.filter(user=p.user).values_list("role__code", flat=True))
        for p in PersonRef.objects.exclude(user=None)
    }
    # Students are students; staff who teach are lecturers; other staff have no system role.
    assert roles == {"26MRP0101": ["student"], "E0101": ["lecturer"], "E0102": []}
    assert len(mailoutbox) == 3 and "/#/set-password/" in mailoutbox[0].body
    assert AuditLog.objects.filter(action="account_invited").count() == 3
    # Asked again, nobody is invited twice; the person without an email address is left out.
    assert accounts.invite_all(None, campus_code="MRP")["invited"] == 0


@pytest.mark.django_db
def test_a_term_limits_the_invitations_to_the_people_on_its_sites(people, mailoutbox):
    assert accounts.invite_all(None, term_code="2026-27-S2")["invited"] == 2
    assert {m.to[0] for m in mailoutbox} == {"k@x.gy", "n@x.gy"}


@pytest.mark.django_db
def test_the_link_chooses_a_password_once(people, mailoutbox):
    accounts.invite(None, people["student"])
    uid, token = link_from(mailoutbox[0])
    client = APIClient()
    checked = client.post("/api/v1/auth/password/check/", {"uid": uid, "token": token}, format="json")
    assert checked.json() == {"username": "26MRP0101", "kind": "invitation"}
    weak = client.post(
        "/api/v1/auth/password/set/", {"uid": uid, "token": token, "password": "123"}, format="json"
    )
    assert weak.status_code == 400 and "password" in weak.json()
    done = client.post(
        "/api/v1/auth/password/set/", {"uid": uid, "token": token, "password": NEW_PASSWORD}, format="json"
    )
    assert done.status_code == 200
    again = client.post(
        "/api/v1/auth/password/set/", {"uid": uid, "token": token, "password": NEW_PASSWORD}, format="json"
    )
    assert again.status_code == 400 and again.json()["code"] == "invalid_link"
    login = client.post(
        "/api/v1/auth/login/", {"username": "26MRP0101", "password": NEW_PASSWORD}, format="json"
    )
    assert login.status_code == 200 and login.json()["roles"] == ["student"]
    # The account is now in use: a further invitation leaves it alone.
    assert accounts.invite(None, PersonRef.objects.get(pk=people["student"].pk))["outcome"] == "in_use"


@pytest.mark.django_db
def test_an_expired_or_forged_link_is_refused(people, mailoutbox, monkeypatch):
    accounts.invite(None, people["student"])
    uid, token = link_from(mailoutbox[0])
    client = APIClient()
    bad = client.post("/api/v1/auth/password/check/", {"uid": "zz", "token": token}, format="json")
    assert bad.status_code == 400
    forged = client.post("/api/v1/auth/password/check/", {"uid": uid, "token": "abc-def"}, format="json")
    assert forged.status_code == 400
    later = timezone.now() + timedelta(days=8)
    monkeypatch.setattr(accounts.LinkTokens, "_now", lambda self: later.replace(tzinfo=None))
    expired = client.post("/api/v1/auth/password/check/", {"uid": uid, "token": token}, format="json")
    assert expired.status_code == 400 and expired.json()["code"] == "invalid_link"


@pytest.mark.django_db
def test_forgotten_password_gives_the_same_answer_and_is_limited(student, settings, mailoutbox):
    settings.PASSWORD_RESETS_PER_ADDRESS = 3
    student.user.email = "ravi@students.gsa.edu.gy"
    student.user.save()
    client = APIClient()
    known = client.post("/api/v1/auth/password/forgot/", {"login": "26MRP0001"}, format="json")
    unknown = client.post("/api/v1/auth/password/forgot/", {"login": "nobody"}, format="json")
    assert known.json() == unknown.json() and known.status_code == 200
    assert len(mailoutbox) == 1 and "Choose a new password" in mailoutbox[0].subject
    uid, token = link_from(mailoutbox[0])
    kind = client.post("/api/v1/auth/password/check/", {"uid": uid, "token": token}, format="json").json()
    assert kind["kind"] == "reset"
    client.post("/api/v1/auth/password/forgot/", {"login": "ravi@students.gsa.edu.gy"}, format="json")
    blocked = client.post("/api/v1/auth/password/forgot/", {"login": "26MRP0001"}, format="json")
    assert blocked.status_code == 429 and blocked.json()["code"] == "too_many_attempts"


@pytest.mark.django_db
def test_one_account_is_sent_only_so_many_links(student, settings, mailoutbox):
    settings.PASSWORD_RESETS_PER_ACCOUNT = 1
    for _ in range(3):
        APIClient().post("/api/v1/auth/password/forgot/", {"login": "26MRP0001"}, format="json")
    assert len(mailoutbox) == 1


@pytest.mark.django_db
def test_changing_my_password_needs_the_current_one(student, client_for):
    client = client_for(student.user)
    wrong = client.post(
        "/api/v1/auth/password/change/",
        {"current_password": "nope", "new_password": NEW_PASSWORD},
        format="json",
    )
    assert wrong.status_code == 400 and wrong.json()["code"] == "wrong_password"
    ok = client.post(
        "/api/v1/auth/password/change/",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert ok.status_code == 200
    student.user.refresh_from_db()
    assert student.user.check_password(NEW_PASSWORD)


@pytest.mark.django_db
def test_an_inactive_record_closes_the_account_and_its_sessions(student):
    client = APIClient()
    client.post("/api/v1/auth/login/", {"username": "26MRP0001", "password": PASSWORD}, format="json")
    assert UserSession.objects.filter(user=student.user).count() == 1
    student.is_active = False
    student.save()
    user = get_user_model().objects.get(pk=student.user_id)
    assert user.is_active is False and not UserSession.objects.filter(user=user).exists()
    assert client.get("/api/v1/auth/me/").status_code == 403
    assert AuditLog.objects.filter(action="account_closed", entity_id=user.pk).exists()
    refused = client.post(
        "/api/v1/auth/login/", {"username": "26MRP0001", "password": PASSWORD}, format="json"
    )
    assert refused.status_code == 401


@pytest.mark.django_db
def test_only_administrators_invite_from_the_api(people, make_user, client_for, mailoutbox):
    admin, course_admin = make_user("admin", "administrator"), make_user("ca", "course_admin")
    assert (
        client_for(course_admin).post("/api/v1/auth/accounts/invite/", {"campus_code": "MRP"}).status_code
        == 403
    )
    client = client_for(admin)
    assert client.get("/api/v1/auth/accounts/uninvited/?campus_code=MRP").json() == {
        "count": 3,
        "without_email": 1,
    }
    assert client.post("/api/v1/auth/accounts/invite/", {}, format="json").status_code == 400
    sent = client.post("/api/v1/auth/accounts/invite/", {"campus_code": "MRP"}, format="json")
    assert sent.json() == {"invited": 3, "emailed": 3, "in_use": 0}

    nomail = PersonRef.objects.get(external_id="E0103")
    assert client.post(f"/api/v1/auth/accounts/invite/{nomail.pk}/").json()["code"] == "no_email"
    clerk = people["clerk"]
    again = client.post(f"/api/v1/auth/accounts/invite/{clerk.pk}/")
    assert again.status_code == 200 and again.json()["outcome"] == "invited"  # never used: sent again
    clerk.refresh_from_db()
    clerk.is_active = False
    clerk.save()
    assert client.post(f"/api/v1/auth/accounts/invite/{clerk.pk}/").status_code == 409


@pytest.mark.django_db
def test_a_returning_person_is_invited_back_into_a_closed_unused_account(people, mailoutbox):
    clerk = people["clerk"]
    accounts.invite(None, clerk)
    clerk.refresh_from_db()
    clerk.is_active = False
    clerk.save()
    clerk.is_active = True
    clerk.save()
    assert accounts.invite(None, clerk)["outcome"] == "invited"
    clerk.user.refresh_from_db()
    assert clerk.user.is_active


@pytest.mark.django_db
def test_the_command_invites_a_campus(people, mailoutbox, capsys):
    from django.core.management import CommandError

    with pytest.raises(CommandError):
        call_command("invite_people")
    call_command("invite_people", campus="MRP", dry_run=True)
    assert "3 people would be invited" in capsys.readouterr().out and not mailoutbox
    call_command("invite_people", campus="MRP")
    assert len(mailoutbox) == 3


@pytest.mark.django_db
def test_a_username_already_taken_is_numbered_on(people, make_user):
    make_user("26MRP0101")
    accounts.invite(None, people["student"])
    assert PersonRef.objects.get(external_id="26MRP0101").user.username == "26MRP0101-2"
