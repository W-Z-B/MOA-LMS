"""The phone's offline queue (item 3.15): the same record sent twice is saved once, and the phone's clock is
kept beside the server's but refused when it cannot be right."""

import json
import uuid

import pytest

from practicals.conftest import now_iso, photo, today_iso
from practicals.models import IdempotencyKey, LogbookEntry, LogbookPhoto, Observation


@pytest.mark.django_db
def test_an_observation_sent_twice_under_one_key_is_saved_once(task, passing, student, lecturer, client_for):
    teacher = client_for(lecturer.user)
    key = str(uuid.uuid4())
    body = {"student": student.id, "observed_at": now_iso(hours=-30), "results": passing}
    url = f"/api/v1/practical-tasks/{task.id}/observations/"
    first = teacher.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    again = teacher.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == again.status_code == 201
    assert again.json() == first.json() and again["Idempotent-Replay"] == "true"
    assert Observation.objects.count() == 1

    # The same key on a different record is refused; a new key makes a new attempt.
    changed = teacher.post(url, {**body, "comments": "x"}, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert changed.status_code == 409 and changed.json()["code"] == "idempotency_key_reused"
    elsewhere = teacher.post(f"/api/v1/observations/{first.json()['id']}/release/", HTTP_IDEMPOTENCY_KEY=key)
    assert elsewhere.json()["code"] == "idempotency_key_reused"
    assert teacher.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="not-a-uuid").json()["code"] == (
        "invalid_idempotency_key"
    )
    assert (
        teacher.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())).json()["attempt"] == 2
    )


@pytest.mark.django_db
def test_a_key_belongs_to_one_person(task, passing, student, lecturer, field_assessor, client_for):
    key = str(uuid.uuid4())
    body = {"student": student.id, "observed_at": now_iso(), "results": passing}
    url = f"/api/v1/practical-tasks/{task.id}/observations/"
    client_for(lecturer.user).post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    theirs = client_for(field_assessor.user).post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert theirs.status_code == 201 and theirs.json()["assessor_name"] == "Mark Bovell"
    assert Observation.objects.count() == 2


@pytest.mark.django_db
def test_the_phones_clock_is_refused_when_too_old_or_ahead(task, passing, student, observe):
    old = observe(task, student, passing, observed_at=now_iso(days=-7, minutes=-1))
    assert old.status_code == 400 and old.json()["code"] == "client_time_too_old"
    assert "more than 7 days ago" in old.json()["detail"]
    ahead = observe(task, student, passing, observed_at=now_iso(minutes=11))
    assert ahead.status_code == 400 and ahead.json()["code"] == "client_time_in_future"
    assert observe(task, student, passing, observed_at=now_iso(minutes=9)).status_code == 201
    assert observe(task, student, passing, observed_at=now_iso(days=-6, hours=-23)).status_code == 201


@pytest.mark.django_db
def test_a_refused_request_is_not_kept_so_it_can_be_corrected_and_sent_again(site, student, client_for):
    learner = client_for(student.user)
    key = str(uuid.uuid4())
    entry = {
        "site": site.id,
        "work_date": today_iso(),
        "unit_type": "pond",
        "unit_text": "Pond 2, tilapia",
        "task": "Fed fingerlings and checked oxygen",
        "hours": "2.5",
        "client_recorded_at": now_iso(days=-8),
        "idempotency_key": key,  # in the body, as a multipart form from the phone
        "photos": [photo("pond.jpg")],
    }
    refused = learner.post("/api/v1/logbook/", entry, format="multipart")
    assert refused.status_code == 400 and refused.json()["code"] == "client_time_too_old"
    assert not IdempotencyKey.objects.exists()

    entry["client_recorded_at"] = now_iso(hours=-3)
    entry["photos"] = [photo("pond.jpg")]
    saved = learner.post("/api/v1/logbook/", entry, format="multipart")
    assert saved.status_code == 201
    entry["photos"] = [photo("pond.jpg")]
    replayed = learner.post("/api/v1/logbook/", entry, format="multipart")
    assert replayed.status_code == 201 and replayed.json()["id"] == saved.json()["id"]
    assert LogbookEntry.objects.count() == 1 and LogbookPhoto.objects.count() == 1
    stored = LogbookEntry.objects.get()
    assert stored.client_recorded_at < stored.created_at


@pytest.mark.django_db
def test_sign_off_and_release_are_safe_to_resend(task, passing, student, lecturer, client_for, observe, site):
    teacher, learner = client_for(lecturer.user), client_for(student.user)
    made = observe(task, student, passing).json()
    key = str(uuid.uuid4())
    for _ in range(2):
        assert teacher.post(
            f"/api/v1/practical-tasks/{task.id}/release/", HTTP_IDEMPOTENCY_KEY=key
        ).json() == {"released": 1}
    assert Observation.objects.get(pk=made["id"]).is_released
    entry = learner.post(
        "/api/v1/logbook/",
        {
            "site": site.id,
            "work_date": today_iso(),
            "unit_type": "laboratory",
            "task": "Soil pH tests",
            "hours": "3",
            "client_recorded_at": now_iso(),
        },
        format="json",
    ).json()
    key = str(uuid.uuid4())
    body = json.dumps({"decision": "sign"})
    for _ in range(2):
        signed = teacher.post(
            f"/api/v1/logbook/{entry['id']}/review/",
            body,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        assert signed.status_code == 200 and signed.json()["status"] == "signed"
