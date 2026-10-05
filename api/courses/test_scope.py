"""Every write settles the site first: a site, or a record on one, that the caller cannot open reads as
unknown, before any other check (item 1.15)."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from assessments.models import Assignment, Mark, Submission
from courses.models import Announcement, ContentItem, CourseSite, Membership, Module


@pytest.fixture
def other_site(make_person):
    """A course on another campus, taught by another lecturer, with its own student and work handed in."""
    teacher = make_person("staff", "E0002", "Bibi", "Khan", "lecturer")
    learner = make_person("student", "26ESQ0001", "Joel", "Adams", "student")
    site = CourseSite.objects.create(
        code="LIV110-2026-27-S1-ESQ", title="LIV110 Poultry", campus_code="ESQ", is_published=True
    )
    Membership.objects.create(site=site, person=teacher, role="lecturer")
    Membership.objects.create(site=site, person=learner, role="student")
    module = Module.objects.create(site=site, title="Week 1")
    item = ContentItem.objects.create(module=module, title="Brooding", body="x")
    work = Assignment.objects.create(
        site=site, title="Flock record", due_at=timezone.now() + timedelta(days=7), is_published=True
    )
    submission = Submission.objects.create(
        assignment=work, student=learner, text="12 birds", submitted_at=timezone.now()
    )
    return {"site": site, "module": module, "item": item, "assignment": work, "submission": submission}


def unknown(response, field: str) -> bool:
    """The answer for an id that does not exist at all."""
    return response.status_code == 400 and "does not exist" in response.json()[field][0]


@pytest.mark.django_db
def test_a_lecturer_cannot_build_on_a_site_of_another_campus(site, lecturer, other_site, client_for):
    teacher = client_for(lecturer.user)
    there = other_site["site"].id
    # The answer is word for word the one for a site that is not there at all.
    module = teacher.post("/api/v1/modules/", {"site": there, "title": "x"}, format="json")
    assert unknown(module, "site")
    nowhere = teacher.post("/api/v1/modules/", {"site": 999999, "title": "x"}, format="json")
    said, said_for_nothing = module.json()["site"][0], nowhere.json()["site"][0]
    assert said.replace(str(there), "?") == said_for_nothing.replace("999999", "?")
    assert unknown(
        teacher.post("/api/v1/announcements/", {"site": there, "title": "x", "body": "x"}, format="json"),
        "site",
    )
    assert unknown(
        teacher.post(
            "/api/v1/assignments/",
            {"site": there, "title": "x", "due_at": "2027-01-01T00:00:00Z"},
            format="json",
        ),
        "site",
    )
    assert unknown(
        teacher.post("/api/v1/content/", {"module": other_site["module"].id, "title": "x"}, format="json"),
        "module",
    )
    assert Module.objects.filter(site_id=there).count() == 1
    assert not Announcement.objects.exists()


@pytest.mark.django_db
def test_records_of_another_site_cannot_be_changed_moved_or_removed(site, lecturer, other_site, client_for):
    teacher = client_for(lecturer.user)
    mine = Module.objects.create(site=site, title="Mine")
    theirs = other_site["module"].id
    assert teacher.patch(f"/api/v1/modules/{theirs}/", {"title": "x"}, format="json").status_code == 404
    assert teacher.delete(f"/api/v1/content/{other_site['item'].id}/").status_code == 404
    site_patch = teacher.patch(f"/api/v1/sites/{other_site['site'].id}/", {"title": "x"}, format="json")
    assert site_patch.status_code == 404
    moved = teacher.patch(f"/api/v1/modules/{mine.id}/", {"site": other_site["site"].id}, format="json")
    assert unknown(moved, "site")
    assert Module.objects.get(pk=mine.pk).site_id == site.id


@pytest.mark.django_db
def test_a_site_one_can_open_but_not_teach_is_refused_before_the_fields_are_read(site, student, client_for):
    learner = client_for(student.user)
    refused = learner.post("/api/v1/modules/", {"site": site.id, "title": ""}, format="json")
    assert refused.status_code == 403 and refused.json()["code"] == "permission_denied"
    module = Module.objects.create(site=site, title="Week 1")
    patched = learner.patch(f"/api/v1/modules/{module.id}/", {"title": ""}, format="json")
    assert patched.status_code == 403
    created = learner.post("/api/v1/sites/", {"code": ""}, format="json")
    assert created.status_code == 403 and created.json()["code"] == "permission_denied"


@pytest.mark.django_db
def test_a_student_cannot_submit_to_a_course_they_are_not_in(site, student, other_site, client_for):
    learner = client_for(student.user)
    url = f"/api/v1/assignments/{other_site['assignment'].id}/submit/"
    refused = learner.post(url, {"text": "mine"}, format="json")
    assert refused.status_code == 404 and refused.json()["code"] == "not_found"
    upload = SimpleUploadedFile("work.pdf", b"%PDF-1.7 mine")
    assert learner.post(url, {"file": upload}, format="multipart").status_code == 404
    assert Submission.objects.count() == 1


@pytest.mark.django_db
def test_work_on_another_site_cannot_be_marked_or_opened(site, lecturer, student, other_site, client_for):
    theirs = other_site["submission"].id
    teacher = client_for(lecturer.user)
    # Even a mark out of range is answered as for a submission that is not there.
    marked = teacher.post(f"/api/v1/submissions/{theirs}/mark/", {"mark": "-5"}, format="json")
    assert marked.status_code == 404 and marked.json()["code"] == "not_found"
    assert teacher.get(f"/api/v1/submissions/{theirs}/download/").status_code == 404
    assert teacher.get(f"/api/v1/assignments/{other_site['assignment'].id}/submissions/").status_code == 404
    assert teacher.get(f"/api/v1/sites/{other_site['site'].id}/gradebook/").status_code == 404
    assert not Mark.objects.exists()

    # Another student's work is unknown to a student; their own may be seen but not marked.
    learner = client_for(student.user)
    assert learner.get(f"/api/v1/submissions/{theirs}/download/").status_code == 404
    one = {"mark": "1"}
    assert learner.post(f"/api/v1/submissions/{theirs}/mark/", one, format="json").status_code == 404
    work = Assignment.objects.create(site=site, title="Own", due_at=timezone.now(), is_published=True)
    own = Submission.objects.create(assignment=work, student=student, text="x", submitted_at=timezone.now())
    assert learner.post(f"/api/v1/submissions/{own.id}/mark/", one, format="json").status_code == 403
