"""The shared content library (item 5.14): shelves by department, open educational resources with their
licences, sharing a course's item or question bank, and using an item in another course."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from audit.models import AuditLog
from courses.models import ContentItem, CourseSite, Membership, Module
from iam.models import Role, RoleScope
from library.models import LibraryItem, SharedBank
from packages.models import ContentPackage
from packages.tests import scorm12
from quizzes.models import Question, QuestionBank, QuestionCategory, QuestionVersion

URL = "/api/v1/library/items/"


def pdf(name="guide.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.7 fictional FAO guide")


@pytest.fixture
def module(site):
    return Module.objects.create(site=site, title="Week 1", position=1)


@pytest.fixture
def teacher(lecturer, client_for, agronomy):
    # Roles change first: a change of roles signs the person out.
    return client_for(lecturer.user)


@pytest.fixture
def agronomy(lecturer):
    RoleScope.objects.create(user=lecturer.user, role=Role.objects.get(code="lecturer"), unit_code="AGRON")
    return "AGRON"


def oer(**extra):
    return {
        "kind": "file",
        "title": "Integrated pest management",
        "file": pdf(),
        "licence": "open_licence",
        "open_licence": "cc_by",
        "source": "FAO e-learning Academy, 2025",
        "publisher": "FAO",
        "is_open_resource": True,
        **extra,
    }


@pytest.mark.django_db
def test_open_resources_come_in_with_their_licence(teacher, agronomy):
    made = teacher.post(URL, oer(department_code=agronomy), format="multipart")
    assert made.status_code == 201, made.content
    body = made.json()
    assert body["is_open_resource"] and body["publisher"] == "FAO" and body["filename"] == "guide.pdf"
    assert body["may_change"] and body["download_url"]
    assert AuditLog.objects.filter(entity="library.libraryitem", action="create").exists()
    assert "licence" in teacher.post(URL, oer(licence="gsa_own"), format="multipart").json()
    assert "publisher" in teacher.post(URL, oer(publisher=""), format="multipart").json()
    assert "open_licence" in teacher.post(URL, oer(open_licence=""), format="multipart").json()
    assert "source" in teacher.post(URL, oer(source=""), format="multipart").json()
    renamed = SimpleUploadedFile("notes.pdf", b"<html>not a pdf</html>")
    assert "file" in teacher.post(URL, oer(file=renamed), format="multipart").json()


@pytest.mark.django_db
def test_links_pages_and_packages(teacher):
    link = {
        "kind": "link",
        "title": "CABI Compendium",
        "url": "https://www.cabi.org/",
        "licence": "permission_held",
    }
    assert "source" in teacher.post(URL, link, format="json").json()
    assert teacher.post(URL, {**link, "source": "CABI"}, format="json").status_code == 201
    assert "url" in teacher.post(URL, {**link, "url": "", "source": "CABI"}, format="json").json()
    page = teacher.post(URL, {"kind": "page", "title": "Rules", "body": "Wash hands", "body_format": "text",
                              "licence": "gsa_own"}, format="json")  # fmt: skip
    assert page.status_code == 201 and page.json()["body"] == "<p>Wash hands</p>"
    package = teacher.post(
        URL, {"kind": "package", "file": scorm12(), "licence": "gsa_own"}, format="multipart"
    )
    assert package.status_code == 201, package.content
    assert package.json()["title"] == "Soil testing" and package.json()["package"]["standard"] == "scorm12"
    broken = teacher.post(
        URL, {"kind": "package", "file": pdf("x.zip"), "licence": "gsa_own"}, format="multipart"
    )
    assert "file" in broken.json()
    assert "title" in teacher.post(URL, {"kind": "page", "licence": "gsa_own"}, format="json").json()


@pytest.mark.django_db
def test_who_may_browse_and_who_may_shelve(teacher, student, client_for, agronomy, make_person, course_admin):
    learner = client_for(student.user)
    assert learner.get(URL).status_code == 403
    assert teacher.post(URL, oer(department_code="VETSCI"), format="multipart").status_code == 403
    assert teacher.post(URL, oer(), format="multipart").status_code == 201  # the whole School's shelf
    admin = client_for(course_admin)
    vet = admin.post(URL, oer(department_code="VETSCI"), format="multipart")
    assert vet.status_code == 201
    assert not teacher.get(f"{URL}{vet.json()['id']}/").json()["may_change"]
    assert teacher.patch(f"{URL}{vet.json()['id']}/", {"title": "Mine now"}, format="json").status_code == 403
    assert teacher.delete(f"{URL}{vet.json()['id']}/").status_code == 403
    assert admin.delete(f"{URL}{vet.json()['id']}/").status_code == 204
    listed = teacher.get(URL, {"q": "pest", "open": "true", "department": "-"}).json()["results"]
    assert [i["department_code"] for i in listed] == [""]
    assert teacher.get(URL, {"kind": "link"}).json()["results"] == []


@pytest.mark.django_db
def test_changing_an_item_keeps_its_kind_and_file(teacher, agronomy):
    made = teacher.post(URL, oer(department_code=agronomy), format="multipart").json()
    changed = teacher.patch(
        f"{URL}{made['id']}/", {"title": "IPM", "tags": ["pests", " Soil "]}, format="json"
    )
    assert changed.status_code == 200 and changed.json()["tags"] == ["pests", "Soil"]
    assert teacher.patch(f"{URL}{made['id']}/", {"kind": "link"}, format="json").status_code == 400
    assert (
        teacher.patch(f"{URL}{made['id']}/", {"department_code": "VETSCI"}, format="json").status_code == 403
    )
    assert teacher.get(f"{URL}{made['id']}/download/").status_code == 200


@pytest.mark.django_db
def test_an_item_is_used_in_a_course_as_a_draft(teacher, module, site, agronomy, client_for, make_person):
    made = teacher.post(URL, oer(department_code=agronomy), format="multipart").json()
    used = teacher.post(f"{URL}{made['id']}/use/", {"module": module.id}, format="json")
    assert used.status_code == 201, used.content
    item = ContentItem.objects.get(pk=used.json()["item"])
    assert not item.is_published and item.licence == "open_licence" and item.open_licence == "cc_by"
    assert item.source == "FAO e-learning Academy, 2025" and item.file_size > 0
    assert used.json()["storage"]["used_bytes"] == item.file_size
    other = make_person("staff", "E0300", "Other", "Teacher", "lecturer")
    elsewhere = CourseSite.objects.create(code="X2", title="Elsewhere", is_published=True)
    Membership.objects.create(site=elsewhere, person=other, role="lecturer")
    assert (
        client_for(other.user)
        .post(f"{URL}{made['id']}/use/", {"module": module.id}, format="json")
        .status_code
        == 400
    )
    site.storage_allowance_mb = 0
    site.save()
    assert teacher.post(f"{URL}{made['id']}/use/", {"module": module.id}, format="json").status_code == 400


@pytest.mark.django_db
def test_a_package_in_the_library_is_used_as_a_package(teacher, module):
    made = teacher.post(
        URL, {"kind": "package", "file": scorm12(), "licence": "gsa_own"}, format="multipart"
    ).json()
    used = teacher.post(f"{URL}{made['id']}/use/", {"module": module.id}, format="json").json()
    package = ContentPackage.objects.get(item_id=used["item"])
    assert package.standard == "scorm12" and package.scos[0]["href"] == "index.html"


@pytest.mark.django_db
def test_a_course_item_is_shared_to_the_library(teacher, module, agronomy):
    item = ContentItem.objects.create(
        module=module, kind="file", title="Field sheet", licence="gsa_own", original_name="sheet.pdf"
    )
    item.file.save("sheet.pdf", pdf("sheet.pdf"))
    item.file_size = item.file.size
    item.save()
    shared = teacher.post(
        f"{URL}share/", {"item": item.id, "department_code": agronomy, "tags": ["soil"]}, format="json"
    )
    assert shared.status_code == 201, shared.content
    copy = LibraryItem.objects.get(pk=shared.json()["id"])
    assert copy.shared_from == item and copy.file.name != item.file.name and copy.tags == ["soil"]
    package_item = teacher.post(
        "/api/v1/packages/",
        {"module": module.id, "file": scorm12(), "licence": "gsa_own"},
        format="multipart",
    ).json()["item"]
    shared_package = teacher.post(f"{URL}share/", {"item": package_item}, format="json").json()
    assert shared_package["package"]["standard"] == "scorm12"
    item.licence = "unknown"
    item.save()
    assert teacher.post(f"{URL}share/", {"item": item.id}, format="json").json()["code"] == "licence_unknown"
    item.licence, item.under_review = "gsa_own", True
    item.save()
    assert teacher.post(f"{URL}share/", {"item": item.id}, format="json").json()["code"] == "taken_down"


@pytest.mark.django_db
def test_a_course_question_bank_is_shared_to_a_department(
    teacher, site, agronomy, lecturer, client_for, student
):
    bank = QuestionBank.objects.create(site=site, name="AGR101 bank")
    category = QuestionCategory.objects.create(bank=bank, name="Soils")
    question = Question.objects.create(bank=bank, category=category, qtype="truefalse", name="Loam")
    QuestionVersion.objects.create(question=question, text="Loam is a soil.", data={"correct": True})
    Question.objects.create(bank=bank, qtype="essay", name="Old", is_archived=True)
    shared = teacher.post(
        "/api/v1/library/banks/share/",
        {"bank": bank.id, "department_code": agronomy, "licence": "gsa_own", "name": "Soils questions"},
        format="json",
    )
    assert shared.status_code == 201, shared.content
    copy = QuestionBank.objects.get(pk=shared.json()["id"])
    assert copy.department_code == agronomy and copy.site is None and copy.questions.count() == 1
    assert (
        copy.questions.get().category.name == "Soils"
        and copy.questions.get().latest.text == "Loam is a soil."
    )
    assert SharedBank.objects.get(bank=copy).copied_from == bank
    listed = teacher.get("/api/v1/library/banks/").json()
    assert listed[0]["licence"] == "gsa_own" and listed[0]["questions"] == 1
    refused = teacher.post(
        "/api/v1/library/banks/share/",
        {"bank": bank.id, "department_code": "VETSCI", "licence": "gsa_own"},
        format="json",
    )
    assert refused.status_code == 403
    assert client_for(student.user).get("/api/v1/library/banks/").status_code == 403
    unsourced = teacher.post(
        "/api/v1/library/banks/share/",
        {"bank": bank.id, "department_code": agronomy, "licence": "fair_dealing"},
        format="json",
    )
    assert "source" in unsourced.json()
