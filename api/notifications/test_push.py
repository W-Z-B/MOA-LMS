"""Push notices to the installed app (item 4.04): turned on per device and per kind, sent by the job worker
for marks, announcements and reminders, and dropped when the push service says a subscription is gone."""

import json
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from pywebpush import WebPushException
from requests import ConnectionError as NetworkDown

from audit.models import AuditLog
from notifications import push, tasks
from notifications.management.commands.vapid_keys import make_keys
from notifications.models import Notification, NotificationPreference, PushSubscription
from notifications.services import notify

ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"
KEYS = {"p256dh": "BOr" + "x" * 84, "auth": "secret-auth-16b"}


@pytest.fixture(autouse=True)
def public_push_services(monkeypatch):
    """The push services' names look up to a public address (no network in the tests)."""
    from core import outbound

    monkeypatch.setattr(outbound, "resolve", lambda host, port, **k: [(2, 1, 6, "", ("142.250.0.10", port))])


@pytest.fixture
def vapid(settings):
    settings.VAPID_PUBLIC_KEY, settings.VAPID_PRIVATE_KEY = make_keys()
    return settings


@pytest.fixture
def person(make_person):
    return make_person("student", "26MRP0060", "Kezia", "Ram", "student")


@pytest.fixture
def phone(person, client_for):
    return client_for(person.user)


@pytest.fixture
def deferred(monkeypatch):
    jobs = []
    monkeypatch.setattr(tasks.send_push, "defer", lambda **kw: jobs.append(kw))
    return jobs


def subscribe(client, endpoint=ENDPOINT, **extra):
    data = {"endpoint": endpoint, "keys": KEYS, "device": "Chrome on Android", **extra}
    return client.post("/api/v1/notifications/push/subscribe/", data, format="json")


@pytest.mark.django_db
def test_push_is_off_until_the_server_has_its_keys(phone, settings):
    assert phone.get("/api/v1/notifications/push/").json() == {
        "available": False,
        "public_key": None,
        "devices": 0,
    }
    refused = subscribe(phone)
    assert refused.status_code == 409 and refused.json()["code"] == "push_off"
    assert not PushSubscription.objects.exists()


@pytest.mark.django_db
def test_a_device_turns_push_on_and_off(phone, person, vapid):
    state = phone.get("/api/v1/notifications/push/").json()
    assert state["available"] is True and state["public_key"] == vapid.VAPID_PUBLIC_KEY
    created = subscribe(phone)
    assert created.status_code == 201 and created.json()["devices"] == 1
    saved = PushSubscription.objects.get()
    assert saved.user == person.user and saved.auth == KEYS["auth"] and saved.device == "Chrome on Android"
    entry = AuditLog.objects.get(entity="notifications.pushsubscription", action="create")
    assert ENDPOINT not in json.dumps(entry.after) and entry.after["endpoint"].startswith("***")
    assert subscribe(phone).json()["devices"] == 1  # the same browser again changes nothing
    off = phone.post("/api/v1/notifications/push/unsubscribe/", {"endpoint": ENDPOINT}, format="json")
    assert off.status_code == 200 and off.json()["devices"] == 0
    assert AuditLog.objects.filter(entity="notifications.pushsubscription", action="delete").exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/abc",  # not https
        "https://169.254.169.254/latest/meta-data",  # an address of someone's choosing
        "https://fcm.googleapis.com.evil.example/x",
        "https://fcm.googleapis.com:8443/x",
    ],
)
def test_only_the_browsers_push_services_are_accepted(phone, vapid, endpoint):
    refused = subscribe(phone, endpoint=endpoint)
    assert refused.status_code == 400 and "push service" in str(refused.json())


@pytest.mark.django_db
def test_a_shared_browser_belongs_to_whoever_turned_push_on_last(
    phone, person, make_person, client_for, vapid
):
    subscribe(phone)
    other = make_person("student", "26MRP0061", "Tevin", "Joseph", "student")
    subscribe(client_for(other.user), endpoint=ENDPOINT)
    assert list(PushSubscription.objects.values_list("user", flat=True)) == [other.user.id]
    assert phone.get("/api/v1/notifications/push/").json()["devices"] == 0
    assert subscribe(phone, endpoint="https://web.push.apple.com/QGx").status_code == 201
    assert subscribe(phone, endpoint="https://wns2-par02p.notify.windows.com/w/?token=x").status_code == 201


