"""Fixtures for practical assessment: a published task with a three-criterion checklist on the AGR101 site,
a field assessor, and a competency framework the site follows."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

FRAMEWORK = {
    "code": "AGR-CROP-L2",
    "title": "Crop Production Level 2",
    "source": "Council for TVET occupational standard",
    "version": "2024.1",
    "units": [
        {
            "code": "U1",
            "title": "Prepare land for planting",
            "elements": [
                {
                    "code": "E1.1",
                    "title": "Prepare beds",
                    "criteria": [
                        {"code": "PC1.1.1", "text": "Beds are formed to the specified width"},
                        {"code": "PC1.1.2", "text": "Tools are cleaned and stored after use"},
                    ],
                }
            ],
        },
        {
            "code": "U2",
            "title": "Apply fertiliser",
            "elements": [
                {
                    "code": "E2.1",
                    "title": "Calculate rates",
                    "criteria": [{"code": "PC2.1.1", "text": "Rate is calculated for the area"}],
                }
            ],
        },
    ],
}


def now_iso(**delta) -> str:
    return (timezone.now() + timedelta(**delta)).isoformat()


def today_iso() -> str:
    """Today's date, by the server's local (Guyana) calendar day.

    A work date is compared against `timezone.localdate()`, not UTC, so a test that writes "today" for
    work_date must use this rather than slicing `now_iso()`: between 20:00 and 23:59 Guyana time (00:00-03:59
    UTC) the UTC calendar date is already tomorrow's, and that date would be refused as in the future.
    """
    return timezone.localdate().isoformat()


def photo(name="plot 7.jpg"):
    return SimpleUploadedFile(name, b"\xff\xd8\xff\xe0" + b"0" * 64, content_type="image/jpeg")


@pytest.fixture
def task(site):
    from practicals.models import PracticalCriterion, PracticalTask

    task = PracticalTask.objects.create(
        site=site,
        title="Prepare a vegetable bed",
        unit_type="crop_plot",
        location="Plot 7",
        weight=2,
        is_published=True,
        max_attempts=2,
    )
    PracticalCriterion.objects.create(task=task, position=1, text="Bed formed to 1.2 m", is_critical=True)
    PracticalCriterion.objects.create(
        task=task, position=2, text="Soil tilth", kind="scored", max_score=5, pass_score=3
    )
    PracticalCriterion.objects.create(task=task, position=3, text="Tools cleaned")
    return task


@pytest.fixture
def criteria(task):
    return list(task.criteria.all())


@pytest.fixture
def passing(criteria):
    """A checklist with every criterion passed: 1 + 4 + 1 of 7."""
    return [
        {"criterion": criteria[0].id, "passed": True},
        {"criterion": criteria[1].id, "score": 4, "comment": "Fine tilth"},
        {"criterion": criteria[2].id, "passed": True},
    ]


@pytest.fixture
def failing(criteria):
    """The critical criterion failed: 0 + 2 + 1 of 7."""
    return [
        {"criterion": criteria[0].id, "passed": False, "comment": "Bed too narrow"},
        {"criterion": criteria[1].id, "score": 2},
        {"criterion": criteria[2].id, "passed": True},
    ]


@pytest.fixture
def field_assessor(make_person, site):
    from practicals.models import PracticalAssessor

    person = make_person("staff", "E0100", "Mark", "Bovell")
    PracticalAssessor.objects.create(site=site, person=person, note="Farm manager")
    return person


@pytest.fixture
def framework(db):
    from practicals.serializers import FrameworkImportSerializer

    data = FrameworkImportSerializer(data=FRAMEWORK)
    data.is_valid(raise_exception=True)
    return data.save()


@pytest.fixture
def followed(site, framework):
    from practicals.models import SiteFramework

    SiteFramework.objects.create(site=site, framework=framework)
    return framework


@pytest.fixture
def observe(client_for, lecturer):
    """Record an observation as the lecturer (or another client) and return the response."""

    def _observe(task, student, results, client=None, **extra):
        client = client or client_for(lecturer.user)
        body = {"student": student.id, "observed_at": now_iso(minutes=-5), "results": results, **extra}
        return client.post(f"/api/v1/practical-tasks/{task.id}/observations/", body, format="json")

    return _observe


@pytest.fixture
def mapped(task, criteria, followed):
    """The critical criterion (bed width) and tools-cleaned map to unit U1, which the fixture returns."""
    from practicals.models import PerformanceCriterion

    criteria[0].performance_criteria.add(PerformanceCriterion.objects.get(code="PC1.1.1"))
    criteria[2].performance_criteria.add(PerformanceCriterion.objects.get(code="PC1.1.2"))
    return followed.units.get(code="U1")
