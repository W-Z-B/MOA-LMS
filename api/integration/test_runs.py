"""Item 1.23: pushes that carry on past a refused row, retry the network, run each night and are recorded."""

from datetime import date

import pytest
from django.utils import timezone

from assessments.models import Mark, Submission
from courses.models import Completion, CourseSite
from integration.client import IntegrationError
from integration.models import IntegrationRun
from integration.tests import STAFF, ecosystem  # noqa: F401 - the stand-in HRMS and SRMS
from people.models import PersonRef


def _staff_completion(person, code="SD-201", expires=None):
    site, _ = CourseSite.objects.get_or_create(
        code=code, defaults={"title": f"Course {code}", "kind": "staff_development", "is_published": True}
    )
    return Completion.objects.create(
        site=site, person=person, completed_on=date(2026, 10, 1), expires_on=expires
    )


@pytest.mark.django_db
def test_an_unknown_employee_no_longer_stops_the_training_push(lecturer, make_person, ecosystem):  # noqa: F811
    """The refused row is recorded, the others are sent, and it is tried again next time."""
    from integration.hrms import push_training

    stranger = make_person("staff", "E0999", "Not", "Known")
    first = _staff_completion(stranger, "SD-201")
    second = _staff_completion(lecturer, "SD-202", expires=date(2028, 10, 1))
    ecosystem["unknown"] = {"E0999"}
    result = push_training()
    assert (result["ok"], result["failed"], result["stopped"]) == (1, 1, "")
    run = IntegrationRun.objects.get(pk=result["run"])
    assert run.kind == "training_push" and run.finished_at is not None
    assert run.errors == [
        {
            "ref": "lms:SD-201:E0999",
            "code": "unknown_employee",
            "detail": "/api/v1/integration/training-completions/ answered HTTP 404",
        }
    ]
    second.refresh_from_db()
    first.refresh_from_db()
    assert second.reported_at is not None and first.reported_at is None
    sent = {data["employee_no"]: data for _, data in ecosystem["posted"]}
    assert sent["E0001"]["expiry_date"] == "2028-10-01"  # item 5.06: the expiry goes too
    ecosystem["unknown"] = set()
    assert push_training()["ok"] == 1


@pytest.mark.django_db
def test_a_network_failure_is_retried_then_stops_the_run(lecturer, ecosystem, settings):  # noqa: F811
    from integration.hrms import push_training

    settings.INTEGRATION_ATTEMPTS = 3
    completion = _staff_completion(lecturer)
    ecosystem["down"] = 2  # two failures, then it answers: retried within the run
    assert push_training()["ok"] == 1
    Completion.objects.filter(pk=completion.pk).update(reported_at=None)
    ecosystem["down"] = 5  # still down after every retry: the run stops, the row waits for next time
    result = push_training()
    assert result["ok"] == 0 and result["failed"] == 0 and "could not be reached" in result["stopped"]
    completion.refresh_from_db()
    assert completion.reported_at is None


def test_retries_wait_longer_each_time(settings):
    from integration.client import with_retries

    settings.INTEGRATION_ATTEMPTS, settings.INTEGRATION_RETRY_SECONDS = 3, 5
    waits, calls = [], []

    def send():
        calls.append(1)
        raise IntegrationError("down")

    with pytest.raises(IntegrationError):
        with_retries(send, sleep=waits.append)
    assert len(calls) == 3 and waits == [5, 10]

    def refused():
        calls.append(1)
        raise IntegrationError("no", status=400)

    calls.clear()
    with pytest.raises(IntegrationError):
        with_retries(refused, sleep=waits.append)
    assert len(calls) == 1  # a refusal is not tried again


@pytest.mark.django_db
def test_the_nightly_marks_push_records_each_site(site, assignment, student, ecosystem):  # noqa: F811
    from integration.srms import push_all_marks

    submission = Submission.objects.create(
        assignment=assignment, student=student, text="x", submitted_at=timezone.now()
    )
    Mark.objects.create(submission=submission, mark=35)
    ecosystem["marks"] = {
        "offering_code": site.code,
        "accepted": [],
        "locked": ["26MRP0002"],
        "unknown": ["X1"],
    }
    result = push_all_marks()
    assert (result["ok"], result["failed"]) == (1, 0)
    run = IntegrationRun.objects.get(pk=result["run"])
    assert [e["code"] for e in run.errors] == ["unknown_student", "locked"]
    ecosystem["down"] = 99
    assert "SRMS could not be reached" in push_all_marks()["stopped"]


@pytest.mark.django_db
def test_a_refused_site_is_recorded_and_the_push_carries_on(site, ecosystem, monkeypatch):  # noqa: F811
    from integration import srms

    def refuse(s):
        raise IntegrationError("answered HTTP 409", status=409)

    monkeypatch.setattr(srms, "push_marks", refuse)
    result = srms.push_all_marks()
    assert result["failed"] == 1
    assert IntegrationRun.objects.get(pk=result["run"]).errors[0]["code"] == "http_409"


