"""The audit log's chained fingerprints and the audit viewer (item 1.17)."""

import importlib
from datetime import UTC, datetime

import pytest
from django.apps import apps
from django.core.management import CommandError, call_command
from django.db import connection

from audit import chain
from audit.models import AuditCheck, AuditLog
from audit.tasks import verify_chain
from notifications.models import Notification

TRIGGER = "audit_log_no_update_delete"


def settle() -> None:
    """Run the foreign-key checks this test's transaction has deferred, as a separate session has none."""
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def as_superuser(sql: str, params=()) -> None:
    """What someone with the database's own superuser can do: switch the trigger off, then edit."""
    settle()
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE audit_auditlog DISABLE TRIGGER {TRIGGER}")
        cursor.execute(sql, params)
        cursor.execute(f"ALTER TABLE audit_auditlog ENABLE TRIGGER {TRIGGER}")


def entries(count: int, **fields) -> list[AuditLog]:
    return [
        AuditLog.objects.create(
            action="update", entity="courses.coursesite", entity_id=n, reason=f"Entry {n}", **fields
        )
        for n in range(count)
    ]


@pytest.fixture
def auditor(make_user):
    return make_user("the.auditor", "auditor")


@pytest.fixture
def administrator(make_user):
    return make_user("sys.admin", "administrator")


# ---------------------------------------------------------------------------------------------- the chain


@pytest.mark.django_db
def test_each_entry_is_chained_to_the_one_before():
    first, second, third = entries(3)
    assert first.chain == chain.link("", first)
    assert second.chain == chain.link(first.chain, second)
    assert third.chain == chain.link(second.chain, third)
    check = chain.verify()
    assert (check.intact, check.rows, check.last_id, check.last_chain) == (True, 3, third.id, third.chain)
    assert verify_chain() is True


@pytest.mark.django_db
def test_a_tampered_entry_shows_even_with_the_trigger_switched_off(auditor, administrator):
    _, middle, _ = entries(3)
    as_superuser("UPDATE audit_auditlog SET reason = %s WHERE id = %s", ["Nothing to see", middle.id])
    check = chain.verify()
    assert check.intact is False and check.first_broken_id == middle.id
    assert f"Entry {middle.id} no longer matches" in check.detail
    alerts = Notification.objects.filter(title="The audit log has been altered")
    assert {note.recipient for note in alerts} == {auditor, administrator}
    with pytest.raises(CommandError, match="no longer matches"):
        call_command("verify_audit_chain")
    assert verify_chain() is False


@pytest.mark.django_db
def test_a_removed_entry_shows_at_the_one_after_it():
    first, middle, last = entries(3)
    as_superuser("DELETE FROM audit_auditlog WHERE id = %s", [middle.id])
    check = chain.verify()
    assert check.intact is False and check.first_broken_id == last.id and check.rows == 1


@pytest.mark.django_db
def test_entries_removed_from_the_end_show_at_the_next_check():
    *_, newest = entries(3)
    assert chain.verify().intact
    as_superuser("DELETE FROM audit_auditlog WHERE id = %s", [newest.id])
    check = chain.verify()
    assert check.intact is False and check.first_broken_id is None
    assert "removed from the end" in check.detail


@pytest.mark.django_db
def test_without_the_key_the_fingerprints_cannot_be_made_again(settings):
    entries(2)
    settings.FIELD_ENCRYPTION_KEY = "a-key-someone-guessed"
    check = chain.verify()
    assert check.intact is False and check.first_broken_id == AuditLog.objects.order_by("id").first().id


@pytest.mark.django_db
def test_addresses_verify_however_they_were_written():
    AuditLog.objects.create(
        action="login", entity="auth.user", source_ip="2001:0db8:0000:0000:0000:0000:0000:0001"
    )
    AuditLog.objects.create(action="login", entity="auth.user", source_ip="::ffff:190.80.1.2")
    AuditLog.objects.create(action="login", entity="auth.user", source_ip=None)
    assert chain.verify().intact


@pytest.mark.django_db
def test_an_entry_is_never_changed_through_the_application():
    (entry,) = entries(1)
    entry.reason = "Edited"
    with pytest.raises(ValueError, match="never changed"):
        entry.save()


@pytest.mark.django_db
def test_entries_written_before_the_chain_are_sealed_by_the_migration():
    when = datetime(2026, 9, 1, 12, tzinfo=UTC)
    with connection.cursor() as cursor:
        for n in range(3):
            cursor.execute(
                "INSERT INTO audit_auditlog (at, action, entity, entity_id, reason, chain, before, after) "
                "VALUES (%s, 'create', 'courses.coursesite', %s, '', '', NULL, %s::jsonb)",
                [when, n, '{"title": "AGR101", "n": 1.5}'],
            )
    assert chain.verify().intact is False  # not sealed yet
    seal = importlib.import_module("audit.migrations.0004_chained_fingerprints").seal
    settle()
    with connection.schema_editor() as editor:
        seal(apps, editor)
    assert chain.verify().intact
    assert AuditLog.objects.create(action="login", entity="auth.user").chain  # new entries carry on the chain
    assert chain.verify().intact


# ---------------------------------------------------------------------------------------------- the viewer


