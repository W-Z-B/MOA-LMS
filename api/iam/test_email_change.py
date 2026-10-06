"""Item 1.10: the sign-in email changes only once the new address confirms it, and the old one is told.
Ported from the HRMS's tests of its item 1.42."""

import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from conftest import PASSWORD
from iam.models import EmailChange, LoginAttempt

CHANGE = "/api/v1/auth/email/change/"
CONFIRM = "/api/v1/auth/email/confirm/"


def _token(message) -> str:
    return re.search(r"/#/confirm-email/(\S+)", message.body).group(1)


def _confirm(token):
    return APIClient().post(CONFIRM, {"token": token}, format="json")


@pytest.fixture
def asha(make_person):
    person = make_person("staff", "E0420", "Asha", "Persaud", email="asha@gsa.example")
    person.user.first_name = "Asha"
    person.user.save(update_fields=["first_name"])
    return person.user


@pytest.mark.django_db
def test_a_person_changes_their_sign_in_email_once_the_new_address_confirms_it(asha, client_for):
    client = client_for(asha)
    wrong = client.post(CHANGE, {"email": "asha.new@gsa.example", "password": "not it"}, format="json")
    assert wrong.status_code == 400 and wrong.json()["code"] == "wrong_password"
    assert LoginAttempt.objects.filter(username=asha.username, success=False).count() == 1
    assert AuditLog.objects.filter(action="email_change_failed").count() == 1
    assert not mail.outbox

    asked = client.post(CHANGE, {"email": "Asha.New@GSA.example", "password": PASSWORD}, format="json")
    assert asked.status_code == 200, asked.content
    assert asked.json()["emailed"] and asked.json()["pending"]["new_email"] == "Asha.New@gsa.example"
    assert "sent to Asha.New@gsa.example" in asked.json()["detail"]
    link, told = mail.outbox
    assert (
        link.to == ["Asha.New@gsa.example"] and "/#/confirm-email/" in link.body and "48 hours" in link.body
    )
    assert link.subject.startswith("[GSA LMS]")
    assert told.to == ["asha@gsa.example"] and "As…@gsa.example" in told.body
    assert "You asked" in told.body and "confirm-email" not in told.body
    asha.refresh_from_db()
    assert asha.email == "asha@gsa.example"  # nothing changes until the link is followed
    assert client.get("/api/v1/auth/email/").json()["pending"]["new_email"] == "Asha.New@gsa.example"

    token = _token(link)
    done = _confirm(token)
    assert done.status_code == 200, done.content
    assert done.json() == {
        "detail": "The sign-in email address is now Asha.New@gsa.example.",
        "email": "Asha.New@gsa.example",
    }
    asha.refresh_from_db()
    assert asha.email == "Asha.New@gsa.example"
    assert asha.person.email == "asha@gsa.example"  # the person record follows the HRMS, not the account
    assert mail.outbox[-1].to == ["asha@gsa.example"] and "has changed" in mail.outbox[-1].subject
    assert _confirm(token).json()["code"] == "expired"  # once only
    changed = AuditLog.objects.get(action="sign_in_email_changed")
    assert changed.before == {"email": "asha@gsa.example"}
    assert changed.after == {"email": "Asha.New@gsa.example"}
    assert AuditLog.objects.get(action="email_change_asked").after == {"new_email": "Asha.New@gsa.example"}
    assert client.get("/api/v1/auth/email/").json() == {"email": "Asha.New@gsa.example", "pending": None}


@pytest.mark.django_db
def test_only_the_latest_link_works_and_only_in_time(asha, make_user, client_for, settings):
    client = client_for(asha)

    def ask(address):
        return client.post(CHANGE, {"email": address, "password": PASSWORD}, format="json")

    ask("first@gsa.example")
    first = _token(mail.outbox[-2])
    ask("second@gsa.example")
    second = _token(mail.outbox[-2])
    assert _confirm(first).json()["code"] == "expired"  # replaced by the newer request
    EmailChange.objects.filter(new_email="second@gsa.example").update(
        asked_at=timezone.now() - timedelta(hours=settings.EMAIL_CHANGE_HOURS + 1)
    )
    assert _confirm(second).json()["code"] == "expired"
    assert client.get("/api/v1/auth/email/").json()["pending"] is None
    assert _confirm("not-a-token").status_code == 400

    make_user("someone.else", email="taken@gsa.example")
    taken = ask("TAKEN@gsa.example")
    assert taken.status_code == 409 and taken.json()["code"] == "taken"
    assert ask("asha@gsa.example").json()["code"] == "same"
    assert ask("not an address").status_code == 400

    settings.LOGIN_MAX_FAILURES = 2
    for _ in range(2):
        client.post(CHANGE, {"email": "third@gsa.example", "password": "wrong"}, format="json")
    locked = ask("third@gsa.example")
    assert locked.status_code == 429 and locked.json()["code"] == "too_many_attempts"


@pytest.mark.django_db
def test_a_link_for_an_account_since_closed_or_an_address_since_taken_changes_nothing(
    asha, make_user, client_for
):
    client = client_for(asha)
    client.post(CHANGE, {"email": "asha.later@gsa.example", "password": PASSWORD}, format="json")
    token = _token(mail.outbox[0])
    other = make_user("quick.one", email="asha.later@gsa.example")
    taken = _confirm(token)
    assert taken.status_code == 409 and taken.json()["code"] == "taken"
    other.delete()
    asha.is_active = False
    asha.save(update_fields=["is_active"])
    assert _confirm(token).json()["code"] == "switched_off"
    asha.refresh_from_db()
    assert asha.email == "asha@gsa.example"


@pytest.mark.django_db
def test_a_change_is_told_to_nobody_when_the_account_had_no_address(make_user, client_for):
    user = make_user("no.mail.yet")
    client_for(user).post(CHANGE, {"email": "first.ever@gsa.example", "password": PASSWORD}, format="json")
    assert [m.to for m in mail.outbox] == [["first.ever@gsa.example"]]
    assert _confirm(_token(mail.outbox[0])).status_code == 200
    assert len(mail.outbox) == 1  # no old address to tell


@pytest.mark.django_db
def test_a_link_that_cannot_be_sent_says_so(asha, client_for, monkeypatch):
    from iam import email_change

    monkeypatch.setattr(email_change, "send_mail", lambda *a, **k: 0)
    asked = client_for(asha).post(CHANGE, {"email": "lost@gsa.example", "password": PASSWORD}, format="json")
    assert asked.status_code == 200 and asked.json()["emailed"] is False
    assert asked.json()["detail"].startswith("The link could not be sent")

    def broken(*args, **kwargs):
        raise OSError("no mail server")

    monkeypatch.setattr(email_change, "send_mail", broken)
    assert email_change._mail("x@gsa.example", "Subject", ["Line"]) is False
    assert email_change.hidden("nobody") == "another address"


@pytest.mark.django_db
def test_old_requests_go_with_the_sign_in_records(asha, client_for):
    from privacy.retention import purge

    client_for(asha).post(CHANGE, {"email": "asha.new@gsa.example", "password": PASSWORD}, format="json")
    EmailChange.objects.update(asked_at=timezone.now() - timedelta(days=800))
    LoginAttempt.objects.all().delete()
    assert purge()["login-attempts"] >= 1 and not EmailChange.objects.exists()
    assert str(EmailChange(user=asha, new_email="x@gsa.example")).endswith("to x@gsa.example")
