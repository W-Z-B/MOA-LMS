"""Scheduled jobs run at GSA's local time (America/Guyana), although procrastinate reads cron lines in UTC."""

import datetime
from zoneinfo import ZoneInfo

import pytest
from croniter import croniter
from django.core.exceptions import ImproperlyConfigured
from procrastinate.contrib.django import app

from core.schedule import local_cron, utc_offset_hours

GUYANA = ZoneInfo("America/Guyana")

# Every periodic job, and the local time it is meant to run (weekdays where it names them). A new job must be
# added here, so that its time is thought about in local terms.
INTENDED = {
    "approvals.chase_decisions": ("07:00", "Mon-Fri"),
    "assessments.due_reminders": ("every hour at :05", None),
    "audit.verify_chain": ("03:30", None),
    "iam.access_review_reminder": ("06:00", "Mon"),
    "insights.sync_outcomes": ("02:10", None),
    "insights.push_competency": ("02:50", None),
    "insights.early_alerts": ("04:15", None),
    "integration.sync_srms": ("02:00", None),
    "integration.sync_staff": ("01:45", None),
    "integration.push_marks": ("02:30", None),
    "integration.push_training": ("02:45", None),
    "integration.sync_training_requirements": ("06:00", None),
    "opencourses.purge_registrations": ("03:40", None),
    "peerreview.allocate_due": ("every hour at :20", None),
    "notifications.daily_summary": ("17:00", None),
    "privacy.retention_purge": ("04:00", None),
    "staffdev.completion_sweep": ("02:15", None),
    "staffdev.required_training": ("06:30", None),
    "terms.lifecycle": ("04:30", None),
}


def runs(cron: str, count: int) -> list[datetime.datetime]:
    """The next runs of a cron line as procrastinate computes them (from a Unix timestamp: UTC), in Guyana."""
    start = datetime.datetime(2026, 10, 5, tzinfo=datetime.UTC).timestamp()  # a Monday, 00:00 UTC
    schedule = croniter(cron, start)
    return [
        datetime.datetime.fromtimestamp(schedule.get_next(float), tz=datetime.UTC).astimezone(GUYANA)
        for _ in range(count)
    ]


def test_every_periodic_job_runs_at_its_intended_local_time():
    jobs = {pt.task.name: pt.cron for pt in app.periodic_registry.periodic_tasks.values()}
    assert set(jobs) == set(INTENDED), "add each new periodic job to INTENDED with its local time"
    for name, (at, weekdays) in INTENDED.items():
        times = runs(jobs[name], 14)
        if at.startswith("every hour"):
            assert {t.strftime(":%M") for t in times} == {at[-3:]} and len({t.hour for t in times}) == 14, (
                name
            )
            continue
        assert {t.strftime("%H:%M") for t in times} == {at}, name
        days = {t.strftime("%a") for t in times}
        expected = {"Mon-Fri": {"Mon", "Tue", "Wed", "Thu", "Fri"}, "Mon": {"Mon"}}.get(weekdays)
        assert days == (expected or {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}), name


def test_the_daily_summary_goes_at_five_in_the_afternoon_not_one():
    """The finding that started this: a UTC "0 17" is 13:00 in Guyana."""
    assert runs("0 17 * * *", 1)[0].hour == 13
    assert local_cron("0 17 * * *") == "0 21 * * *"
    assert runs(local_cron("0 17 * * *"), 1)[0].hour == 17


def test_guyana_keeps_one_offset_all_year():
    for year in (2026, 2027, 2030):
        assert utc_offset_hours("America/Guyana", year=year) == 4


def test_local_cron_shifts_hours_and_refuses_what_it_cannot_express():
    assert local_cron("5 * * * *") == "5 * * * *"
    assert local_cron("0 7 * * 1-5") == "0 11 * * 1-5"
    assert local_cron("0 6,18 * * *") == "0 10,22 * * *"
    assert local_cron("0 8-10 * * *") == "0 12,13,14 * * *"
    assert local_cron("30 22 * * *") == "30 2 * * *"  # every day, so crossing midnight is fine
    with pytest.raises(ValueError, match="crosses midnight"):
        local_cron("30 22 * * 1")  # Monday night locally is Tuesday in UTC
    with pytest.raises(ValueError, match="in full"):
        local_cron("0 */2 * * *")
    with pytest.raises(ValueError, match="five-field"):
        local_cron("0 7 * *")
    with pytest.raises(ValueError, match="list of hours"):
        local_cron("0 25 * * *")
    with pytest.raises(ImproperlyConfigured, match="changes its clock"):
        local_cron("0 7 * * *", zone="America/New_York")
    with pytest.raises(ImproperlyConfigured, match="whole number"):
        local_cron("0 7 * * *", zone="Asia/Kolkata")
