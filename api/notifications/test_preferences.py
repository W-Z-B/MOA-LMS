"""Notification settings per person (item 2.33), the daily summary, and reminders before a due date (2.34)."""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from assessments.models import Accommodation, Assignment, Submission
from notifications.models import Notification, NotificationPreference
from notifications.services import notify, send_daily_summaries


@pytest.mark.django_db
def test_each_person_chooses_how_each_kind_arrives(make_person, client_for):
    person = make_person("student", "26MRP0050", "Asha", "Ram", "student", email="asha@students.gsa.edu.gy")
    client = client_for(person.user)
    rows = client.get("/api/v1/notifications/preferences/").json()
    marks = next(r for r in rows if r["kind"] == "mark")
    assert marks == {
        "kind": "mark",
        "label": "Marks and feedback",
        "in_app": True,
        "email": "instant",
        "push": False,
    }
    changed = client.put(
        "/api/v1/notifications/preferences/",
        [
            {"kind": "mark", "email": "daily", "push": True},
            {"kind": "reminder", "email": "off", "push": False},
        ],
        format="json",
    )
    assert changed.status_code == 200
    assert next(r for r in changed.json() if r["kind"] == "mark")["email"] == "daily"
    assert (
        client.put(
            "/api/v1/notifications/preferences/", [{"kind": "x", "email": "off"}], format="json"
        ).status_code
        == 400
    )

    mail.outbox.clear()
    notify([person.user], title="Marked: Report", kind="mark")
    notify([person.user], title="Due soon", kind="reminder")
    notify([person.user], title="Announcement", body="Field trip", kind="info", link="/sites/1")
    # In the app all three; by email only the one left at once.
    assert Notification.objects.filter(recipient=person.user).count() == 3
    assert [m.subject for m in mail.outbox] == ["[GSA LMS] Announcement"]
    held = Notification.objects.get(title="Marked: Report")
    assert held.in_summary and not held.emailed

    mail.outbox.clear()
    assert send_daily_summaries() == 1
    assert "Marked: Report" in mail.outbox[0].body and "Due soon" not in mail.outbox[0].body
    assert Notification.objects.get(pk=held.pk).summarised_at is not None
    assert send_daily_summaries() == 0  # nothing new since the last summary
    assert NotificationPreference.objects.filter(user=person.user).count() == 2


@pytest.mark.django_db
def test_a_long_summary_lists_fifty_and_counts_the_rest(make_person):
    person = make_person("student", "26MRP0051", "Devi", "Lall", "student", email="devi@students.gsa.edu.gy")
    NotificationPreference.objects.create(user=person.user, kind="info", email="daily")
    for n in range(52):
        notify([person.user], title=f"Note {n}")
    mail.outbox.clear()
    from notifications.tasks import daily_summary

    assert daily_summary() == 1
    assert (
        "... and 2 more in the app." in mail.outbox[0].body and "52 notifications" in mail.outbox[0].subject
    )


@pytest.mark.django_db
def test_reminders_before_a_due_date_go_once_to_those_who_have_not_handed_in(
    site, assignment, student, other_student
):
    from assessments.tasks import due_reminders, send_due_reminders

    now = timezone.now()
    Assignment.objects.filter(pk=assignment.pk).update(due_at=now + timedelta(hours=40))
    Submission.objects.create(assignment=assignment, student=other_student, text="x", submitted_at=now)
    assert send_due_reminders(now) == 1
    assert send_due_reminders(now) == 0  # the same window is not sent twice
    note = Notification.objects.get(recipient=student.user)
    assert note.kind == "reminder" and note.title == "Due soon: Soil sampling report"
    assert not Notification.objects.filter(recipient=other_student.user).exists()
    assert send_due_reminders(now + timedelta(hours=17)) == 1  # now inside 24 hours
    assert due_reminders() == 0
    assert send_due_reminders(now + timedelta(hours=41)) == 0  # past the due date
    # An accommodation moves the student's own due date, and the reminders with it.
    Accommodation.objects.create(person=student, extra_days=2)
    assert send_due_reminders(now + timedelta(hours=41)) == 1  # 47 hours left: the 48-hour reminder
    assert Notification.objects.filter(recipient=student.user).count() == 3
    assert send_due_reminders(now + timedelta(days=5)) == 0
