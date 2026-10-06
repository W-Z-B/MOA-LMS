"""Items 3.11 and 6.10: course outlines from the SRMS; competency results and outcome standings back to it.
HTTP is mocked: once at the edge (urllib) to check what goes over the wire, otherwise at the client."""

import io
import json
from datetime import date

import pytest

from insights import srms
from insights.models import Outcome, OutcomeLink, SiteProfile
from insights.tests.conftest import hand_in
from integration.client import IntegrationError
from integration.models import IntegrationRun

pytestmark = pytest.mark.django_db


@pytest.fixture
def configured(settings):
    settings.SRMS_API_URL, settings.SRMS_API_KEY = "http://srms-api:8000", "k" * 40
    settings.INTEGRATION_RETRY_SECONDS = 0
    settings.INTEGRATION_ATTEMPTS = 2


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_outlines_are_read_over_http_with_the_service_key(configured, monkeypatch):
    seen = []

    def urlopen(request, timeout):
        seen.append(request)
        body = [{"course_code": "AGR101", "outcomes": [{"code": "LO1", "text": "Sample a soil"}]}]
        return FakeResponse(json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    summary = srms.sync_outcomes()

    request = seen[0]
    assert request.full_url == "http://srms-api:8000/api/v1/integration/course-outcomes/"
    assert request.get_method() == "GET" and request.get_header("Authorization") == f"Api-Key {'k' * 40}"
    assert summary["ok"] == 1 and summary["failed"] == 0
    outcome = Outcome.objects.get()
    assert (outcome.source, outcome.course_code, outcome.code, outcome.text) == (
        "srms",
        "AGR101",
        "LO1",
        "Sample a soil",
    )
    assert IntegrationRun.objects.get().kind == "outcome_sync"


def test_paged_outlines_are_followed_and_outcomes_no_longer_listed_are_kept_inactive(configured, monkeypatch):
    Outcome.objects.create(source="srms", course_code="AGR101", code="OLD", text="Dropped from the outline")
    pages = {
        srms.OUTCOMES_PATH: {
            "results": [{"course_code": "AGR101", "outcomes": [{"code": "LO1", "text": "One"}]}],
            "next": "http://srms-api:8000/api/v1/integration/course-outcomes/?page=2",
        },
        "http://srms-api:8000/api/v1/integration/course-outcomes/?page=2": {
            "results": [
                {
                    "course_code": "ANS201",
                    "outcomes": [{"code": "LO1", "text": "Breeds"}, {"code": "LO2", "text": "Feed"}],
                },
                {"course_code": "", "outcomes": []},
                {"course_code": "BAD1", "outcomes": [{"code": "", "text": "No code"}]},
            ],
            "next": None,
        },
    }
    monkeypatch.setattr(srms, "call", lambda base, key, path, **kw: pages[path])

    summary = srms.sync_outcomes()

    assert summary["ok"] == 3 and summary["failed"] == 2
    assert Outcome.objects.filter(is_active=True).count() == 3
    assert Outcome.objects.get(code="OLD").is_active is False
    errors = IntegrationRun.objects.get().errors
    assert {e["ref"] for e in errors} == {"?", "BAD1"}


def test_an_unreachable_srms_stops_the_run_and_keeps_what_is_held(configured, monkeypatch):
    Outcome.objects.create(source="srms", course_code="AGR101", code="LO1", text="Held")

    def down(*args, **kwargs):
        raise IntegrationError("could not be reached")

    monkeypatch.setattr(srms, "call", down)
    summary = srms.sync_outcomes()
    assert "could not be reached" in summary["stopped"]
    assert Outcome.objects.get().is_active is True


def test_competency_results_and_outcome_standings_are_posted_in_the_agreed_shape(
    configured, site, lecturer, student, monkeypatch, make_assignment
):
    from practicals.models import CompetencyFramework, CompetencyResult, CompetencyUnit

    framework = CompetencyFramework.objects.create(code="AGR-L2", title="Crop production")
    unit = CompetencyUnit.objects.create(framework=framework, code="CP-01", title="Prepare soil")
    other_unit = CompetencyUnit.objects.create(framework=framework, code="CP-02", title="Plant")
    CompetencyResult.objects.create(
        site=site,
        student=student,
        unit=unit,
        status="competent",
        assessor=lecturer,
        decided_on=date(2026, 10, 1),
    )
    CompetencyResult.objects.create(
        site=site,
        student=student,
        unit=other_unit,
        status="not_assessed",
        assessor=lecturer,
        decided_on=date(2026, 10, 1),
    )
    SiteProfile.objects.create(site=site, course_code="AGR101")
    outcome = Outcome.objects.create(source="srms", course_code="AGR101", code="LO1", text="Sample a soil")
    report = make_assignment("Soil report")
    OutcomeLink.objects.create(site=site, outcome=outcome, assignment=report)
    hand_in(report, student, mark=45, released=True)
    sent = []

    def urlopen(request, timeout):
        sent.append(request)
        return FakeResponse(
            json.dumps({"accepted": ["26MRP0001"], "locked": [], "unknown": ["26MRP0009"]}).encode()
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    summary = srms.push_all_competency()

    request = sent[0]
    assert (
        request.full_url.endswith("/api/v1/integration/competency-results/")
        and request.get_method() == "POST"
    )
    rows = json.loads(request.data)
    assert rows[0] == {
        "offering_code": site.code,
        "student_no": "26MRP0001",
        "unit_code": "CP-01",
        "result": "competent",
        "assessed_on": "2026-10-01",
    }
    assert rows[1]["unit_code"] == "LO1" and rows[1]["result"] == "outcome_met"
    assert len(rows) == 2  # nothing for the unit not assessed, nor for students with no released evidence
    assert summary["ok"] == 2
    run = IntegrationRun.objects.get(kind="competency_push")
    assert run.errors[0]["code"] == "unknown_student"


def test_the_push_names_refusals_and_stops_when_the_srms_is_down(configured, site, monkeypatch):
    from courses.models import CourseSite

    CourseSite.objects.create(code="ANS201", title="Other", source="srms", is_published=True)
    CourseSite.objects.create(code="LOCAL1", title="Local", source="local", is_published=True)
    monkeypatch.setattr(srms, "competency_rows", lambda site: [{"offering_code": site.code}])
    calls = []

    def refuse(base, key, path, **kwargs):
        calls.append(kwargs["data"][0]["offering_code"])
        raise IntegrationError("answered HTTP 400", status=400)

    monkeypatch.setattr(srms, "call", refuse)
    summary = srms.push_all_competency()
    assert summary["failed"] == 2 and sorted(calls) == ["AGR101-2026-27-S1-MRP", "ANS201"]

    def down(base, key, path, **kwargs):
        raise IntegrationError("could not be reached")

    monkeypatch.setattr(srms, "call", down)
    assert "could not be reached" in srms.push_all_competency()["stopped"]
    assert srms.push_competency(CourseSite.objects.get(code="LOCAL1"))["skipped"] == "not an SRMS offering"


def test_an_offering_with_nothing_to_send_makes_no_call(configured, site, monkeypatch):
    monkeypatch.setattr(srms, "call", lambda *a, **k: pytest.fail("nothing should be sent"))
    assert srms.push_competency(site)["sent"] == []


def test_the_push_is_off_until_gsa_decides(configured, settings, monkeypatch):
    from insights import tasks

    monkeypatch.setattr(srms, "push_all_competency", lambda: {"pushed": True})
    monkeypatch.setattr(srms, "sync_outcomes", lambda: {"synced": True})
    assert tasks.push_competency() == {"skipped": True}
    settings.SRMS_COMPETENCY_PUSH = True
    assert tasks.push_competency() == {"pushed": True}
    assert tasks.sync_outcomes() == {"synced": True}
    settings.SRMS_API_URL = ""
    assert tasks.sync_outcomes() == {"skipped": True}


def test_the_site_sync_keeps_the_offerings_course_and_programmes(site):
    srms.record_offering(site, {"course_code": "AGR101", "programme_code": "DIP-AG"})
    assert SiteProfile.objects.get(site=site).programme_codes == ["DIP-AG"]
    srms.record_offering(site, {"course_code": "AGR101", "programme_codes": ["DIP-AG", "CERT-AG"]})
    profile = SiteProfile.objects.get(site=site)
    assert profile.course_code == "AGR101" and profile.programme_codes == ["DIP-AG", "CERT-AG"]
    srms.record_offering(site, {"course_code": "AGR101"})
    assert SiteProfile.objects.get(site=site).programme_codes == []
