"""The retention schedule, disposal approved by a second person, the nightly purge and the breach register
(item 1.19)."""

from datetime import date, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from audit.models import AuditLog
from notifications.models import Notification
from privacy.models import DisposalRun, RetentionRule
from privacy.retention import months_after, months_before, purge
from privacy.tasks import retention_purge


@pytest.fixture
def dpo(make_user):
    return make_user("the.dpo", "dpo")


@pytest.fixture
def administrator(make_user):
    return make_user("sys.admin", "administrator")


@pytest.fixture
def old_work(site, student, assignment):
    """Ravi's marked report on a course whose term ended seven years ago."""
    from assessments.models import Mark, Submission

    long_ago = timezone.now() - timedelta(days=7 * 366)
    type(assignment).objects.filter(pk=assignment.pk).update(due_at=long_ago)
    submission = Submission.objects.create(
        assignment=assignment,
        student=student,
        text="Soil pH was 6.2",
        file=SimpleUploadedFile("report.pdf", b"%PDF-1.4\n%report\n", content_type="application/pdf"),
        submitted_at=long_ago,
    )
    Mark.objects.create(submission=submission, mark=40, feedback="Good")
    return submission


def rule(code: str) -> RetentionRule:
    return RetentionRule.objects.get(code=code)


def test_months_are_counted_as_people_count_them():
    assert months_before(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert months_before(date(2024, 3, 31), 1) == date(2024, 2, 29)
    assert months_before(date(2026, 10, 1), 72) == date(2020, 10, 1)
    assert months_after(date(2026, 1, 31), 1) == date(2026, 2, 28)


@pytest.mark.django_db
def test_the_schedule_is_seeded_as_proposals_to_be_confirmed(seeded):
    periods = {r.code: (r.keep_months, r.automatic, r.confirmed_at) for r in RetentionRule.objects.all()}
    assert periods == {
        "submitted-work": (72, False, None),
        "marks-evidence": (72, False, None),
        "forum-posts": (36, False, None),
        "audit-log": (84, False, None),
        "login-attempts": (12, True, None),
        "ai-exchanges": (12, True, None),  # items 6.11, 6.12
        "notifications": (24, True, None),
        "course-sites": (12, True, None),
    }
    assert all("to be confirmed by GSA" in r.note for r in RetentionRule.objects.all())


@pytest.mark.django_db
def test_old_work_is_destroyed_only_when_a_second_person_approves(administrator, dpo, old_work, client_for):
    from assessments.models import Submission

    stored, name = old_work.file.storage, old_work.file.name
    admin = client_for(administrator)
    found = admin.post(f"/api/v1/privacy/retention-rules/{rule('submitted-work').id}/find/")
    assert found.status_code == 201, found.content
    run = found.json()["run"]
    assert [item["person_number"] for item in run["items"]] == ["26MRP0001"]
    assert run["proposed_by"] == "sys.admin" and run["proposed_by_me"] is True
    assert Notification.objects.filter(recipient=dpo, title__startswith="Records to dispose of").exists()

    same = admin.post(f"/api/v1/privacy/disposal-runs/{run['id']}/approve/")
    assert same.status_code == 403 and same.json()["code"] == "same_person"
    assert stored.exists(name)

    approved = client_for(dpo).post(f"/api/v1/privacy/disposal-runs/{run['id']}/approve/").json()
    assert approved["state"] == "done" and approved["items"][0]["disposed_at"]
    kept = Submission.objects.get(pk=old_work.pk)
    assert (kept.text, kept.file.name, kept.mark.mark) == ("", "", 40)  # the work goes, the mark stays
    assert not stored.exists(name)
    gone = AuditLog.objects.get(action="disposed")
    assert gone.subject == old_work.student_id and gone.reason.startswith(
        "Retention schedule: Submitted work"
    )
    assert gone.before["text_length"] == len("Soil pH was 6.2") and "Soil pH" not in str(gone.before)

    again = admin.post(f"/api/v1/privacy/retention-rules/{rule('submitted-work').id}/find/")
    assert again.json() == {"detail": "Nothing is due under this rule.", "run": None}

    evidence = admin.post(f"/api/v1/privacy/retention-rules/{rule('marks-evidence').id}/find/").json()["run"]
    client_for(dpo).post(f"/api/v1/privacy/disposal-runs/{evidence['id']}/approve/")
    assert not Submission.objects.filter(pk=old_work.pk).exists()


@pytest.mark.django_db
def test_recent_work_is_not_due(administrator, site, student, assignment, client_for):
    from assessments.models import Submission

    Submission.objects.create(
        assignment=assignment, student=student, text="Fresh", submitted_at=timezone.now()
    )
    found = client_for(administrator).post(
        f"/api/v1/privacy/retention-rules/{rule('marks-evidence').id}/find/"
    )
    assert found.json()["run"] is None


@pytest.mark.django_db
def test_a_record_can_be_kept_back_with_the_reason(administrator, dpo, old_work, client_for):
    from assessments.models import Submission

    admin = client_for(administrator)
    run = admin.post(f"/api/v1/privacy/retention-rules/{rule('marks-evidence').id}/find/").json()["run"]
    url = f"/api/v1/privacy/disposal-runs/{run['id']}/keep/"
    item = run["items"][0]["id"]
    assert admin.post(url, {"item": item, "reason": ""}, format="json").status_code == 400
    kept = admin.post(url, {"item": item, "reason": "Needed for an academic appeal"}, format="json")
    assert kept.json()["items"][0]["keep_reason"] == "Needed for an academic appeal"
    assert admin.post(url, {"item": 999999, "reason": "x"}, format="json").status_code == 404
    client_for(dpo).post(f"/api/v1/privacy/disposal-runs/{run['id']}/approve/")
    assert Submission.objects.filter(pk=old_work.pk).exists()
    assert AuditLog.objects.get(action="disposal_approved").after == {"disposed": 0, "kept": 1}
    assert admin.post(url, {"item": item, "reason": "late"}, format="json").status_code == 409


@pytest.mark.django_db
def test_one_run_waits_per_rule_and_a_run_can_be_cancelled(administrator, old_work, client_for):
    admin = client_for(administrator)
    url = f"/api/v1/privacy/retention-rules/{rule('marks-evidence').id}/find/"
    run = admin.post(url).json()["run"]
    second = admin.post(url)
    assert second.status_code == 409 and second.json()["code"] == "open_run"
    cancelled = admin.post(f"/api/v1/privacy/disposal-runs/{run['id']}/cancel/").json()
    assert cancelled["state"] == "cancelled"
    assert admin.post(url).status_code == 201  # a new run may now be proposed
    assert DisposalRun.objects.count() == 2


@pytest.mark.django_db
def test_who_keeps_the_schedule_and_what_cannot_be_disposed_of_here(
    administrator, dpo, course_admin, student, make_user, client_for
):
    admin = client_for(administrator)
    work = rule("submitted-work")
    confirmed = admin.post(f"/api/v1/privacy/retention-rules/{work.id}/confirm/").json()
    assert confirmed["confirmed"] is True and confirmed["confirmed_by_name"] == "sys.admin"
    changed = admin.patch(f"/api/v1/privacy/retention-rules/{work.id}/", {"keep_months": 84}, format="json")
    assert changed.json()["keep_months"] == 84 and changed.json()["confirmed"] is False
    assert AuditLog.objects.get(action="retention_changed").before["keep_months"] == 72
    zero = admin.patch(f"/api/v1/privacy/retention-rules/{work.id}/", {"keep_months": 0}, format="json")
    assert zero.status_code == 400

    auditor = client_for(make_user("the.auditor", "auditor"))
    assert len(auditor.get("/api/v1/privacy/retention-rules/").json()) == 7
    assert auditor.patch(f"/api/v1/privacy/retention-rules/{work.id}/", {"keep_months": 1}).status_code == 403
    assert client_for(course_admin).get("/api/v1/privacy/retention-rules/").status_code == 403
    assert (
        client_for(student.user).post(f"/api/v1/privacy/retention-rules/{work.id}/find/").status_code == 403
    )
    nightly = admin.post(f"/api/v1/privacy/retention-rules/{rule('login-attempts').id}/find/")
    assert nightly.status_code == 409 and nightly.json()["code"] == "automatic"
    audit_log = admin.post(f"/api/v1/privacy/retention-rules/{rule('audit-log').id}/find/")
    assert audit_log.status_code == 409 and audit_log.json()["code"] == "review_only"
    forum = admin.post(f"/api/v1/privacy/retention-rules/{rule('forum-posts').id}/find/")
    assert forum.json()["run"] is None


@pytest.mark.django_db
def test_old_logs_go_every_night_without_review(student):
    from iam.models import LoginAttempt

    long_ago = timezone.now() - timedelta(days=800)
    old = LoginAttempt.objects.create(username="26MRP0001", success=True)
    LoginAttempt.objects.filter(pk=old.pk).update(at=long_ago)
    LoginAttempt.objects.create(username="26MRP0001", success=True)
    stale = Notification.objects.create(recipient=student.user, title="Sent long ago")
    Notification.objects.filter(pk=stale.pk).update(created_at=long_ago)
    fresh = Notification.objects.create(recipient=student.user, title="Sent today")

    assert purge(timezone.localdate()) == {"login-attempts": 1, "notifications": 1, "ai-exchanges": 0}
    assert LoginAttempt.objects.count() == 1
    assert list(Notification.objects.values_list("pk", flat=True)) == [fresh.pk]
    assert AuditLog.objects.filter(action="purged").count() == 2
    assert retention_purge() == {"login-attempts": 0, "notifications": 0, "ai-exchanges": 0}


@pytest.mark.django_db
def test_a_breach_is_recorded_followed_up_and_closed(administrator, dpo, make_user, client_for):
    admin = client_for(administrator)
    breach = admin.post(
        "/api/v1/privacy/breaches/",
        {
            "discovered_at": "2026-10-01T09:00:00-04:00",
            "summary": "A class list was emailed to the wrong address.",
            "data_affected": "Names and student numbers of 30 first-year students",
            "people_affected": 30,
            "minors_affected": True,
            "risk": "medium",
        },
        format="json",
    )
    assert breach.status_code == 201, breach.content
    entry = breach.json()
    year = timezone.localdate().year
    assert entry["reference"] == f"BR-{year}-001" and entry["minors_affected"] is True
    assert Notification.objects.filter(recipient=dpo, title__startswith="Personal data breach").exists()

    url = f"/api/v1/privacy/breaches/{entry['id']}/"
    early = admin.post(f"{url}close/")
    assert early.status_code == 409 and early.json()["code"] == "not_contained"
    admin.patch(
        url,
        {"contained_at": "2026-10-01T11:00:00-04:00", "change_reason": "Recipient confirmed deletion"},
        format="json",
    )
    assert (
        AuditLog.objects.get(entity="privacy.breach", action="update").reason
        == "Recipient confirmed deletion"
    )
    closed = admin.post(f"{url}close/").json()
    assert closed["closed_at"] and admin.post(f"{url}close/").status_code == 409

    auditor = client_for(make_user("the.auditor", "auditor"))
    assert auditor.get("/api/v1/privacy/breaches/").json()["count"] == 1
    assert auditor.post("/api/v1/privacy/breaches/", {"summary": "x"}, format="json").status_code == 403
