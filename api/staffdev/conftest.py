"""Fixtures for the staff-development, approvals and certificate tests (Phase 5)."""

import pytest
from django.utils import timezone

from courses.models import ContentItem, CourseSite, ItemCompletion, Module


@pytest.fixture
def staff(make_person):
    """A member of staff who is not a lecturer: the catalogue's usual reader."""
    person = make_person("staff", "E0201", "Joy", "Lall", email="joy@gsa.edu.gy")
    person.post_title, person.unit_code = "Farm Supervisor", "FARM"
    person.save()
    return person


@pytest.fixture
def supervisor(make_person):
    return make_person("staff", "E0202", "Mark", "Boss", email="boss@gsa.edu.gy")


@pytest.fixture
def make_course(db):
    def _make(code="SD-301", title="Farm safety", *, items=2, published=True, **entry):
        from staffdev.models import CatalogueEntry

        site = CourseSite.objects.create(
            code=code, title=title, kind="staff_development", is_published=published, campus_code="MRP"
        )
        module = Module.objects.create(site=site, title="Week 1")
        for n in range(items):
            ContentItem.objects.create(
                module=module, title=f"Page {n + 1}", body="<p>Read</p>", position=n + 1
            )
        values = {"self_enrol": "open", "summary": f"About {title}", "length_hours": 4, **entry}
        CatalogueEntry.objects.create(site=site, **values)
        return site

    return _make


@pytest.fixture
def course(make_course):
    return make_course()


@pytest.fixture
def finish_items():
    """Complete every item of a site for a person, as opening each page would."""

    def _finish(site, person, at=None):
        for item in ContentItem.objects.filter(module__site=site):
            ItemCompletion.objects.get_or_create(
                person=person, item=item, defaults={"completed_at": at or timezone.now(), "how": "viewed"}
            )

    return _finish
