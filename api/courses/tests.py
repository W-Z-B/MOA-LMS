import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from audit.models import AuditLog
from courses.models import ContentItem, CourseSite, Module
from notifications.models import Notification


@pytest.mark.django_db
def test_people_see_only_their_own_sites(site, student, lecturer, make_person, course_admin, client_for):
    outsider = make_person("student", "26ESQ0009", "Out", "Sider", "student")
    CourseSite.objects.create(code="LIV110-2026-27-S1-MRP", title="LIV110 Poultry", is_published=True)

    assert [s["code"] for s in client_for(student.user).get("/api/v1/sites/").json()["results"]] == [
        site.code
    ]
    assert client_for(student.user).get("/api/v1/sites/").json()["results"][0]["my_role"] == "student"
    assert client_for(lecturer.user).get("/api/v1/sites/").json()["results"][0]["my_role"] == "lecturer"
    assert client_for(outsider.user).get("/api/v1/sites/").json()["count"] == 0
    assert client_for(outsider.user).get(f"/api/v1/sites/{site.id}/contents/").status_code == 404
    assert client_for(course_admin).get("/api/v1/sites/").json()["count"] == 2


@pytest.mark.django_db
def test_unpublished_site_is_hidden_from_students_but_not_from_its_lecturer(
    site, student, lecturer, client_for
):
    CourseSite.objects.filter(pk=site.pk).update(is_published=False)
    assert client_for(student.user).get("/api/v1/sites/").json()["count"] == 0
    teacher = client_for(lecturer.user)
    assert teacher.get("/api/v1/sites/").json()["count"] == 1
    assert (
        teacher.patch(f"/api/v1/sites/{site.id}/", {"is_published": True}, format="json").status_code == 200
    )
    assert client_for(student.user).get("/api/v1/sites/").json()["count"] == 1


@pytest.mark.django_db
def test_lecturer_builds_content_and_students_see_published_items_only(site, student, lecturer, client_for):
    teacher, learner = client_for(lecturer.user), client_for(student.user)
    module = teacher.post("/api/v1/modules/", {"site": site.id, "title": "Week 1: Soils"}, format="json")
    assert module.status_code == 201, module.content
    module_id = module.json()["id"]
    page = teacher.post(
        "/api/v1/content/",
        {"module": module_id, "kind": "page", "title": "Soil horizons", "body": "O, A, B, C and R."},
        format="json",
    )
    draft = teacher.post(
        "/api/v1/content/",
        {"module": module_id, "kind": "page", "title": "Answers", "body": "secret", "is_published": False},
        format="json",
    )
    assert page.status_code == 201 and draft.status_code == 201

    titles = lambda client: [  # noqa: E731
        i["title"]
        for m in client.get(f"/api/v1/sites/{site.id}/contents/").json()["modules"]
        for i in m["items"]
    ]
    assert titles(teacher) == ["Soil horizons", "Answers"]
    assert titles(learner) == ["Soil horizons"]
    # Students cannot author.
    assert (
        learner.post("/api/v1/modules/", {"site": site.id, "title": "Hack"}, format="json").status_code == 403
    )
    assert AuditLog.objects.filter(entity="courses.module", action="create").count() == 1


@pytest.mark.django_db
def test_file_download_is_membership_checked_and_audited(site, student, lecturer, make_person, client_for):
    teacher = client_for(lecturer.user)
    module = Module.objects.create(site=site, title="Week 1")
    upload = SimpleUploadedFile("handout.pdf", b"%PDF-1.4 handout", content_type="application/pdf")
    created = teacher.post(
        "/api/v1/content/",
        {"module": module.id, "kind": "file", "title": "Handout", "file": upload, "licence": "gsa_own"},
        format="multipart",
    )
    assert created.status_code == 201, created.content
    body = created.json()
    assert "file" not in body and body["filename"] == "handout.pdf"

    response = client_for(student.user).get(body["download_url"])
    assert response.status_code == 200 and b"".join(response.streaming_content) == b"%PDF-1.4 handout"
    assert AuditLog.objects.filter(entity="courses.contentitem", action="download").exists()

    outsider = make_person("student", "26ESQ0009", "Out", "Sider", "student")
    assert client_for(outsider.user).get(body["download_url"]).status_code == 404
    ContentItem.objects.filter(pk=body["id"]).update(is_published=False)
    # A draft is unknown to students.
    assert client_for(student.user).get(body["download_url"]).status_code == 404


@pytest.mark.django_db
def test_announcement_notifies_students(site, student, lecturer, client_for):
    posted = client_for(lecturer.user).post(
        "/api/v1/announcements/",
        {"site": site.id, "title": "Field trip Friday", "body": "Meet at the farm gate at 07:30."},
        format="json",
    )
    assert posted.status_code == 201 and posted.json()["author_name"] == "Asha Persaud"
    note = Notification.objects.get(recipient=student.user)
    assert note.title == f"{site.code}: Field trip Friday" and note.emailed


@pytest.mark.django_db
def test_course_files_are_stored_under_random_names_and_keep_the_name_chosen(
    site, lecturer, student, client_for
):
    """Item 1.12."""
    module = Module.objects.create(site=site, title="Week 1")
    upload = SimpleUploadedFile("Asha Persaud week 1.pdf", b"%PDF-1.7 week one")
    created = (
        client_for(lecturer.user)
        .post(
            "/api/v1/content/",
            {"module": module.id, "kind": "file", "title": "Week 1", "file": upload, "licence": "gsa_own"},
            format="multipart",
        )
        .json()
    )
    stored = ContentItem.objects.get(pk=created["id"])
    assert stored.file.name.startswith("content/") and stored.file.name.endswith(".pdf")
    assert "Asha" not in stored.file.name
    assert stored.original_name == "Asha Persaud week 1.pdf" == created["filename"]
    download = client_for(student.user).get(created["download_url"])
    assert "Asha Persaud week 1.pdf" in download["Content-Disposition"]


@pytest.mark.django_db
def test_a_page_disguised_as_a_handout_is_refused(site, lecturer, client_for):
    module = Module.objects.create(site=site, title="Week 1")
    upload = SimpleUploadedFile("handout.pdf", b"<html><script>steal()</script></html>")
    refused = client_for(lecturer.user).post(
        "/api/v1/content/",
        {"module": module.id, "kind": "file", "title": "Handout", "file": upload, "licence": "gsa_own"},
        format="multipart",
    )
    assert refused.status_code == 400
    assert "do not match its name" in refused.json()["file"][0]
    assert not ContentItem.objects.exists()


@pytest.mark.django_db
def test_drafts_are_unknown_to_students_in_every_list(site, lecturer, student, client_for):
    module = Module.objects.create(site=site, title="Week 1")
    ContentItem.objects.create(module=module, title="Notes", body="x")
    draft = ContentItem.objects.create(module=module, title="Answers", body="secret", is_published=False)
    learner = client_for(student.user)
    assert [i["title"] for i in learner.get("/api/v1/content/").json()["results"]] == ["Notes"]
    assert learner.get(f"/api/v1/content/{draft.id}/").status_code == 404
    assert [i["title"] for i in learner.get("/api/v1/modules/").json()["results"][0]["items"]] == ["Notes"]
    teacher = client_for(lecturer.user)
    assert [i["title"] for i in teacher.get("/api/v1/modules/").json()["results"][0]["items"]] == [
        "Notes",
        "Answers",
    ]
