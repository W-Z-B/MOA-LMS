"""Decision D13 (ADR 0019), item 5.05: required training read from the HRMS each night (scope training:read),
kept beside the requirements course administrators keep, and read-only in the LMS while it is."""

import urllib.parse

import pytest
from django.core.management import call_command

from audit.models import AuditLog
from integration import client
from integration.client import IntegrationError
from integration.models import IntegrationRun
from staffdev import required
from staffdev.models import RequiredTraining, TrainingAssignment

HRMS = "http://hrms-api:8000"
LIST = "/api/v1/integration/training-requirements/"
REQUIRED = "/api/v1/staff-development/required/"


def _row(id_, course_code="SD-301", **extra):
    return {
        "id": id_,
        "course_code": course_code,
        "title": f"Requirement {id_}",
        "post_title": None,
        "unit_code": None,
        "campus_code": None,
        "due_days": 30,
        "renewal_months": None,
        "updated_at": "2026-10-01T09:00:00-04:00",
        **extra,
    }


@pytest.fixture
def hrms(settings, monkeypatch):
    """A stand-in for the HRMS's list endpoint at the HTTP client: two rows a page, with "next" links, so the
    real paging (integration.client.pages) is used."""
    import insights.srms  # noqa: F401 - these bind the real call when first imported; import them first
    import integration.hrms
    import integration.srms  # noqa: F401

    settings.HRMS_API_URL, settings.HRMS_API_KEY = HRMS, "k"
    settings.INTEGRATION_RETRY_SECONDS = 0
    state = {"rows": [], "refuse": None, "down": 0, "asked": []}

    def fake_call(base, key, path, params=None, data=None):
        state["asked"].append((path, params))
        if state["down"]:
            state["down"] -= 1
            raise IntegrationError(f"{path} could not be reached")
        if state["refuse"]:
            raise IntegrationError(f"{path} answered HTTP {state['refuse']}", status=state["refuse"])
        assert data is None and key == "k"
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        page = int(query.get("page", ["1"])[0])
        assert path.startswith((LIST, f"{HRMS}{LIST}"))
        rows = state["rows"][(page - 1) * 2 : page * 2]
        more = len(state["rows"]) > page * 2
        return {
            "count": len(state["rows"]),
            "next": f"{HRMS}{LIST}?page={page + 1}&page_size=500" if more else None,
            "previous": None,
            "results": rows,
        }

    monkeypatch.setattr(client, "call", fake_call)
    return state


def _sync():
    from integration.hrms import sync_training_requirements

    return sync_training_requirements()


@pytest.mark.django_db
def test_requirements_are_created_from_every_page_and_assigned(hrms, staff, make_course):
    site = make_course("SD-301", "Farm safety")
    make_course("SD-302", "First aid")
    hrms["rows"] = [
        _row(11, post_title="farm supervisor", due_days=14),
        _row(12, "SD-302", unit_code="FARM", campus_code="MRP", renewal_months=24),
        _row(13, "SD-302", post_title="Bursar"),
    ]
    result = _sync()
    assert (result["ok"], result["failed"], result["stopped"]) == (3, 0, "")
    assert hrms["asked"][0] == (LIST, {"page_size": 500}) and len(hrms["asked"]) == 2  # two pages read
    run = IntegrationRun.objects.get(pk=result["run"])
    assert run.kind == "requirement_sync" and run.errors == []
    first = RequiredTraining.objects.get(hrms_id=11)
    assert (first.site, first.source, first.post_title, first.due_days, first.is_active) == (
        site,
        "hrms",
        "farm supervisor",
        14,
        True,
    )
    second = RequiredTraining.objects.get(hrms_id=12)
    assert (second.unit_code, second.campus_code, second.renewal_months) == ("FARM", "MRP", 24)
    assert AuditLog.objects.filter(action="create", entity="staffdev.requiredtraining").count() == 3
    # The daily run assigns them: the post is matched without regard to case.
    required.daily()
    mine = TrainingAssignment.objects.filter(person=staff).values_list("requirement__hrms_id", flat=True)
    assert set(mine) == {11, 12}
    # Read again unchanged: nothing written, nothing audited.
    _sync()
    assert AuditLog.objects.filter(entity="staffdev.requiredtraining").count() == 3


