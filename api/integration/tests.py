from datetime import date

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from assessments.models import Mark, Submission
from courses.models import Completion, CourseSite, Membership
from integration.models import ServiceClient
from people.models import PersonRef

OFFERING = {
    "code": "AGR101-2026-27-S1-MRP",
    "course_code": "AGR101",
    "title": "Introduction to Crop Science",
    "term_code": "2026-27-S1",
    "campus_code": "MRP",
    "lecturer_employee_no": "E0001",
    "coursework_weight": "40.00",
}
ROSTER = [
    {
        "student_no": "26MRP0001",
        "first_name": "Ravi",
        "last_name": "Singh",
        "email": "",
        "campus_code": "MRP",
    },
    {
        "student_no": "26MRP0002",
        "first_name": "Devi",
        "last_name": "Ramnarine",
        "email": "",
        "campus_code": "MRP",
    },
]
STAFF = {
    "employee_no": "E0001",
    "first_name": "Asha",
    "last_name": "Persaud",
    "email": "asha@gsa.edu.gy",
    "campus_code": "MRP",
}


@pytest.fixture
def ecosystem(settings, monkeypatch):
    """Stand-ins for the SRMS and HRMS: the HTTP client is replaced, everything else is real."""
    from integration import hrms, srms

    settings.SRMS_API_URL, settings.SRMS_API_KEY = "http://srms-api:8000", "k"
    settings.HRMS_API_URL, settings.HRMS_API_KEY = "http://hrms-api:8000", "k"
    state = {"roster": list(ROSTER), "staff": [STAFF], "posted": []}

    def fake_pages(base, key, path, params=None):
        if "offerings" in path:
            return iter([OFFERING])
        if "enrolments" in path:
            return iter(state["roster"])
        if "staff" in path:
            return iter(state["staff"])
        raise AssertionError(path)

    def fake_call(base, key, path, params=None, data=None):
        state["posted"].append((path, data))
        if "coursework-marks" in path:
            return {
                "offering_code": data["offering_code"],
                "accepted": [m["student_no"] for m in data["marks"]],
                "locked": [],
                "unknown": [],
            }
        if "training-completions" in path:
            return {"created": True}
        if path.endswith("/org/"):
            return {
                "campuses": [{"code": "MRP", "name": "Mon Repos Campus", "region": "Region 4"}],
                "units": [],
            }
        raise AssertionError(path)

    monkeypatch.setattr(srms, "pages", fake_pages)
    monkeypatch.setattr(srms, "call", fake_call)
    monkeypatch.setattr(hrms, "call", fake_call)
    monkeypatch.setattr(hrms, "pages", fake_pages)
    return state


@pytest.mark.django_db
def test_sites_and_class_lists_come_from_the_srms(seeded, ecosystem):
    from integration.srms import sync_sites

    assert sync_sites() == {"sites": 1, "lecturers": 1, "students": 2, "deactivated": 0}
    site = CourseSite.objects.get(code=OFFERING["code"])
    assert site.title == "AGR101 Introduction to Crop Science" and site.source == "srms"
    lecturer = PersonRef.objects.get(kind="staff", external_id="E0001")
    assert lecturer.full_name == "Asha Persaud"  # name resolved from the HRMS
    assert Membership.objects.get(site=site, person=lecturer).role == "lecturer"

    # A student drops the course in the SRMS: the membership is deactivated, not deleted.
    ecosystem["roster"] = ROSTER[:1]
    assert sync_sites()["deactivated"] == 1
    dropped = Membership.objects.get(site=site, person__external_id="26MRP0002")
    assert dropped.is_active is False
    assert Membership.objects.filter(site=site).count() == 3


@pytest.mark.django_db
def test_coursework_totals_are_returned_to_the_srms(site, assignment, student, ecosystem):
    from integration.srms import push_marks

    submission = Submission.objects.create(
        assignment=assignment, student=student, text="x", submitted_at=timezone.now()
    )
    Mark.objects.create(submission=submission, mark=35)  # 35/50 = 70%
    result = push_marks(site)
    assert result["accepted"] == ["26MRP0001"]
    path, data = ecosystem["posted"][-1]
    assert path == "/api/v1/integration/coursework-marks/"
    assert data == {"offering_code": site.code, "marks": [{"student_no": "26MRP0001", "mark": "70.00"}]}

    local = CourseSite.objects.create(code="LOCAL-1", title="Local site", source="local")
    assert push_marks(local)["skipped"] == "not an SRMS offering"