@pytest.mark.django_db
def test_only_the_auditor_and_administrators_read_the_log(
    auditor, administrator, course_admin, student, client_for
):
    entries(2)
    assert client_for(auditor).get("/api/v1/audit/").json()["count"] == 2
    assert client_for(administrator).get("/api/v1/audit/").status_code == 200
    assert client_for(course_admin).get("/api/v1/audit/").status_code == 403
    assert client_for(student.user).get("/api/v1/audit/").status_code == 403
    assert client_for(student.user).get("/api/v1/audit/export/").status_code == 403
    assert client_for(student.user).post("/api/v1/audit/chain/").status_code == 403
    assert AuditCheck.objects.count() == 0


@pytest.mark.django_db
def test_the_log_is_filtered_and_said_in_words(auditor, course_admin, student, site, client_for):
    changed = client_for(course_admin).patch(
        f"/api/v1/sites/{site.id}/",
        {"description": "Soils and crops"},
        format="json",
    )
    assert changed.status_code == 200, changed.content
    AuditLog.objects.create(action="login", entity="auth.user", entity_id=student.user.pk, subject=student.pk)
    AuditLog.objects.create(action="update", entity="courses.coursesite", reason="Outline agreed")
    client = client_for(auditor)
    rows = client.get("/api/v1/audit/", {"record": "courses.coursesite"}).json()["results"]
    change = next(row for row in rows if row["action"] == "update" and row["changes"])
    assert (change["action_name"], change["record"], change["actor_username"]) == (
        "Changed",
        "Course site",
        "course.admin",
    )
    assert {"field": "Description", "before": "", "after": "Soils and crops"} in change["changes"]
    assert change["chain"]

    mine = client.get("/api/v1/audit/", {"person": "26MRP0001"}).json()["results"]
    assert [(row["action"], row["person_number"]) for row in mine] == [("login", "26MRP0001")]
    assert client.get("/api/v1/audit/", {"action": "login"}).json()["count"] == 1
    assert client.get("/api/v1/audit/", {"q": "outline"}).json()["count"] >= 1
    assert client.get("/api/v1/audit/", {"who": "course.ad"}).json()["count"] >= 1
    today = datetime.now().date().isoformat()
    assert client.get("/api/v1/audit/", {"since": today, "until": today}).json()["count"] >= 2
    assert client.get("/api/v1/audit/", {"until": "2020-01-01"}).json()["count"] == 0
    bad = client.get("/api/v1/audit/", {"since": "2026-02-30"})
    assert bad.status_code == 400 and bad.json()["since"] == ["Give a date as YYYY-MM-DD."]

    choices = client.get("/api/v1/audit/choices/").json()
    assert {"code": "login", "name": "Signed in"} in choices["actions"]
    assert {"code": "courses.coursesite", "name": "Course site"} in choices["records"]


@pytest.mark.django_db
def test_a_submission_names_its_student(student, assignment, client_for):
    response = client_for(student.user).post(
        f"/api/v1/assignments/{assignment.id}/submit/", {"text": "My report"}, format="json"
    )
    assert response.status_code in (200, 201), response.content
    entry = AuditLog.objects.get(action="submit")
    assert entry.subject == student.pk and entry.actor == student.user


@pytest.mark.django_db
def test_who_did_it_is_said_plainly_when_nobody_was_signed_in(auditor, client_for):
    AuditLog.objects.create(action="login", entity="auth.user", source_ip="190.80.1.2")
    AuditLog.objects.create(
        action="integration:sites.read", entity="integration.serviceclient", source_ip="10.0.0.5"
    )
    AuditLog.objects.create(action="purged", entity="privacy.retentionrule")
    rows = client_for(auditor).get("/api/v1/audit/").json()["results"]
    said = {row["action"]: (row["actor"], row["action_name"]) for row in rows}
    assert said["login"] == ("Someone not signed in", "Signed in")
    assert said["integration:sites.read"] == ("A linked system", "Integration: sites.read")
    assert said["purged"] == ("System", "Old logs removed")


@pytest.mark.django_db
def test_the_export_is_a_safe_spreadsheet_file_and_is_itself_audited(auditor, client_for):
    AuditLog.objects.create(
        action="update", entity="courses.coursesite", entity_id=1, reason='=HYPERLINK("http://x")'
    )
    response = client_for(auditor).get("/api/v1/audit/export/", {"action": "update"})
    assert response.status_code == 200 and response["Content-Type"].startswith("text/csv")
    assert response["Content-Disposition"].startswith('attachment; filename="gsa-lms-audit-')
    text = b"".join(response.streaming_content).decode("utf-8")
    assert text.startswith("﻿Entry,When,Who,Username,What,Record")
    assert "'=HYPERLINK" in text and ",=HYPERLINK" not in text
    exported = AuditLog.objects.get(action="audit_exported")
    assert exported.actor == auditor and exported.after == {"filters": {"action": "update"}, "rows": 1}


@pytest.mark.django_db
def test_the_state_of_the_chain_is_shown_and_checked_on_request(auditor, client_for):
    entries(2)
    client = client_for(auditor)
    before = client.get("/api/v1/audit/chain/").json()
    assert before["entries"] == 2 and before["latest_check"] is None
    checked = client.post("/api/v1/audit/chain/").json()
    assert checked["latest_check"]["intact"] is True and checked["latest_check"]["rows"] == 2
    assert checked["latest_check"]["checked_by"] == "the.auditor"
    assert AuditLog.objects.filter(action="audit_checked").exists()
    assert AuditCheck.objects.count() == 1
    call_command("verify_audit_chain")
    nightly = client.get("/api/v1/audit/chain/").json()["latest_check"]
    assert nightly["checked_by"] == "The nightly check" and nightly["rows"] == 3