@pytest.mark.django_db
def test_a_changed_requirement_is_updated_and_audited(hrms, make_course):
    make_course("SD-301")
    other = make_course("SD-302", "First aid")
    hrms["rows"] = [_row(11)]
    _sync()
    hrms["rows"] = [_row(11, "SD-302", due_days=60, post_title="Driver", renewal_months=12)]
    assert _sync()["ok"] == 1
    requirement = RequiredTraining.objects.get(hrms_id=11)
    assert (requirement.site, requirement.due_days, requirement.post_title, requirement.renewal_months) == (
        other,
        60,
        "Driver",
        12,
    )
    change = AuditLog.objects.get(action="update", entity="staffdev.requiredtraining")
    assert change.before["due_days"] == 30 and change.after["due_days"] == 60
    assert change.reason == "From the HRMS"


@pytest.mark.django_db
def test_one_no_longer_listed_is_retired_and_those_kept_in_the_lms_are_left_alone(hrms, make_course):
    site = make_course("SD-301")
    ours = RequiredTraining.objects.create(site=site, post_title="Lecturer")
    hrms["rows"] = [_row(11), _row(12)]
    _sync()
    hrms["rows"] = [_row(12)]
    result = _sync()
    gone = RequiredTraining.objects.get(hrms_id=11)
    assert gone.is_active is False
    assert RequiredTraining.objects.get(hrms_id=12).is_active is True
    ours.refresh_from_db()
    assert ours.is_active is True and ours.source == "lms"
    run = IntegrationRun.objects.get(pk=result["run"])
    assert run.errors == [
        {"ref": "hrms:11", "code": "retired", "detail": "No longer listed by the HRMS: no longer in force."}
    ]
    assert AuditLog.objects.get(action="update", entity_id=gone.pk).reason == "Retired in the HRMS"
    # Listed again: in force again.
    hrms["rows"] = [_row(11), _row(12)]
    _sync()
    gone.refresh_from_db()
    assert gone.is_active is True


@pytest.mark.django_db
def test_an_unknown_course_code_is_reported_with_its_title_and_the_run_carries_on(hrms, make_course):
    make_course("SD-301")
    from courses.models import CourseSite

    CourseSite.objects.create(code="AGR101", title="Crop science", kind="academic")
    hrms["rows"] = [
        _row(11),
        _row(12, "SD-999", title="Safe use of tractors"),
        _row(13, "AGR101", title="Crop science for staff"),  # a course, but not staff development
        _row(14, None, title="Fire warden duties"),
    ]
    result = _sync()
    assert (result["ok"], result["failed"], result["stopped"]) == (1, 0, "")
    errors = IntegrationRun.objects.get(pk=result["run"]).errors
    assert [(e["ref"], e["code"]) for e in errors] == [
        ("hrms:12", "unmatched_course"),
        ("hrms:13", "unmatched_course"),
        ("hrms:14", "unmatched_course"),
    ]
    assert "Safe use of tractors" in errors[0]["detail"] and "SD-999" in errors[0]["detail"]
    assert "Fire warden duties" in errors[2]["detail"]
    assert list(RequiredTraining.objects.values_list("hrms_id", flat=True)) == [11]
    # Once a course administrator makes the course, the next run reads it.
    make_course("SD-999", "Safe use of tractors")
    assert _sync()["ok"] == 2
    # A requirement whose course the LMS does not have stops being in force, noted once.
    hrms["rows"] = [_row(11, "SD-404")]
    errors = IntegrationRun.objects.get(pk=_sync()["run"]).errors
    assert [e["code"] for e in errors] == ["unmatched_course", "retired"]
    assert not RequiredTraining.objects.filter(is_active=True).exists()