@pytest.mark.django_db
def test_staff_training_completions_are_reported_to_the_hrms_once(lecturer, ecosystem):
    from integration.hrms import push_training

    site = CourseSite.objects.create(
        code="SD-101", title="Records management for HR officers", kind="staff_development", is_published=True
    )
    Completion.objects.create(
        site=site, person=lecturer, completed_on=date(2026, 10, 9), certificate="Certificate"
    )
    assert push_training() == {"reported": 1}
    path, data = ecosystem["posted"][-1]
    assert path.endswith("/training-completions/")
    assert data["external_ref"] == "lms:SD-101:E0001" and data["employee_no"] == "E0001"
    assert push_training() == {"reported": 0}


@pytest.mark.django_db
def test_integration_api_requires_a_scoped_key(site):
    _, key = ServiceClient.issue("srms", ["sites:read"])
    anonymous = APIClient().get("/api/v1/integration/sites/")
    assert anonymous.status_code in (401, 403)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")
    body = client.get("/api/v1/integration/sites/").json()
    assert body["count"] == 1 and body["results"][0]["code"] == site.code


@pytest.mark.django_db
def test_a_key_held_by_the_platform_is_registered_without_being_printed(monkeypatch, capsys):
    from django.core.management import CommandError, call_command

    key = "k" * 43
    monkeypatch.setenv("SERVICE_KEY_TEST", key)
    call_command("create_service_client", name="sibling", scopes=["sites:read"], key_env="SERVICE_KEY_TEST")
    assert key not in capsys.readouterr().out
    client = ServiceClient.authenticate(key)
    assert client is not None and client.name == "sibling" and client.scopes == ["sites:read"]

    monkeypatch.setenv("SERVICE_KEY_TEST", "too-short")
    with pytest.raises(CommandError):
        call_command(
            "create_service_client", name="sibling", scopes=["sites:read"], key_env="SERVICE_KEY_TEST"
        )
    assert ServiceClient.authenticate(key) is not None


@pytest.mark.django_db
def test_demonstration_content_follows_the_class_lists_and_is_idempotent(seeded, ecosystem):
    from decimal import Decimal

    from django.core.management import CommandError, call_command

    from assessments.models import Assignment
    from assessments.services import coursework_percent
    from courses.models import Announcement, ContentItem, Module

    with pytest.raises(CommandError):
        call_command("seed_demo", verbosity=0)
    assert not CourseSite.objects.exists()

    ecosystem["roster"] = ROSTER + [
        {"student_no": "26MRP0003", "first_name": "Joshua", "last_name": "Henry", "campus_code": "MRP"},
        {"student_no": "26MRP0004", "first_name": "Alicia", "last_name": "Gomes", "campus_code": "MRP"},
    ]
    ecosystem["staff"] = [
        STAFF,
        {**STAFF, "employee_no": "E0006", "first_name": "Natasha", "last_name": "Khan"},
    ]

    def counts():
        return tuple(
            model.objects.count()
            for model in (
                CourseSite,
                Module,
                ContentItem,
                Announcement,
                Assignment,
                Submission,
                Mark,
                Completion,
            )
        )

    call_command("seed_demo", fictional=True, verbosity=0)
    first = counts()
    call_command("seed_demo", fictional=True, verbosity=0)
    assert counts() == first == (2, 3, 4, 1, 2, 3, 2, 1)

    site = CourseSite.objects.get(code=OFFERING["code"])
    assert site.is_published and site.announcements.get().author.external_id == "E0001"
    people = {p.last_name: p for p in PersonRef.objects.filter(kind="student")}
    # name order: Gomes and Henry are marked, Ramnarine waits for a mark, Singh has not submitted
    assert coursework_percent(site, people["Gomes"]) == Decimal("84.00")
    assert coursework_percent(site, people["Henry"]) == Decimal("76.00")
    assert coursework_percent(site, people["Ramnarine"]) is None
    assert coursework_percent(site, people["Singh"]) == Decimal("0.00")
    assert Submission.objects.get(student=people["Henry"]).is_late

    # the staff-development site takes only staff the HRMS knows, and one of them has completed it
    staff_site = CourseSite.objects.get(code="SD-101")
    assert staff_site.kind == "staff_development" and staff_site.source == "local"
    assert [m.person.external_id for m in staff_site.memberships.all()] == ["E0006"]
    assert staff_site.completions.get().person.full_name == "Natasha Khan"
