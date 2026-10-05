"""The calendar (item 2.32): due dates, classes and release dates as the person may see them, and the private
feed for phone calendars."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from attendance.models import ClassSession
from audit.models import AuditLog
from calendars.models import CalendarFeed
from calendars.services import _fold, ical


@pytest.fixture(autouse=True)
def _fresh_throttles():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def dated(site, student, assignment):
    """One of everything on the calendar, some of it hidden from the student."""
    from assessments.models import Assignment
    from courses.models import ContentItem, Membership, Module, SiteGroup
    from practicals.models import PracticalTask
    from quizzes.models import Quiz, QuizOverride

    soon = timezone.now() + timedelta(days=3)
    Assignment.objects.create(site=site, title="Draft essay", due_at=soon, is_published=False)
    quiz = Quiz.objects.create(site=site, title="Week 2 quiz", closes_at=soon, is_published=True)
    QuizOverride.objects.create(quiz=quiz, student=student, closes_at=soon + timedelta(days=2))
    Quiz.objects.create(site=site, title="Unpublished quiz", closes_at=soon)
    PracticalTask.objects.create(
        site=site, title="Prepare a bed", closes_at=soon, is_published=True, location="Plot 7"
    )
    lab = SiteGroup.objects.create(site=site, name="Lab A")
    other = SiteGroup.objects.create(site=site, name="Lab B")
    lab.members.add(Membership.objects.get(site=site, person=student))
    ClassSession.objects.create(
        site=site,
        title="Lecture",
        starts_at=soon,
        ends_at=soon + timedelta(hours=1),
        meeting_url="https://meet.example.org/x",
        location="Hall 1",
    )
    ClassSession.objects.create(
        site=site, title="Lab B practical", group=other, starts_at=soon, ends_at=soon + timedelta(hours=2)
    )
    module = Module.objects.create(site=site, title="Week 5", available_from=soon)
    hidden_module = Module.objects.create(site=site, title="Lab B notes", available_from=soon)
    hidden_module.groups.add(other)
    ContentItem.objects.create(module=module, title="Fertiliser page", available_from=soon)
    ContentItem.objects.create(
        module=module, title="Unpublished page", available_from=soon, is_published=False
    )
    ContentItem.objects.create(module=hidden_module, title="Lab B sheet", available_from=soon)
    return quiz


@pytest.mark.django_db
def test_a_students_calendar_shows_what_they_may_see(dated, client_for, student, lecturer):
    events = client_for(student.user).get("/api/v1/calendar/").json()
    titles = {e["title"] for e in events}
    assert titles == {
        "Due: Soil sampling report",
        "Quiz closes: Week 2 quiz",
        "Practical closes: Prepare a bed",
        "Lecture",
        "Opens: Week 5",
        "Opens: Fertiliser page",
    }
    quiz = next(e for e in events if e["kind"] == "quiz_closes")
    assert (
        quiz["starts_at"] > next(e for e in events if e["kind"] == "practical_closes")["starts_at"]
    )  # extension
    lecture = next(e for e in events if e["kind"] == "class_session")
    assert lecture["meeting_url"] == "https://meet.example.org/x" and lecture["ends_at"]

    staff = {e["title"] for e in client_for(lecturer.user).get("/api/v1/calendar/").json()}
    assert {
        "Due: Draft essay",
        "Quiz closes: Unpublished quiz",
        "Lab B practical",
        "Opens: Lab B notes",
        "Opens: Lab B sheet",
        "Opens: Unpublished page",
    } <= staff


@pytest.mark.django_db
def test_the_calendar_period_is_checked(dated, client_for, student):
    client = client_for(student.user)
    now = timezone.now()
    nothing = client.get("/api/v1/calendar/", {"from": (now + timedelta(days=30)).isoformat()})
    assert nothing.json() == []
    backwards = client.get(
        "/api/v1/calendar/", {"from": now.isoformat(), "to": (now - timedelta(days=1)).isoformat()}
    )
    assert backwards.status_code == 400 and backwards.json()["code"] == "bad_period"
    too_long = client.get("/api/v1/calendar/", {"to": (now + timedelta(days=500)).isoformat()})
    assert too_long.status_code == 400
    assert client.get("/api/v1/calendar/", {"from": "next tuesday"}).status_code == 400
    naive = client.get("/api/v1/calendar/", {"from": "2026-01-01T00:00:00", "to": "2026-02-01T00:00:00"})
    assert naive.status_code == 200


@pytest.mark.django_db
def test_the_private_feed_needs_no_sign_in_and_can_be_rotated_or_turned_off(dated, client_for, student):
    from rest_framework.test import APIClient

    owner = client_for(student.user)
    assert owner.get("/api/v1/calendar/feed/").json()["url"] is None
    made = owner.post("/api/v1/calendar/feed/")
    assert made.status_code == 201
    url = made.json()["url"]
    assert owner.get("/api/v1/calendar/feed/").json()["url"] == url
    feed = CalendarFeed.objects.get()
    assert feed.token_hash not in url and feed.token in url

    phone = APIClient()  # no session
    body = phone.get(url)
    assert body.status_code == 200 and body["Content-Type"].startswith("text/calendar")
    text = body.content.decode()
    assert text.startswith("BEGIN:VCALENDAR\r\n") and "SUMMARY:AGR101-2026-27-S1-MRP: Lecture" in text
    assert "Lab B practical" not in text and "LOCATION:Hall 1" in text
    assert CalendarFeed.objects.get().last_used_at is not None
    assert phone.post(url).status_code == 405  # read-only

    rotated = owner.post("/api/v1/calendar/feed/").json()["url"]
    assert rotated != url
    assert phone.get(url).status_code == 404 and phone.get(rotated).status_code == 200
    assert owner.delete("/api/v1/calendar/feed/").status_code == 204
    assert phone.get(rotated).status_code == 404
    assert owner.delete("/api/v1/calendar/feed/").status_code == 204
    assert AuditLog.objects.filter(action__startswith="calendar_feed").count() == 3

    owner.post("/api/v1/calendar/feed/")
    student.user.is_active = False
    student.user.save()
    assert phone.get(f"/api/v1/calendar/feed/{CalendarFeed.objects.get().token}.ics").status_code == 404


@pytest.mark.django_db
def test_the_feed_is_rate_limited(dated, client_for, student):
    from rest_framework.test import APIClient

    url = client_for(student.user).post("/api/v1/calendar/feed/").json()["url"]
    phone = APIClient()
    codes = [phone.get(url).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429
    cache.clear()
    guesses = [phone.get(f"/api/v1/calendar/feed/guess{n}.ics").status_code for n in range(121)]
    assert set(guesses[:120]) == {404} and guesses[120] == 429


def test_long_lines_are_folded_and_text_is_escaped():
    line = "SUMMARY:" + "é" * 80
    folded = _fold(line)
    assert all(len(part.encode()) <= 75 for part in folded.split("\r\n "))
    assert folded.replace("\r\n ", "") == line
    from calendars.services import Event

    when = timezone.now()
    text = ical([Event("release", 1, 1, "AGR101", "Opens: A; B, C\\D", when)], "https://lms.example")
    assert "SUMMARY:AGR101: Opens: A\\; B\\, C\\\\D" in text and "DTEND" not in text