@pytest.mark.django_db
def test_the_staff_directory_closes_the_accounts_of_those_who_left(lecturer, make_person, ecosystem):  # noqa: F811
    """Item 1.22: a member of staff the HRMS lists as separated, or no longer lists, goes inactive and their
    account closes; the post and unit come across for required training (item 5.05)."""
    from integration.hrms import sync_staff

    leaver = make_person("staff", "E0050", "Gone", "Away")
    ecosystem["staff"] = [
        {**STAFF, "position_title": "Lecturer II", "unit_code": "AGRO", "status": "active"},
        {
            **STAFF,
            "employee_no": "E0007",
            "first_name": "New",
            "last_name": "Hire",
            "status": "active",
            "supervisor_employee_no": "E0001",
        },
        {**STAFF, "employee_no": "E0008", "first_name": "Left", "last_name": "Early", "status": "separated"},
    ]
    result = sync_staff()
    assert result["ok"] == 3
    lecturer.refresh_from_db()
    assert (lecturer.post_title, lecturer.unit_code, lecturer.is_active) == ("Lecturer II", "AGRO", True)
    assert PersonRef.objects.get(external_id="E0007").supervisor == lecturer
    assert PersonRef.objects.get(external_id="E0008").is_active is False
    leaver.refresh_from_db()
    leaver.user.refresh_from_db()
    assert leaver.is_active is False and leaver.user.is_active is False
    assert IntegrationRun.objects.get(pk=result["run"]).errors[0]["code"] == "not_listed"


@pytest.mark.django_db
def test_the_directory_moves_and_clears_supervisors(lecturer, make_person, ecosystem):  # noqa: F811
    """Decision D13: supervisor_employee_no in the directory decides who approves staff-development requests
    (staffdev.enrolment.approver_for); a change of supervisor, or none, comes across too."""
    from integration.hrms import sync_staff
    from staffdev.enrolment import approver_for

    other = make_person("staff", "E0002", "Ram", "Das")
    hire = {**STAFF, "employee_no": "E0007", "first_name": "New", "last_name": "Hire"}
    others = [STAFF, {**STAFF, "employee_no": "E0002"}]
    ecosystem["staff"] = [*others, {**hire, "supervisor_employee_no": "E0001"}]
    sync_staff()
    person = PersonRef.objects.get(external_id="E0007")
    assert approver_for(person) == lecturer
    ecosystem["staff"] = [*others, {**hire, "supervisor_employee_no": "E0002"}]
    sync_staff()
    person.refresh_from_db()
    assert person.supervisor == other
    ecosystem["staff"] = [*others, hire]  # a directory that does not send the field changes nothing
    sync_staff()
    person.refresh_from_db()
    assert person.supervisor == other
    ecosystem["staff"] = [*others, {**hire, "supervisor_employee_no": None}]
    sync_staff()
    person.refresh_from_db()
    assert person.supervisor is None and approver_for(person) is None


@pytest.mark.django_db
def test_an_unreadable_directory_changes_nobody(lecturer, ecosystem, monkeypatch):  # noqa: F811
    from integration import hrms

    def down(*args, **kwargs):
        raise IntegrationError("down")

    monkeypatch.setattr(hrms, "pages", down)
    assert hrms.sync_staff()["stopped"] == "down"
    lecturer.refresh_from_db()
    assert lecturer.is_active


@pytest.mark.django_db
def test_scheduled_pushes_skip_quietly_when_not_configured(settings):
    from integration import tasks

    settings.HRMS_API_URL = settings.SRMS_API_URL = ""
    assert tasks.push_training() == {"skipped": True}
    assert tasks.push_marks() == {"skipped": True}
    assert tasks.sync_staff() == {"skipped": True}
    assert tasks.report_completion(1) == {"skipped": True}
    assert not IntegrationRun.objects.exists()


@pytest.mark.django_db
def test_scheduled_pushes_run_when_configured(lecturer, site, ecosystem):  # noqa: F811
    from integration import tasks

    completion = _staff_completion(lecturer)
    assert tasks.report_completion(completion.pk)["ok"] == 1
    assert tasks.push_training()["ok"] == 0
    assert tasks.push_marks()["ok"] == 1
    assert tasks.sync_staff()["ok"] == 1


@pytest.mark.django_db
def test_administrators_see_the_runs(lecturer, make_user, client_for, ecosystem):  # noqa: F811
    from integration.hrms import push_training

    ecosystem["unknown"] = {"E0001"}
    _staff_completion(lecturer)
    push_training()
    admin = make_user("admin", "administrator")
    client = client_for(admin)
    body = client.get("/api/v1/integration-runs/?failed=1&kind=training_push").json()
    assert body["count"] == 1 and body["results"][0]["errors"][0]["code"] == "unknown_employee"
    assert client.get(f"/api/v1/integration-runs/{body['results'][0]['id']}/").status_code == 200
    assert client_for(lecturer.user).get("/api/v1/integration-runs/").status_code == 403


@pytest.mark.django_db
def test_the_command_reads_staff_and_pushes(lecturer, site, ecosystem, capsys):  # noqa: F811
    from django.core.management import call_command

    call_command("sync_ecosystem", staff=True, push_marks=True, push_training=True)
    out = capsys.readouterr().out
    assert "staff:" in out and "training:" in out
