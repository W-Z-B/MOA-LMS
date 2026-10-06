"""Packaged content (items 5.12, 5.13) and the statement store (item 6.09): checking a package, opening it,
serving its files to the sandboxed player, SCORM commits, H5P statements, completion and coursework."""

import io
import json
import zipfile
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from assessments.services import coursework_working, gradebook
from audit.models import AuditLog
from courses.models import ContentItem, ItemCompletion, Module
from packages import archive
from packages.models import ContentPackage, PackageAttempt, Statement
from packages.services import activity_iri

MANIFEST_12 = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="soil" version="1" xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2">
  <metadata><schema>ADL SCORM</schema><schemaversion>1.2</schemaversion></metadata>
  <organizations default="org"><organization identifier="org"><title>Soil testing</title>
    <item identifier="i1" identifierref="r1"><title>Taking a sample</title></item>
  </organization></organizations>
  <resources><resource identifier="r1" type="webcontent" adlcp:scormtype="sco" href="index.html">
    <file href="index.html"/></resource></resources>
</manifest>"""

MANIFEST_2004 = """<?xml version="1.0"?>
<manifest identifier="m" xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3">
  <metadata><schema>ADL SCORM</schema><schemaversion>2004 4th Edition</schemaversion></metadata>
  <organizations default="o"><organization identifier="o"><title>Pests</title>
    <item identifier="a" identifierref="ra" parameters="?lesson=1"><title>Part one</title></item>
    <item identifier="b" identifierref="rb"><title>Part two</title></item>
  </organization></organizations>
  <resources xml:base="course/">
    <resource identifier="ra" adlcp:scormType="sco" type="webcontent" href="one.html"/>
    <resource identifier="rb" adlcp:scormType="sco" type="webcontent" href="two.html"/>
  </resources>