@pytest.mark.django_db
def test_a_key_without_the_scope_is_recorded_as_a_failure_and_nothing_is_retired(hrms, make_course):
    make_course("SD-301")
    hrms["rows"] = [_row(11)]
    _sync()
    hrms["refuse"] = 403
    result = _sync()
    assert result["failed"] == 1 and "HTTP 403" in result["stopped"]
    run = IntegrationRun.objects.get(pk=result["run"])
    assert run.errors[0]["code"] == "http_403" and run.finished_at is not None
    assert len(hrms["asked"]) == 2  # a refusal is not tried again
    assert RequiredTraining.objects.get(hrms_id=11).is_active is True


@pytest.mark.django_db
def test_an_hrms_that_cannot_be_reached_is_tried_again_then_stops_the_run(hrms, make_course, settings):
    make_course("SD-301")
    settings.INTEGRATION_ATTEMPTS = 2
    hrms["rows"] = [_row(11)]
    _sync()
    hrms["down"] = 1
    assert _sync()["ok"] == 1  # answered on the second try
    hrms["down"] = 5
    result = _sync()
    assert (result["ok"], result["failed"]) == (0, 0) and "could not be reached" in result["stopped"]
    assert RequiredTraining.objects.get(hrms_id=11).is_active is True


@pytest.mark.django_db
def test_requirements_kept_in_the_hrms_are_read_only_while_it_is_read(
    hrms, make_course, course_admin, client_for, settings
):
    site = make_course("SD-301")
    hrms["rows"] = [_row(11)]
    _sync()
    theirs = RequiredTraining.objects.get(hrms_id=11)
    ours = RequiredTraining.objects.create(site=site, post_title="Lecturer")
    api = client_for(course_admin)

    settings.HRMS_TRAINING_REQUIREMENTS_SYNC = True
    listed = {r["id"]: r for r in api.get(REQUIRED).json()["results"]}
    assert (listed[theirs.pk]["source"], listed[theirs.pk]["editable"]) == ("hrms", False)
    assert (listed[ours.pk]["source"], listed[ours.pk]["editable"]) == ("lms", True)
    refused = api.patch(f"{REQUIRED}{theirs.pk}/", {"due_days": 5}, format="json")
    assert refused.status_code == 409
    assert refused.json()["code"] == "kept_in_hrms" and "kept in the HRMS" in refused.json()["detail"]
    theirs.refresh_from_db()
    assert theirs.due_days == 30
    changed = api.patch(f"{REQUIRED}{ours.pk}/", {"due_days": 5, "source": "hrms"}, format="json")
    assert changed.status_code == 200 and changed.json()["source"] == "lms"
    made = api.post(REQUIRED, {"site": site.pk, "source": "hrms"}, format="json")
    assert made.status_code == 201 and made.json()["source"] == "lms"  # the source is never chosen here
    # Assigning now is not a change to the requirement.
    assert api.post(f"{REQUIRED}{theirs.pk}/assign/").status_code == 200

    settings.HRMS_TRAINING_REQUIREMENTS_SYNC = False  # no longer read: course administrators keep it
    assert api.patch(f"{REQUIRED}{theirs.pk}/", {"due_days": 5}, format="json").status_code == 200


@pytest.mark.django_db
def test_the_nightly_read_runs_only_when_switched_on(hrms, make_course, settings):
    from integration import tasks

    make_course("SD-301")
    hrms["rows"] = [_row(11)]
    settings.HRMS_TRAINING_REQUIREMENTS_SYNC = False
    assert tasks.sync_training_requirements() == {"skipped": True}
    settings.HRMS_TRAINING_REQUIREMENTS_SYNC = True
    settings.HRMS_API_URL = ""
    assert tasks.sync_training_requirements() == {"skipped": True}
    assert not IntegrationRun.objects.exists()
    settings.HRMS_API_URL = HRMS
    assert tasks.sync_training_requirements()["ok"] == 1


@pytest.mark.django_db
def test_the_command_reads_the_requirements(hrms, make_course, monkeypatch, capsys):
    from integration import srms

    make_course("SD-301")
    hrms["rows"] = [_row(11)]
    monkeypatch.setattr(srms, "sync_sites", lambda current_only: {"sites": 0})
    call_command("sync_ecosystem", "--training-requirements")
    assert "training requirements: {" in capsys.readouterr().out
    assert RequiredTraining.objects.filter(hrms_id=11).exists()
