"""Shared test fixtures. Database tests need PostgreSQL (run inside the Compose stack or CI)."""

from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

requires_postgres = pytest.mark.skipif(
    "postgresql" not in settings.DATABASES["default"]["ENGINE"],
    reason="database tests need PostgreSQL; run them in the Compose stack or CI",
)

PASSWORD = "Str0ng-Passw0rd-123"
SITE_CODE = "AGR101-2026-27-S1-MRP"


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.get_closest_marker("django_db"):
            item.add_marker(requires_postgres)


@pytest.fixture(autouse=True)
def _media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "files"


@pytest.fixture(autouse=True)
def _encryption_key(settings):
    settings.FIELD_ENCRYPTION_KEY = "test-only-key"
    from core import crypto

    crypto._fernet.cache_clear()


@pytest.fixture
def seeded(db):
    from django.core.management import call_command

    call_command("seed", "--country", "GY", verbosity=0)


@pytest.fixture
def make_user(seeded):
    def _make(username, *roles, email=""):
        from iam.models import Role, RoleScope

        user = get_user_model().objects.create_user(username=username, password=PASSWORD, email=email)
        for code in roles:
            RoleScope.objects.create(user=user, role=Role.objects.get(code=code))
        return user

    return _make


@pytest.fixture
def client_for():
    def _client(user):
        client = APIClient()
        client.force_login(user)
        session = client.session
        session["mfa_verified"] = True
        session.save()
        return client

    return _client


@pytest.fixture
def make_person(make_user):
    def _make(kind, external_id, first, last, *roles, email=""):
        from people.models import PersonRef

        user = make_user(external_id, *roles, email=email)
        return PersonRef.objects.create(
            kind=kind,
            external_id=external_id,
            first_name=first,
            last_name=last,
            email=email,
            user=user,
            campus_code="MRP",
        )

    return _make


@pytest.fixture
def course_admin(make_user):
    return make_user("course.admin", "course_admin")


@pytest.fixture
def lecturer(make_person):
    return make_person("staff", "E0001", "Asha", "Persaud", "lecturer", email="asha@gsa.edu.gy")


@pytest.fixture
def student(make_person):
    return make_person("student", "26MRP0001", "Ravi", "Singh", "student", email="ravi@students.gsa.edu.gy")


@pytest.fixture
def other_student(make_person):
    return make_person("student", "26MRP0002", "Devi", "Ramnarine", "student")


@pytest.fixture
def site(lecturer, student, other_student):
    from courses.models import CourseSite, Membership

    site = CourseSite.objects.create(
        code=SITE_CODE,
        title="AGR101 Introduction to Crop Science",
        term_code="2026-27-S1",
        campus_code="MRP",
        source="srms",
        is_published=True,
    )
    Membership.objects.create(site=site, person=lecturer, role="lecturer")
    Membership.objects.create(site=site, person=student, role="student")
    Membership.objects.create(site=site, person=other_student, role="student")
    return site


@pytest.fixture
def assignment(site):
    from assessments.models import Assignment

    return Assignment.objects.create(
        site=site,
        title="Soil sampling report",
        due_at=timezone.now() + timedelta(days=7),
        max_mark=50,
        weight=2,
        is_published=True,
    )
