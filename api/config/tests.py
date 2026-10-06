import pytest
from django.db.models import ProtectedError
from django.test import Client
from django.utils import timezone

from courses.models import CourseSite


@pytest.mark.django_db
def test_health_endpoint_reports_ok():
    response = Client().get("/api/health/")
    assert response.status_code == 200
    assert response.json()["database"] is True


@pytest.mark.django_db
def test_api_documentation_is_for_signed_in_people_unless_made_public(settings, student):
    """Item 1.13."""
    settings.API_DOCS_PUBLIC = False
    refused = Client().get("/api/schema/")
    assert refused.status_code == 403 and b"not_authenticated" in refused.content  # rendered as OpenAPI
    signed_in = Client()
    signed_in.force_login(student.user)
    assert signed_in.get("/api/schema/").status_code == 200
    assert signed_in.get("/api/docs/").status_code == 200

    settings.API_DOCS_PUBLIC = True  # development default
    assert Client().get("/api/schema/").status_code == 200


@pytest.mark.django_db
def test_every_refusal_carries_a_code(course_admin, student, site):
    """The framework's own refusals carry a code as well as a sentence (core.exceptions, item 1.14)."""
    anonymous = Client().get("/api/v1/sites/")
    assert anonymous.status_code == 403 and anonymous.json()["code"] == "not_authenticated"

    privileged = Client()
    privileged.force_login(course_admin)  # no authenticator code yet
    assert privileged.get("/api/v1/sites/").json() == {
        "detail": "An authenticator code is required for your role.",
        "code": "mfa_required",
    }

    learner = Client()
    learner.force_login(student.user)
    refused = learner.post("/api/v1/sites/", {"code": "X", "title": "X"}, content_type="application/json")
    assert refused.status_code == 403 and refused.json()["code"] == "permission_denied"
    missing = learner.get("/api/v1/sites/999999/")
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"


@pytest.mark.django_db
def test_removing_a_record_others_still_need_is_a_conflict_not_a_failure(student):
    from assessments.models import Assignment, Submission
    from core.exceptions import api_exception_handler

    other = Assignment.objects.create(
        site=CourseSite.objects.create(code="S", title="S"), title="A", due_at=timezone.now()
    )
    Submission.objects.create(assignment=other, student=student, submitted_at=timezone.now())
    with pytest.raises(ProtectedError) as held:
        student.delete()
    response = api_exception_handler(held.value, {})
    assert response.status_code == 409
    assert response.data == {
        "code": "in_use",
        "detail": "It cannot be removed while 1 submission still refers to it.",
    }
