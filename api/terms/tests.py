"""The term life-cycle (item 7.12): the calendar, sites closing to work and to change, and the archive."""

import json
import zipfile
from datetime import date, timedelta

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from audit.models import AuditLog
from notifications.models import Notification
from terms import lifecycle
from terms.models import SiteArchive, Term

TERM = "2026-27-S1"


def make_term(closes_days_ago: int, *, grace=None, code=TERM, **extra) -> Term:
    """A term whose close date was this many days ago (negative: still to come)."""
    today = timezone.localdate()
    closes = today - timedelta(days=closes_days_ago)
    return Term.objects.create(
        code=code,
        name="Semester 1",
        starts_on=closes - timedelta(days=120),
        ends_on=closes - timedelta(days=14),
        closes_on=closes,
        grace_days=grace,
        **extra,
    )


def submit(client, assignment, text="My report"):
    return client.post(f"/api/v1/assignments/{assignment.id}/submit/", {"text": text}, format="multipart")


def test_phases_follow_the_calendar(settings):
    settings.TERM_GRACE_DAYS = 2
    today = date(2026, 12, 10)
    term = Term(code=TERM, name="S1", starts_on=date(2026, 9, 1), ends_on=date(2026, 12, 1))
    term.closes_on = date(2026, 12, 9)

    def at(day, hour=12):
        return timezone.make_aware(timezone.datetime(day.year, day.month, day.day, hour))

    assert lifecycle.term_phase(term, at(date(2026, 8, 1))) == "upcoming"
    assert lifecycle.term_phase(term, at(date(2026, 10, 1))) == "teaching"
    assert lifecycle.term_phase(term, at(date(2026, 12, 5))) == "ended"
    assert lifecycle.term_phase(term, at(date(2026, 12, 9), 23)) == "ended"  # the close date is a whole day
    assert lifecycle.term_phase(term, at(today)) == "grace"
    assert lifecycle.term_phase(term, at(date(2026, 12, 11), 23)) == "grace"
    assert lifecycle.term_phase(term, at(date(2026, 12, 12), 0)) == "closed"
    term.grace_days = 0  # the term's own grace wins over the default
    assert lifecycle.term_phase(term, at(today)) == "closed"
    term.archived_at = timezone.now()
    assert lifecycle.term_phase(term, at(today)) == "archived"
    assert lifecycle.phase_from(None, archived=False).phase == "open"  # a code not in the calendar


@pytest.mark.django_db
def test_a_closed_site_takes_no_work_from_students(site, assignment, student, client_for):
    learner = client_for(student.user)
    make_term(closes_days_ago=1, grace=2)  # within the grace: still taking work
    assert submit(learner, assignment).status_code == 201
    Term.objects.filter(code=TERM).update(grace_days=0)
    refused = submit(learner, assignment, text="Too late")
    assert refused.status_code == 409 and refused.json()["code"] == "site_closed"
    assert "read-only for appeals" in refused.json()["detail"]
    assert learner.get(f"/api/v1/assignments/{assignment.id}/").status_code == 200  # reading goes on
    site_row = learner.get(f"/api/v1/sites/{site.id}/").json()
    assert site_row["phase"] == "closed" and "read-only" in site_row["closed_notice"]


@pytest.mark.django_db
def test_a_closed_site_is_read_only_to_its_lecturer_but_not_to_a_course_administrator(
    site, assignment, lecturer, course_admin, client_for
):
    make_term(closes_days_ago=5, grace=0)
    teacher = client_for(lecturer.user)
    change = teacher.patch(f"/api/v1/assignments/{assignment.id}/", {"title": "Renamed"}, format="json")
    assert change.status_code == 409 and change.json()["code"] == "site_closed"
    added = teacher.post("/api/v1/modules/", {"site": site.id, "title": "Late notes"}, format="json")
    assert added.status_code == 409
    admin = client_for(course_admin)  # a change made for an appeal
    change = admin.patch(f"/api/v1/assignments/{assignment.id}/", {"title": "Renamed"}, format="json")
    assert change.status_code == 200
    assert AuditLog.objects.filter(
        action="update", entity="assessments.assignment", actor=course_admin
    ).exists()


@pytest.mark.django_db
def test_an_archived_site_refuses_everyone_and_leaves_members_lists(
    site, assignment, student, course_admin, client_for
):
    make_term(closes_days_ago=500, grace=0)
    SiteArchive.objects.create(
        site=site,
        term_code=TERM,
        file=ContentFile(b"x", name="a.zip"),
        size=1,
        sha256="0" * 64,
        records=0,
        files=0,
    )
    admin = client_for(course_admin)
    change = admin.patch(f"/api/v1/assignments/{assignment.id}/", {"title": "Renamed"}, format="json")
    assert change.status_code == 409 and "archived" in change.json()["detail"]
    assert admin.get(f"/api/v1/sites/{site.id}/").json()["phase"] == "archived"
    assert client_for(student.user).get("/api/v1/sites/").json()["results"] == []