@pytest.mark.django_db
def test_notify_pushes_only_the_kinds_the_person_chose(
    phone, person, vapid, deferred, django_capture_on_commit_callbacks
):
    subscribe(phone)
    NotificationPreference.objects.create(user=person.user, kind="mark", push=True)
    with django_capture_on_commit_callbacks(execute=True):
        marked = notify([person.user], title="Marked: Soil report", kind=Notification.Kind.MARK)
        notify([person.user], title="Due soon", kind=Notification.Kind.REMINDER)
    assert deferred == [{"notification_id": marked[0].id}]
    PushSubscription.objects.all().delete()  # no device: nothing to push to
    with django_capture_on_commit_callbacks(execute=True):
        notify([person.user], title="Marked again", kind=Notification.Kind.MARK)
    assert len(deferred) == 1


@pytest.mark.django_db
def test_announcements_reminders_and_marks_are_kinds_of_their_own(phone, person, lecturer, client_for, site):
    teacher = client_for(lecturer.user)
    from courses.models import Membership

    Membership.objects.create(site=site, person=person, role="student")
    made = teacher.post(
        "/api/v1/announcements/",
        {"site": site.id, "title": "Field trip", "body": "Bring boots."},
        format="json",
    )
    assert made.status_code == 201
    note = Notification.objects.get(recipient=person.user)
    assert note.kind == "announcement"
    kinds = [r["kind"] for r in phone.get("/api/v1/notifications/preferences/").json()]
    assert {"announcement", "mark", "reminder"} <= set(kinds)


@pytest.mark.django_db
def test_the_worker_sends_the_title_and_the_link_and_drops_gone_subscriptions(person, vapid, monkeypatch):
    for n in range(3):
        PushSubscription.objects.create(user=person.user, endpoint=f"{ENDPOINT}{n}", **KEYS)
    note = Notification.objects.create(
        recipient=person.user, kind="mark", title="Marked: Soil report", body="47 out of 50.", link="/sites/4"
    )
    sent = []

    def webpush(subscription_info, data, vapid_private_key, vapid_claims, ttl, timeout, requests_session):
        assert requests_session.max_redirects == 0 and requests_session.trust_env is False
        sent.append(json.loads(data))
        assert vapid_private_key == vapid.VAPID_PRIVATE_KEY and vapid_claims == {"sub": vapid.VAPID_SUBJECT}
        assert subscription_info["keys"] == KEYS
        end = subscription_info["endpoint"]
        if end.endswith("1"):
            raise WebPushException("gone", response=SimpleNamespace(status_code=410))
        if end.endswith("2"):
            raise NetworkDown("no route")

    monkeypatch.setattr("pywebpush.webpush", webpush)
    assert tasks.send_push(notification_id=note.id) == 1
    assert sent[0] == {"title": "Marked: Soil report", "link": "/sites/4", "tag": f"gsa-lms-{note.id}"}
    assert "47 out of 50" not in json.dumps(sent)  # the mark stays behind sign-in
    left = {s.endpoint: s for s in PushSubscription.objects.all()}
    assert set(left) == {f"{ENDPOINT}0", f"{ENDPOINT}2"}
    assert left[f"{ENDPOINT}0"].last_sent_at is not None and left[f"{ENDPOINT}2"].failures == 1
    left[f"{ENDPOINT}2"].failures = push.MAX_FAILURES - 1
    left[f"{ENDPOINT}2"].save()
    push.send(note)
    assert not PushSubscription.objects.filter(endpoint=f"{ENDPOINT}2").exists()  # failing for good
    assert tasks.send_push(notification_id=999999) == 0


@pytest.mark.django_db
def test_nothing_is_sent_without_keys(person, settings, monkeypatch):
    PushSubscription.objects.create(user=person.user, endpoint=ENDPOINT, **KEYS)
    note = Notification.objects.create(recipient=person.user, title="x")
    monkeypatch.setattr("pywebpush.webpush", lambda **kw: pytest.fail("sent without keys"))
    assert push.send(note) == 0
    assert push.wanted(person.user, "info") is False


def test_vapid_keys_are_a_p256_pair_in_base64url():
    out = StringIO()
    call_command("vapid_keys", stdout=out)
    public = out.getvalue().split("VAPID_PUBLIC_KEY=")[1].split()[0]
    private = out.getvalue().split("VAPID_PRIVATE_KEY=")[1].split()[0]
    assert len(public) == 87 and len(private) == 43 and "=" not in public + private
