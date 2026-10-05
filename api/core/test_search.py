"""Items 2.07 to 2.09: search finds only what the person could open, and is not audited."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient


@pytest.fixture
def library(site, lecturer, other_student, make_person, assignment):
    """On the class's site: items published, draft, under review and held back until another is complete;
    a draft assignment; a published and a draft quiz. A draft site and another site the student is not on,
    each with matching names, and a member of staff on no site at all."""
    from assessments.models import Assignment
    from courses.models import ContentItem, CourseSite, Membership, Module
    from quizzes.models import Quiz

    module = Module.objects.create(site=site, title="Week 1")
    outline = ContentItem.objects.create(module=module, title="Soil outline")
    ContentItem.objects.create(module=module, title="Soil draft notes", is_published=False)
    ContentItem.objects.create(module=module, title="Soil chapter under review", under_review=True)
    ContentItem.objects.create(module=module, title="Soil test answers", requires_item=outline)
    Assignment.objects.create(
        site=site, title="Soil draft task", due_at=timezone.now() + timedelta(days=9), max_mark=10
    )
    Quiz.objects.create(site=site, title="Soil quiz", is_published=True)
    Quiz.objects.create(site=site, title="Soil quiz draft")
    draft = CourseSite.objects.create(code="SOIL900-DRAFT", title="Soil science (draft)")
    other = CourseSite.objects.create(code="SOIL200-2026", title="Soil fertility", is_published=True)
    stranger = make_person("student", "26MRP0099", "Devika", "Soil", "student")
    Membership.objects.create(site=other, person=stranger, role="student")
    Membership.objects.create(site=draft, person=lecturer, role="lecturer")
    ContentItem.objects.create(
        module=Module.objects.create(site=other, title="Week 1"), title="Soil fertility notes"
    )
    return {
        "draft": draft,
        "other": other,
        "stranger": stranger,
        "nobody": make_person("staff", "E0777", "Soila", "Ng"),
    }


def _titles(body, kind):
    return [hit["title"] for hit in body[kind]]


@pytest.mark.django_db
def test_search_refuses_anyone_not_signed_in_and_a_lecturer_without_a_code(lecturer, site):
    refused = APIClient().get("/api/v1/search/", {"q": "soil"})
    assert refused.status_code == 403 and refused.json()["code"] == "not_authenticated"
    unverified = APIClient()
    unverified.force_login(lecturer.user)
    response = unverified.get("/api/v1/search/", {"q": "soil"})
    assert response.status_code == 403 and response.json()["code"] == "mfa_required"


@pytest.mark.django_db
def test_search_needs_two_letters(client_for, student, site):
    client = client_for(student.user)
    for q in ("", " s ", "x"):
        response = client.get("/api/v1/search/", {"q": q})
        assert response.status_code == 400
        assert response.json() == {"code": "bad_request", "detail": "Type at least two letters."}


@pytest.mark.django_db
def test_a_student_finds_only_what_they_can_open_and_never_people(client_for, student, site, library):
    from audit.models import AuditLog

    before = AuditLog.objects.count()
    body = client_for(student.user).get("/api/v1/search/", {"q": "soil"}).json()
    assert _titles(body, "sites") == []  # neither the draft site nor one they are not on
    assert _titles(body, "content") == ["Soil outline"]
    assert _titles(body, "assignments") == ["Soil sampling report"]
    assert _titles(body, "quizzes") == ["Soil quiz"]
    assert body["people"] == []  # a student never finds people, not even classmates
    hit = body["assignments"][0]
    due = timezone.localtime(timezone.now() + timedelta(days=7))
    assert (
        hit["sub"] == f"{site.title} · due {due:%d/%m/%Y}" and hit["link"] == f"/sites/{site.id}/assignments"
    )
    assert body["content"][0]["link"] == f"/sites/{site.id}" and body["content"][0]["sub"] == site.title
    assert body["quizzes"][0]["link"] == f"/sites/{site.id}/quizzes"
    sites = client_for(student.user).get("/api/v1/search/", {"q": "agr101"}).json()["sites"]
    assert sites == [{"id": site.id, "title": site.title, "sub": site.code, "link": f"/sites/{site.id}"}]
    assert AuditLog.objects.count() == before  # a search is a read and is not audited


@pytest.mark.django_db
def test_a_lecturer_finds_drafts_and_the_people_on_the_sites_they_teach(
    client_for, lecturer, other_student, site, library
):
    body = client_for(lecturer.user).get("/api/v1/search/", {"q": "soil"}).json()
    assert _titles(body, "sites") == ["Soil science (draft)"]
    assert _titles(body, "content") == [
        "Soil chapter under review",
        "Soil draft notes",
        "Soil outline",
        "Soil test answers",
    ]
    assert _titles(body, "assignments") == ["Soil sampling report", "Soil draft task"]
    assert _titles(body, "quizzes") == ["Soil quiz", "Soil quiz draft"]
    assert body["people"] == []  # Devika Soil studies a site this lecturer does not teach
    people = client_for(lecturer.user).get("/api/v1/search/", {"q": "devi ram"}).json()["people"]
    assert people == [
        {
            "id": other_student.id,
            "title": "Devi Ramnarine",
            "sub": "26MRP0002 · Student",
            "link": f"/sites/{site.id}",
        }
    ]
    by_number = client_for(lecturer.user).get("/api/v1/search/", {"q": "26MRP0002"}).json()["people"]
    assert [p["id"] for p in by_number] == [other_student.id]


@pytest.mark.django_db
def test_course_administrators_and_auditors_find_anyone(client_for, course_admin, make_user, library):
    for user in (course_admin, make_user("aud", "auditor")):
        body = client_for(user).get("/api/v1/search/", {"q": "soil"}).json()
        people = {p["title"]: p for p in body["people"]}
        assert set(people) == {"Devika Soil", "Soila Ng"}
        assert people["Devika Soil"]["link"] == f"/sites/{library['other'].id}"
        assert people["Soila Ng"] == {
            "id": library["nobody"].id,
            "title": "Soila Ng",
            "sub": "E0777 · Staff",
            "link": "",
        }
        assert "Soil fertility" in _titles(body, "sites")
    assert len(body["content"]) <= 5