</manifest>"""

PAGE = b"<!doctype html><html><head><title>Sample</title></head><body>Hello</body></html>"


def zipped(files: dict[str, bytes | str], name="course.zip") -> SimpleUploadedFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive_file:
        for path, data in files.items():
            archive_file.writestr(path, data)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/zip")


def scorm12(**extra) -> SimpleUploadedFile:
    return zipped({"imsmanifest.xml": MANIFEST_12, "index.html": PAGE, "img/a.png": b"\x89PNG", **extra})


def scorm2004() -> SimpleUploadedFile:
    return zipped({"imsmanifest.xml": MANIFEST_2004, "course/one.html": PAGE, "course/two.html": PAGE})


def h5p(with_library=True) -> SimpleUploadedFile:
    files = {
        "h5p.json": json.dumps(
            {
                "title": "Crop quiz",
                "mainLibrary": "H5P.GSATest",
                "preloadedDependencies": [
                    {"machineName": "H5P.GSATest", "majorVersion": 1, "minorVersion": 0}
                ],
            }
        ),
        "content/content.json": "{}",
    }
    if with_library:
        files["H5P.GSATest-1.0/library.json"] = "{}"
        files["H5P.GSATest-1.0/test.js"] = "H5P.GSATest = function () {};"
    return zipped(files, "quiz.h5p")


@pytest.fixture
def module(site):
    return Module.objects.create(site=site, title="Week 1", position=1)


@pytest.fixture
def teacher(lecturer, client_for):
    return client_for(lecturer.user)


@pytest.fixture
def learner(student, client_for):
    return client_for(student.user)


def put_up(client, module, file=None, **extra):
    data = {"module": module.id, "file": file or scorm12(), "licence": "gsa_own", "is_published": True}
    return client.post("/api/v1/packages/", {**data, **extra}, format="multipart")


@pytest.fixture
def package(teacher, module):
    response = put_up(teacher, module)
    assert response.status_code == 201, response.content
    return ContentPackage.objects.get(pk=response.json()["id"])


def launch(client, package, **body):
    return client.post(f"/api/v1/packages/{package.id}/launch/", body, format="json")


def commit(client, launched, cmi):
    return client.post(launched["commit_url"], {"cmi": cmi}, format="json")


# Checking a package


def refusal(upload) -> str:
    with pytest.raises(archive.PackageRefused) as refused:
        archive.check(upload)
    return str(refused.value)


def test_a_scorm_12_package_is_read_from_its_manifest(settings):
    checked = archive.check(scorm12())
    assert checked.standard == "scorm12" and checked.title == "Soil testing"
    assert [s.as_dict() for s in checked.scos] == [
        {"id": "i1", "title": "Taking a sample", "href": "index.html", "parameters": ""}
    ]
    assert checked.entries == 3


def test_a_scorm_2004_package_with_two_parts_and_a_base_folder(settings):
    checked = archive.check(scorm2004())
    assert checked.standard == "scorm2004" and checked.version_label == "SCORM 2004 4th Edition"
    assert [(s.id, s.href, s.parameters) for s in checked.scos] == [
        ("a", "course/one.html", "lesson=1"),
        ("b", "course/two.html", ""),
    ]


def test_an_h5p_file_needs_its_libraries(settings):
    assert archive.check(h5p()).standard == "h5p"
    assert "does not include the library H5P.GSATest-1.0" in refusal(h5p(with_library=False))


@pytest.mark.parametrize(
    "name",
    ["../evil.html", "/etc/passwd", "a\\b.html", "C:/x.html", "a//b.html", "a/./b.html", "x\x01.html"],
)
def test_names_that_leave_the_package_are_refused(settings, name):
    assert "unsafe name" in refusal(scorm12(**{name: b"x"}))


def test_programs_links_reserved_names_and_duplicates_are_refused(settings):
    assert "a program" in refusal(scorm12(**{"tools/setup.exe": b"MZ"}))
    assert "keeps for itself" in refusal(scorm12(**{"__lms__/x.js": b"x"}))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as made:
        made.writestr("imsmanifest.xml", MANIFEST_12)
        made.writestr("index.html", PAGE)
        link = zipfile.ZipInfo("link.html")
        link.external_attr = 0o120777 << 16
        made.writestr(link, "/etc/passwd")
    assert "a link" in refusal(SimpleUploadedFile("c.zip", buffer.getvalue()))
    assert "two files named" in refusal(scorm12(**{"INDEX.HTML": b"x"}))


def test_zip_bombs_and_oversized_packages_are_refused(settings):
    assert "far more than its size" in refusal(scorm12(**{"big.bin": b"\0" * (5 * 1024 * 1024)}))
    settings.PACKAGE_MAX_ENTRIES = 2
    assert "more than 2 files" in refusal(scorm12())
    settings.PACKAGE_MAX_ENTRIES = 100
    settings.PACKAGE_MAX_UNPACKED_MB = 0
    assert "unpacks to more than 0 MB" in refusal(scorm12())
    settings.PACKAGE_MAX_UNPACKED_MB = 100
    settings.UPLOAD_LIMIT_PACKAGE_MB = 0
    assert "larger than 0 MB" in refusal(scorm12())


def test_manifests_with_entities_or_missing_pages_are_refused(settings):
    bomb = '<?xml version="1.0"?><!DOCTYPE m [<!ENTITY a "aaaa">]><manifest>&a;</manifest>'
    assert "document type or entities" in refusal(zipped({"imsmanifest.xml": bomb}))
    assert "not in the package" in refusal(zipped({"imsmanifest.xml": MANIFEST_12}))
    assert "not a SCORM package or an H5P file" in refusal(zipped({"index.html": PAGE}))
    assert "Send a SCORM package" in refusal(SimpleUploadedFile("x.zip", b"%PDF-1.7"))
    assert "not a complete zip" in refusal(SimpleUploadedFile("x.zip", b"PK\x03\x04broken"))
    assert "which SCORM version" in refusal(
        zipped({"imsmanifest.xml": "<manifest><organizations/></manifest>", "index.html": PAGE})
    )


def test_a_damaged_entry_is_refused(settings):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as made:
        made.writestr("imsmanifest.xml", MANIFEST_12)
        made.writestr("index.html", PAGE)
    raw = bytearray(buffer.getvalue())
    at = raw.find(b"Hello")
    raw[at] = ord("J")  # the checksum no longer matches
    assert "damaged" in refusal(SimpleUploadedFile("c.zip", bytes(raw)))


# Putting a package up


@pytest.mark.django_db
def test_teaching_staff_put_a_package_up_as_an_item(teacher, module, site):
    response = put_up(teacher, module, title="", weight="2", max_attempts=2)
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["title"] == "Soil testing" and body["standard"] == "scorm12" and body["weight"] == "2.00"
    assert body["storage"]["used_bytes"] > 0
    item = ContentItem.objects.get(pk=body["item"])
    assert item.kind == "package" and item.file_size > 0 and item.licence == "gsa_own"
    assert AuditLog.objects.filter(entity="packages.contentpackage", action="create").exists()


@pytest.mark.django_db
def test_putting_a_package_up_is_refused_with_reasons(teacher, learner, module):
    refused = put_up(teacher, module, file=SimpleUploadedFile("x.zip", b"%PDF-1.7"))
    assert refused.status_code == 400 and "Send a SCORM package" in refused.json()["file"][0]
    assert put_up(learner, module).status_code == 403
    credited = put_up(teacher, module, licence="open_licence")
    assert "open_licence" in credited.json()
    unsourced = put_up(teacher, module, licence="open_licence", open_licence="cc_by")
    assert "source" in unsourced.json()
    module.site.storage_allowance_mb = 0
    module.site.save()
    assert "storage allowance" in put_up(teacher, module).json()["file"][0]


@pytest.mark.django_db
def test_packages_never_come_through_the_ordinary_content_routes(teacher, learner, package, module):
    made = teacher.post(
        "/api/v1/content/", {"module": module.id, "kind": "package", "title": "X"}, format="json"
    )
    assert made.status_code == 400 and "kind" in made.json()
    changed = teacher.patch(f"/api/v1/content/{package.item_id}/", {"kind": "page"}, format="json")
    assert changed.status_code == 400
    assert (
        teacher.patch(f"/api/v1/content/{package.item_id}/", {"title": "Renamed"}, format="json").status_code
        == 200
    )
    assert learner.get(f"/api/v1/content/{package.item_id}/download/").status_code == 404
    assert teacher.get(f"/api/v1/content/{package.item_id}/download/").status_code == 200
    assert learner.post(f"/api/v1/content/{package.item_id}/complete/").status_code == 409


@pytest.mark.django_db
def test_teaching_staff_set_how_a_package_counts(teacher, learner, package, site):
    from assessments.models import GradeCategory

    category = GradeCategory.objects.create(site=site, name="Online", weight=10)
    changed = teacher.patch(
        f"/api/v1/packages/{package.id}/", {"weight": "3", "grade_category": category.id}, format="json"
    )
    assert changed.status_code == 200 and changed.json()["grade_category"] == category.id
    assert learner.patch(f"/api/v1/packages/{package.id}/", {"weight": "9"}, format="json").status_code == 403
    assert teacher.get(f"/api/v1/packages/?item={package.item_id}").json()["results"][0]["id"] == package.id


# Opening a package and its files


@pytest.mark.django_db
def test_a_student_opens_a_package_in_an_attempt(learner, package, student):
    first = launch(learner, package)
    assert first.status_code == 200, first.content
    body = first.json()
    assert body["attempt"]["number"] == 1 and not body["attempt"]["is_preview"]
    assert body["cmi"]["core"]["student_id"] == student.external_id
    assert body["cmi"]["core"]["entry"] == "ab-initio"
    assert body["play_url"].endswith("/index.html")
    again = launch(learner, package).json()
    assert again["attempt"]["id"] == body["attempt"]["id"]  # the open attempt is continued
    assert AuditLog.objects.filter(action="package_launch").count() == 2


@pytest.mark.django_db
def test_the_player_serves_only_the_package_inside_a_sandbox(learner, package, client):
    launched = launch(learner, package).json()
    page = client.get(launched["play_url"])  # no session: the signed address is enough
    assert page.status_code == 200
    html = page.content
    assert html.startswith(b"<!doctype html><html><head>") and b"cross-frame-api.min.js" in html
    assert html.index(b"gsa-scorm-frame.js") < html.index(b"<title>")
    csp = page["Content-Security-Policy"]
    assert csp.startswith("sandbox allow-scripts") and "allow-same-origin" not in csp
    assert "frame-ancestors 'self'" in csp and page["Referrer-Policy"] == "no-referrer"
    base = launched["play_url"].rsplit("/", 1)[0]
    image = client.get(f"{base}/img/a.png")
    assert image.status_code == 200 and image["Content-Type"] == "image/png"
    assert b"".join(image.streaming_content) == b"\x89PNG"
    assert client.get(f"{base}/imsmanifest.xml")["Content-Type"] == "application/xml"
    assert client.get(f"{base}/missing.html").status_code == 404
    assert client.get(f"{base}/../index.html").status_code == 404
    assert client.get(f"{base}/img").status_code == 404
    assert client.get("/api/play/forged:token/index.html").status_code == 404


@pytest.mark.django_db
def test_an_h5p_file_opens_in_the_lms_player_page(learner, teacher, module, client):
    made = put_up(teacher, module, file=h5p())
    assert made.status_code == 201, made.content
    package = ContentPackage.objects.get(pk=made.json()["id"])
    launched = launch(learner, package).json()
    assert launched["play_url"].endswith("/") and launched["commit_url"] == "" and launched["cmi"] == {}
    page = client.get(launched["play_url"])
    assert b"/players/h5p/main.bundle.js" in page.content and b"gsa-h5p-frame.js" in page.content
    assert page["Content-Security-Policy"].startswith("sandbox")
    library = client.get(f"{launched['play_url']}H5P.GSATest-1.0/test.js")
    assert library["Content-Type"] == "text/javascript" and library["Access-Control-Allow-Origin"] == "*"


@pytest.mark.django_db
def test_only_the_course_opens_its_packages(package, client_for, make_person, course_admin):
    outsider = make_person("student", "26MRP0099", "Out", "Sider", "student")
    assert launch(client_for(outsider.user), package).status_code == 404
    admin = client_for(course_admin)
    preview = launch(admin, package)
    assert preview.status_code == 200 and preview.json()["attempt"]["is_preview"]


# SCORM commits, completion and coursework


@pytest.mark.django_db
def test_a_scorm_12_commit_completes_the_item_and_counts_in_coursework(
    learner, teacher, package, student, site
):
    package.weight = Decimal(2)
    package.save()
    launched = launch(learner, package).json()
    started = commit(
        learner, launched, {"core": {"lesson_status": "incomplete", "exit": "suspend"}, "suspend_data": "p=3"}
    )
    assert started.json()["result"] is True and started.json()["attempt"]["completion"] == "incomplete"
    resumed = launch(learner, package).json()["cmi"]
    assert resumed["core"]["entry"] == "resume" and resumed["suspend_data"] == "p=3"
    done = commit(
        learner, launched, {"core": {"lesson_status": "passed", "score": {"raw": "80", "min": "", "max": ""}}}
    )
    attempt = done.json()["attempt"]
    assert attempt["completion"] == "completed" and attempt["success"] == "passed"
    assert attempt["score"] == "0.8000" and attempt["score_percent"] == "80.0"
    assert ItemCompletion.objects.get(person=student, item=package.item).how == "package"
    statement = Statement.objects.get(person=student)
    assert (
        statement.verb.endswith("/passed")
        and statement.statement["actor"]["account"]["name"] == student.external_id
    )
    working = coursework_working(site, student)
    row = next(i for i in working["items"] if i["kind"] == "package")
    assert row["state"] == "graded" and row["percent"] == "80.00"
    book = gradebook(site)
    assert book["packages"][0]["id"] == package.id
    assert (
        next(r for r in book["rows"] if r["person_id"] == student.id)["packages"][str(package.id)]["percent"]
        == "80.00"
    )
    assert teacher.get(f"/api/v1/sites/{site.id}/contents/").status_code == 200


@pytest.mark.django_db
def test_scorm_2004_scaled_scores_and_parts(teacher, learner, module, student):
    package = ContentPackage.objects.get(pk=put_up(teacher, module, file=scorm2004()).json()["id"])
    first = launch(learner, package).json()
    assert first["play_url"].endswith("/course/one.html?lesson=1")
    commit(
        learner,
        first,
        {"completion_status": "completed", "success_status": "passed", "score": {"scaled": "0.9"}},
    )
    attempt = PackageAttempt.objects.get(package=package, person=student)
    assert attempt.completion == "incomplete" and attempt.score == Decimal("0.9")  # part two not done yet
    second = launch(learner, package, sco="b").json()
    commit(
        learner, second, {"completion_status": "completed", "score": {"raw": "5", "min": "0", "max": "10"}}
    )
    attempt.refresh_from_db()
    assert attempt.completion == "completed" and attempt.score == Decimal("0.7")
    assert launch(learner, package, sco="nope").status_code == 400


@pytest.mark.django_db
def test_new_attempts_within_the_limit_and_best_score_counts(learner, package, student, site):
    package.max_attempts, package.weight = 2, Decimal(1)
    package.save()
    first = launch(learner, package).json()
    commit(learner, first, {"core": {"lesson_status": "failed", "score": {"raw": "40"}}})
    second = launch(learner, package, new_attempt=True).json()
    assert second["attempt"]["number"] == 2
    commit(learner, second, {"core": {"lesson_status": "completed", "score": {"raw": "30"}}})
    refused = launch(learner, package, new_attempt=True)
    assert refused.status_code == 409 and refused.json()["code"] == "no_attempts_left"
    row = next(i for i in coursework_working(site, student)["items"] if i["kind"] == "package")
    assert row["percent"] == "40.00"


@pytest.mark.django_db
def test_commits_are_the_learners_own_and_well_formed(learner, package, other_student, client_for):
    launched = launch(learner, package).json()
    assert commit(client_for(other_student.user), launched, {"core": {}}).status_code == 404
    bad = learner.post(launched["commit_url"], {"cmi": "x"}, format="json")
    assert bad.status_code == 400 and bad.json()["code"] == "bad_commit"
    huge = commit(learner, launched, {"suspend_data": "x" * 300_000})
    assert huge.json()["code"] == "too_large"


@pytest.mark.django_db
def test_previews_by_teaching_staff_never_count(teacher, learner, package, lecturer):
    preview = launch(teacher, package).json()
    assert preview["attempt"]["is_preview"]
    commit(teacher, preview, {"core": {"lesson_status": "completed"}})
    assert not ItemCompletion.objects.filter(item=package.item).exists()
    assert teacher.get(f"/api/v1/packages/{package.id}/attempts/").json() == []
    launch(learner, package)
    assert len(teacher.get(f"/api/v1/packages/{package.id}/attempts/").json()) == 1
    assert launch(teacher, package, new_attempt=True).json()["attempt"]["number"] == 2


@pytest.mark.django_db
def test_copies_keep_the_package(teacher, package, site, module, lecturer, make_user, client_for):
    duplicate = teacher.post(f"/api/v1/content/{package.item_id}/duplicate/")
    assert duplicate.status_code == 201
    assert ContentPackage.objects.get(item_id=duplicate.json()["id"]).standard == "scorm12"
    from courses.models import CourseSite, Membership

    later = CourseSite.objects.create(code="AGR101-2027", title="Later", term_code="2027", is_published=True)
    Membership.objects.create(site=later, person=lecturer, role="lecturer")
    copied = teacher.post(f"/api/v1/sites/{later.id}/copy-from/", {"source": site.id}, format="json")
    assert copied.status_code == 200, copied.content
    assert ContentPackage.objects.filter(item__module__site=later).count() == 2


# H5P statements and the store (item 6.09)


@pytest.fixture
def h5p_package(teacher, module):
    return ContentPackage.objects.get(pk=put_up(teacher, module, file=h5p(), weight="1").json()["id"])


def statement(launched, **extra):
    return {
        "actor": {"mbox": "mailto:someone@else.example"},
        "verb": {"id": "http://adlnet.gov/expapi/verbs/answered"},
        "object": {"id": launched["activity"], "objectType": "Activity"},
        "context": {"registration": launched["registration"]},
        **extra,
    }


@pytest.mark.django_db
def test_an_h5p_result_completes_the_attempt(learner, h5p_package, student, site):
    launched = launch(learner, h5p_package).json()
    sub = statement(
        launched, object={"id": f"{launched['activity']}?subContentId=1"}, result={"score": {"scaled": 1}}
    )
    posted = learner.post("/api/v1/xapi/statements/", sub, format="json")
    assert posted.status_code == 200 and posted["X-Experience-API-Version"] == "1.0.3"
    assert PackageAttempt.objects.get(person=student).completion == "not_attempted"  # a sub-content only
    whole = statement(
        launched, result={"score": {"raw": 3, "min": 0, "max": 4}, "success": True, "completion": True}
    )
    assert learner.post("/api/v1/xapi/statements/", [whole], format="json").status_code == 200
    attempt = PackageAttempt.objects.get(person=student)
    assert (
        attempt.completion == "completed" and attempt.success == "passed" and attempt.score == Decimal("0.75")
    )
    assert ItemCompletion.objects.filter(person=student, item=h5p_package.item, how="package").exists()
    stored = Statement.objects.filter(person=student).order_by("stored").last().statement
    assert stored["actor"]["account"]["name"] == student.external_id and "mbox" not in json.dumps(
        stored["actor"]
    )
    assert stored["authority"]["account"]["name"] == "lms"
    row = next(i for i in coursework_working(site, student)["items"] if i["kind"] == "package")
    assert row["percent"] == "75.00"


@pytest.mark.django_db
def test_statements_are_refused_outside_the_learners_own_attempt(
    learner, h5p_package, other_student, client_for
):
    launched = launch(learner, h5p_package).json()
    other = client_for(other_student.user)
    assert (
        other.post("/api/v1/xapi/statements/", statement(launched), format="json").json()["code"]
        == "unknown_attempt"
    )
    foreign = statement(launched, object={"id": "https://elsewhere.example/activity"})
    assert (
        learner.post("/api/v1/xapi/statements/", foreign, format="json").json()["code"] == "foreign_activity"
    )
    assert (
        learner.post("/api/v1/xapi/statements/", {"verb": {}}, format="json").json()["code"]
        == "no_registration"
    )
    no_verb = statement(launched, verb={"id": "answered"})
    assert learner.post("/api/v1/xapi/statements/", no_verb, format="json").json()["code"] == "bad_statement"
    assert learner.post("/api/v1/xapi/statements/", [], format="json").status_code == 400
    fixed = statement(launched, id="5b9e4a3c-1111-4222-8333-444455556666")
    assert learner.post("/api/v1/xapi/statements/", fixed, format="json").json() == [fixed["id"]]
    assert learner.post("/api/v1/xapi/statements/", fixed, format="json").status_code == 409
    bad_id = statement(launched, id="not-a-uuid")
    assert learner.post("/api/v1/xapi/statements/", bad_id, format="json").status_code == 400


@pytest.mark.django_db
def test_teaching_staff_read_the_statements_of_their_courses(
    learner, teacher, h5p_package, student, client_for, make_person
):
    launched = launch(learner, h5p_package).json()
    learner.post("/api/v1/xapi/statements/", statement(launched, result={"completion": True}), format="json")
    everything = teacher.get("/api/v1/xapi/statements/").json()
    assert len(everything["statements"]) == 1 and everything["more"] == ""
    by_activity = teacher.get("/api/v1/xapi/statements/", {"activity": activity_iri(h5p_package)}).json()
    assert len(by_activity["statements"]) == 1
    agent = json.dumps({"account": {"name": student.external_id}})
    assert len(teacher.get("/api/v1/xapi/statements/", {"agent": agent}).json()["statements"]) == 1
    assert teacher.get("/api/v1/xapi/statements/", {"agent": "x"}).status_code == 400
    assert teacher.get("/api/v1/xapi/statements/", {"since": "x"}).status_code == 400
    assert teacher.get("/api/v1/xapi/statements/", {"registration": launched["registration"]}).json()[
        "statements"
    ]
    assert (
        teacher.get("/api/v1/xapi/statements/", {"since": "2999-01-01T00:00:00Z"}).json()["statements"] == []
    )
    assert learner.get("/api/v1/xapi/statements/").status_code == 403
    elsewhere = make_person("staff", "E0777", "Other", "Lecturer", "lecturer")
    from courses.models import CourseSite, Membership

    other_site = CourseSite.objects.create(code="X1", title="Other", is_published=True)
    Membership.objects.create(site=other_site, person=elsewhere, role="lecturer")
    assert client_for(elsewhere.user).get("/api/v1/xapi/statements/").json()["statements"] == []