@pytest.mark.django_db
def test_work_outside_a_request_and_unrelated_records_are_not_refused(site, assignment, student, client_for):
    make_term(closes_days_ago=5, grace=0)
    assignment.title = "Changed by a nightly job"
    assignment.save()  # no request: the retention schedule and the SRMS sync follow their own rules
    assert client_for(student.user).post("/api/v1/notifications/read-all/").status_code in (200, 204)


@pytest.mark.django_db
def test_course_administrators_keep_the_calendar(course_admin, client_for):
    admin = client_for(course_admin)
    body = {
        "code": TERM,
        "name": "Semester 1",
        "starts_on": "2026-09-01",
        "ends_on": "2026-12-11",
        "closes_on": "2026-12-23",
    }
    created = admin.post("/api/v1/terms/", body, format="json")
    assert created.status_code == 201, created.json()
    row = created.json()
    assert row["source"] == "local" and row["grace_days"] is None and row["grace_days_applied"] == 2
    assert row["archive_due_on"] == "2027-12-26" and row["site_count"] == 0
    assert AuditLog.objects.filter(action="create", entity="terms.term").exists()
    late = admin.patch(f"/api/v1/terms/{row['id']}/", {"closes_on": "2026-12-01"}, format="json")
    assert late.status_code == 400 and "closes_on" in late.json()
    backwards = admin.patch(f"/api/v1/terms/{row['id']}/", {"ends_on": "2026-08-01"}, format="json")
    assert backwards.status_code == 400 and "ends_on" in backwards.json()
    assert (
        admin.patch(f"/api/v1/terms/{row['id']}/", {"grace_days": 5}, format="json").json()["grace_days"] == 5
    )
    assert admin.delete(f"/api/v1/terms/{row['id']}/").status_code == 204


@pytest.mark.django_db
def test_only_course_administrators_change_the_calendar(
    site, student, lecturer, make_user, client_for, course_admin
):
    term = make_term(closes_days_ago=-30)
    auditor = client_for(make_user("audit.one", "auditor"))
    assert auditor.get("/api/v1/terms/").json()["results"][0]["site_count"] == 1
    assert auditor.patch(f"/api/v1/terms/{term.id}/", {"grace_days": 1}, format="json").status_code == 403
    for person in (student, lecturer):
        client = client_for(person.user)
        assert client.get("/api/v1/terms/").status_code == 403
        assert client.post("/api/v1/terms/", {}, format="json").status_code == 403
    in_use = client_for(course_admin).delete(f"/api/v1/terms/{term.id}/")
    assert in_use.status_code == 409 and in_use.json()["code"] == "in_use"


@pytest.mark.django_db
def test_a_term_from_the_srms_keeps_its_dates_but_its_close_is_the_lms_s(course_admin, client_for):
    term = make_term(closes_days_ago=-30, source=Term.Source.SRMS)
    admin = client_for(course_admin)
    renamed = admin.patch(f"/api/v1/terms/{term.id}/", {"name": "Other"}, format="json")
    assert renamed.status_code == 400 and "SRMS" in str(renamed.json())
    recoded = admin.patch(f"/api/v1/terms/{term.id}/", {"code": "2030-S9"}, format="json")
    assert recoded.status_code == 400
    later = (term.closes_on + timedelta(days=3)).isoformat()
    assert admin.patch(f"/api/v1/terms/{term.id}/", {"closes_on": later}, format="json").status_code == 200


@pytest.mark.django_db
def test_terms_missing_from_the_calendar_and_a_terms_sites(site, course_admin, client_for):
    admin = client_for(course_admin)
    assert admin.get("/api/v1/terms/missing/").json() == [{"term_code": TERM, "sites": 1}]
    term = make_term(closes_days_ago=3, grace=1)
    assert admin.get("/api/v1/terms/missing/").json() == []
    rows = admin.get(f"/api/v1/terms/{term.id}/sites/").json()
    assert rows == [
        {
            "id": site.id,
            "code": site.code,
            "title": site.title,
            "phase": "closed",
            "archive": None,
            "archive_size": None,
            "archive_made_at": None,
        }
    ]


@pytest.mark.django_db
def test_the_nightly_job_closes_then_archives(site, assignment, student, lecturer, course_admin, client_for):
    learner = client_for(student.user)
    assert submit(learner, assignment, text="Soil pH was 6.2").status_code == 201
    term = make_term(closes_days_ago=3, grace=1)
    first = lifecycle.run()
    assert first == {"synced": None, "closed": 1, "archived_sites": 0}
    term.refresh_from_db()
    assert (
        term.closed_at is not None and AuditLog.objects.filter(action="closed", entity="terms.term").exists()
    )
    assert Notification.objects.filter(recipient=lecturer.user, title__contains="is now closed").exists()
    assert lifecycle.run()["closed"] == 0  # once only

    # Twelve months (the retention schedule's period for course sites) after the close: archived.
    later = timezone.now() + timedelta(days=370)
    assert lifecycle.run(later)["archived_sites"] == 1
    archive = SiteArchive.objects.get(site=site)
    term.refresh_from_db()
    assert term.archived_at is not None and archive.records > 0
    with zipfile.ZipFile(archive.file.open("rb")) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        records = json.loads(bundle.read("records.json"))
    assert manifest["site"]["code"] == site.code
    assert {p["number"] for p in manifest["people"]} >= {student.external_id, lecturer.external_id}
    assert records["assessments.submission"][0]["text"] == "Soil pH was 6.2"
    assert AuditLog.objects.filter(action="archived", entity="courses.coursesite", entity_id=site.pk).exists()
    assert lifecycle.run(later)["archived_sites"] == 0

    # The archive is read by course administrators (each download audited), never by teaching staff.
    admin = client_for(course_admin)
    download = admin.get(f"/api/v1/site-archives/{archive.id}/download/")
    assert download.status_code == 200 and download["Content-Disposition"].startswith("attachment")
    assert AuditLog.objects.filter(
        action="download", entity="courses.coursesite", actor=course_admin
    ).exists()
    assert client_for(lecturer.user).get(f"/api/v1/site-archives/{archive.id}/download/").status_code == 403
    sites = admin.get(f"/api/v1/terms/{term.id}/sites/").json()
    assert sites[0]["phase"] == "archived" and sites[0]["archive"] == archive.id


@pytest.mark.django_db
def test_the_archive_period_is_the_retention_schedules(seeded):
    from privacy.models import RetentionRule

    rule = RetentionRule.objects.get(code="course-sites")
    assert rule.action == "archive" and rule.automatic and rule.keep_months == 12
    RetentionRule.objects.filter(pk=rule.pk).update(keep_months=24)
    term = Term(code=TERM, name="S1", starts_on=date(2026, 9, 1), ends_on=date(2026, 12, 1))
    term.closes_on, term.grace_days = date(2026, 12, 9), 0
    assert lifecycle.archive_due_on(term) == date(2028, 12, 10)
    assert lifecycle.run() == {"synced": None, "closed": 0, "archived_sites": 0}  # nothing in the calendar


@pytest.mark.django_db
def test_the_calendar_from_the_srms_when_turned_on(settings, monkeypatch, db):
    from integration import client

    settings.TERMS_FROM_SRMS = True
    rows = [{"code": TERM, "name": "Semester 1", "starts": "2026-09-01", "ends": "2026-12-11"}]
    monkeypatch.setattr(client, "pages", lambda *a, **k: iter(rows))
    assert lifecycle.run()["synced"] == {"created": 1, "updated": 0, "failed": False}
    term = Term.objects.get(code=TERM)
    assert term.source == "srms" and term.closes_on == date(2027, 1, 8)
    rows[0] = {**rows[0], "ends": "2026-12-18"}
    assert lifecycle.sync_from_srms() == {"created": 0, "updated": 1, "failed": False}
    term.refresh_from_db()
    assert term.ends_on == date(2026, 12, 18) and term.closes_on == date(2027, 1, 8)

    def unreachable(*a, **k):
        raise client.IntegrationError("down")

    monkeypatch.setattr(client, "pages", unreachable)
    assert lifecycle.sync_from_srms()["failed"] is True


@pytest.mark.django_db
def test_the_retention_schedule_counts_from_the_close_of_term(site, assignment):
    from privacy.retention import term_ends

    assert term_ends()[site.id] == assignment.due_at  # not in the calendar: the last due date
    term = make_term(closes_days_ago=10, grace=0)
    assert term_ends()[site.id] == lifecycle.locks_at(term)


@pytest.mark.django_db
def test_the_nightly_task(db):
    from terms.tasks import term_lifecycle

    assert term_lifecycle() == {"synced": None, "closed": 0, "archived_sites": 0}
