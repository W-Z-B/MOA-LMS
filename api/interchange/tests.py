# ruff: noqa: E501 - Moodle and cartridge fixtures are kept as the XML they stand for
"""Course interchange (item 6.08): Common Cartridge export and import, and Moodle backups for content only,
with the defences against zip bombs, path traversal, links and XML entities."""

import io
import tarfile
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from audit.models import AuditLog
from courses.models import ContentItem, CourseSite, Membership, Module
from packages.tests import scorm12
from quizzes.models import Question, QuestionBank, QuestionVersion, Quiz, QuizSlot


@pytest.fixture
def teacher(lecturer, client_for):
    return client_for(lecturer.user)


@pytest.fixture
def other_site(lecturer):
    site = CourseSite.objects.create(
        code="AGR102-2027", title="Soils II", term_code="2027", is_published=True
    )
    Membership.objects.create(site=site, person=lecturer, role="lecturer")
    return site


@pytest.fixture
def full_site(site, teacher, assignment):
    module = Module.objects.create(site=site, title="Week 1: Soils", position=1)
    ContentItem.objects.create(
        module=module,
        kind="page",
        title="Soil types",
        body="<p>Loam and <strong>clay</strong></p>",
        licence="gsa_own",
    )
    ContentItem.objects.create(
        module=module, kind="link", title="FAO soils portal", url="https://www.fao.org/soils-portal/",
        licence="open_licence", open_licence="cc_by", source="FAO",
    )  # fmt: skip
    handout = ContentItem(
        module=module, kind="file", title="Handout", licence="gsa_own", original_name="handout sheet.pdf"
    )
    handout.file.save("handout.pdf", SimpleUploadedFile("handout.pdf", b"%PDF-1.7 handout"))
    handout.file_size = handout.file.size
    handout.save()
    assert (
        teacher.post(
            "/api/v1/packages/",
            {"module": module.id, "file": scorm12(), "licence": "gsa_own"},
            format="multipart",
        ).status_code
        == 201
    )
    bank = QuestionBank.objects.create(site=site, name="Bank")
    quiz = Quiz.objects.create(site=site, title="Soils quiz")
    shapes = [
        ("multichoice", {"single": True, "shuffle": True, "choices": [
            {"id": "a", "text": "Loam", "fraction": 1, "feedback": ""},
            {"id": "b", "text": "Rock", "fraction": 0, "feedback": ""}]}),
        ("truefalse", {"correct": False, "feedback_true": "", "feedback_false": ""}),
        ("shortanswer", {"answers": [{"text": "humus", "fraction": 1, "feedback": ""}], "case_sensitive": False}),
        ("essay", {"min_words": None, "max_words": None, "response_template": "", "grader_info": ""}),
        ("matching", {"pairs": [], "extra_answers": [], "shuffle": True}),
    ]  # fmt: skip
    for position, (qtype, data) in enumerate(shapes, 1):
        question = Question.objects.create(bank=bank, qtype=qtype, name=f"{qtype} question")
        QuestionVersion.objects.create(question=question, text=f"<p>About {qtype}</p>", data=data)
        QuizSlot.objects.create(quiz=quiz, question=question, position=position)
    return site


def export(client, site) -> zipfile.ZipFile:
    response = client.get(f"/api/v1/sites/{site.id}/export-cartridge/")
    assert response.status_code == 200, response.content
    assert response["Content-Disposition"].endswith('.imscc"')
    return zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content)))


def as_upload(data: bytes, name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, data)


def import_file(client, site, data: bytes, name="course.imscc"):
    return client.post(
        f"/api/v1/sites/{site.id}/import-content/", {"file": as_upload(data, name)}, format="multipart"
    )


@pytest.mark.django_db
def test_a_course_is_exported_as_a_common_cartridge(teacher, full_site):
    cartridge = export(teacher, full_site)
    names = cartridge.namelist()
    assert "imsmanifest.xml" in names and "README.txt" in names
    manifest = cartridge.read("imsmanifest.xml").decode()
    assert "<schemaversion>1.3.0</schemaversion>" in manifest
    assert 'type="imswl_xmlv1p3"' in manifest and 'type="imsqti_xmlv1p2/imscc_xmlv1p3/assessment"' in manifest
    assert "Under an open licence: CC BY. Source: FAO" in manifest
    assert any(n.endswith("handout-sheet.pdf") for n in names)
    qti = next(cartridge.read(n).decode() for n in names if n.endswith("assessment.xml"))
    assert "cc.multiple_choice.v0p1" in qti and "cc.true_false.v0p1" in qti and "cc.fib.v0p1" in qti
    assert "cc.essay.v0p1" in qti and "matching question" not in qti
    assert "matching question" in cartridge.read("README.txt").decode()
    assert AuditLog.objects.filter(action="export", entity="courses.coursesite").exists()


@pytest.mark.django_db
def test_an_exported_cartridge_comes_back_in_as_drafts(teacher, full_site, other_site):
    data = io.BytesIO()
    for chunk in teacher.get(f"/api/v1/sites/{full_site.id}/export-cartridge/").streaming_content:
        data.write(chunk)
    imported = import_file(teacher, other_site, data.getvalue())
    assert imported.status_code == 200, imported.content
    report = imported.json()
    assert report["format"] == "common_cartridge" and report["modules"] == 3
    assert report["questions"] == 4  # the matching question was never exported
    items = {i.title: i for i in ContentItem.objects.filter(module__site=other_site)}
    assert not any(i.is_published for i in items.values())
    assert items["Soil types"].body == "<p>Loam and <strong>clay</strong></p>"
    assert (
        items["FAO soils portal"].licence == "open_licence"
        and items["FAO soils portal"].open_licence == "cc_by"
    )
    assert items["Handout"].kind == "file" and items["Handout"].licence == "gsa_own"
    assert "Soil testing" in [s["title"] for s in report["skipped"]]  # a package is not a kind of course file
    assert "Soil sampling report" in items  # the assignment, as a page
    assert QuestionBank.objects.get(site=other_site).questions.count() == 4
    assert AuditLog.objects.filter(action="import").exists()


def cartridge_with(manifest: str, files: dict | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as made:
        made.writestr("imsmanifest.xml", manifest)
        for name, data in (files or {}).items():
            made.writestr(name, data)
    return buffer.getvalue()


MANIFEST = """<manifest identifier="x" xmlns="http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1">
<organizations><organization identifier="o"><item identifier="root">
  <item identifier="m1"><title>Topic</title>
    <item identifier="i1" identifierref="r1"><title>Discuss</title></item>
    <item identifier="i2" identifierref="r2"><title>Tool</title></item>
    <item identifier="i3" identifierref="r3"><title>Script</title></item>
    <item identifier="i4" identifierref="missing"><title>Ghost</title></item>
    <item identifier="i5"><title>Empty heading</title></item>
  </item></item></organization></organizations>
<resources>
  <resource identifier="r1" type="imsdt_xmlv1p1"><file href="d.xml"/></resource>
  <resource identifier="r2" type="imsbasiclti_xmlv1p0"><file href="t.xml"/></resource>
  <resource identifier="r3" type="webcontent" href="evil.html.js"><file href="evil.html.js"/></resource>
</resources></manifest>"""


@pytest.mark.django_db
def test_what_a_cartridge_holds_that_the_lms_does_not_take_is_reported(teacher, other_site):
    report = import_file(teacher, other_site, cartridge_with(MANIFEST, {"evil.html.js": "alert(1)"})).json()
    reasons = {s["title"]: s["reason"] for s in report["skipped"]}
    assert "Discussion topics" in reasons["Discuss"] and "LTI" in reasons["Tool"]
    assert "not imported" in reasons["Script"] and "does not hold" in reasons["Ghost"]
    assert "nothing under it" in reasons["Empty heading"]
    assert report["modules"] == 1 and report["items"] == 0


@pytest.mark.django_db
def test_unsafe_cartridges_are_refused_and_change_nothing(teacher, other_site, student, client_for):
    bomb = '<?xml version="1.0"?><!DOCTYPE m [<!ENTITY a "a">]><manifest>&a;</manifest>'
    refused = import_file(teacher, other_site, cartridge_with(bomb))
    assert refused.status_code == 400 and "document type or entities" in refused.json()["detail"]
    escape = import_file(teacher, other_site, cartridge_with(MANIFEST, {"../../etc/x.html": "x"}))
    assert "unsafe name" in escape.json()["detail"]
    assert (
        "not a Common Cartridge"
        in import_file(
            teacher, other_site, cartridge_with(MANIFEST).replace(b"imsmanifest", b"imsmanifesx")
        ).json()["detail"]
    )
    assert (
        "Send a Common Cartridge" in import_file(teacher, other_site, b"%PDF-1.7", "x.pdf").json()["detail"]
    )
    zeros = io.BytesIO()
    with zipfile.ZipFile(zeros, "w", zipfile.ZIP_DEFLATED) as made:
        made.writestr("imsmanifest.xml", MANIFEST)
        made.writestr("big.bin", b"\0" * (5 * 1024 * 1024))
    assert "far more than its size" in import_file(teacher, other_site, zeros.getvalue()).json()["detail"]
    assert not other_site.modules.exists()
    learner = client_for(student.user)
    assert learner.get(f"/api/v1/sites/{other_site.id}/export-cartridge/").status_code == 404
    assert import_file(learner, other_site, cartridge_with(MANIFEST)).status_code == 404


# Moodle backups

BACKUP = """<?xml version="1.0" encoding="UTF-8"?>
<moodle_backup><information><name>backup.mbz</name><contents>
  <activities>
    <activity><moduleid>11</moduleid><sectionid>1</sectionid><modulename>page</modulename><title>Welcome</title><directory>activities/page_11</directory></activity>
    <activity><moduleid>12</moduleid><sectionid>1</sectionid><modulename>url</modulename><title>FAO</title><directory>activities/url_12</directory></activity>
    <activity><moduleid>13</moduleid><sectionid>2</sectionid><modulename>resource</modulename><title>Notes</title><directory>activities/resource_13</directory></activity>
    <activity><moduleid>14</moduleid><sectionid>2</sectionid><modulename>label</modulename><title>Read first</title><directory>activities/label_14</directory></activity>
    <activity><moduleid>15</moduleid><sectionid>2</sectionid><modulename>forum</modulename><title>Chat</title><directory>activities/forum_15</directory></activity>
  </activities>
  <sections>
    <section><sectionid>1</sectionid><title>1</title><directory>sections/section_1</directory></section>
    <section><sectionid>2</sectionid><title>2</title><directory>sections/section_2</directory></section>
    <section><sectionid>3</sectionid><title>3</title><directory>sections/section_3</directory></section>
  </sections>
</contents></information></moodle_backup>"""

QUESTIONS = """<?xml version="1.0" encoding="UTF-8"?>
<question_categories><question_category id="1"><name>Soils</name><question_bank_entries>
 <question_bank_entry id="1"><question_version><question_versions id="1"><questions>
  <question id="100"><parent>0</parent><name>Old wording</name><questiontext>Old</questiontext><qtype>truefalse</qtype>
   <plugin_qtype_truefalse_question><answers>
    <answer id="1"><answertext>True</answertext><fraction>1.0000000</fraction><feedback></feedback></answer>
    <answer id="2"><answertext>False</answertext><fraction>0.0000000</fraction><feedback></feedback></answer>
   </answers></plugin_qtype_truefalse_question></question>
  <question id="101"><parent>0</parent><name>Loam holds water</name><questiontext>&lt;p&gt;Loam holds water.&lt;/p&gt;</questiontext><qtype>truefalse</qtype><defaultmark>2.0000000</defaultmark>
   <plugin_qtype_truefalse_question><answers>
    <answer id="3"><answertext>True</answertext><fraction>1.0000000</fraction><feedback>Yes</feedback></answer>
    <answer id="4"><answertext>False</answertext><fraction>0.0000000</fraction><feedback></feedback></answer>
   </answers></plugin_qtype_truefalse_question></question>
 </questions></question_versions></question_version></question_bank_entry>
 <question_bank_entry id="2"><question_version><question_versions id="2"><questions>
  <question id="102"><parent>0</parent><name>Best soil</name><questiontext>Which?</questiontext><qtype>multichoice</qtype>
   <plugin_qtype_multichoice_question><answers>
    <answer id="5"><answertext>Loam</answertext><fraction>1.0000000</fraction><feedback></feedback></answer>
    <answer id="6"><answertext>Sand</answertext><fraction>0.0000000</fraction><feedback></feedback></answer>
   </answers><multichoice id="1"><single>1</single><shuffleanswers>1</shuffleanswers></multichoice></plugin_qtype_multichoice_question></question>
 </questions></question_versions></question_version></question_bank_entry>
 <question_bank_entry id="3"><question_version><question_versions id="3"><questions>
  <question id="103"><parent>0</parent><name>Drag it</name><questiontext>x</questiontext><qtype>ddwtos</qtype></question>
 </questions></question_versions></question_version></question_bank_entry>
</question_bank_entries></question_category></question_categories>"""

HASH = "ab" + "c" * 38


def backup_files() -> dict[str, bytes]:
    return {
        "moodle_backup.xml": BACKUP.encode(),
        "sections/section_1/section.xml": b"<section><number>1</number><name>Week 1</name><summary>&lt;p&gt;Start here&lt;/p&gt;</summary><sequence>12,11</sequence></section>",
        "sections/section_2/section.xml": b"<section><number>2</number><name></name><summary></summary><sequence>13,14,15</sequence></section>",
        "sections/section_3/section.xml": b"<section><number>3</number><name>Empty</name><summary></summary><sequence></sequence></section>",
        "activities/page_11/page.xml": b'<activity><page><name>Welcome</name><content>&lt;p&gt;Hello &lt;img src="@@PLUGINFILE@@/a.png"&gt;&lt;/p&gt;</content></page></activity>',
        "activities/url_12/url.xml": b"<activity><url><name>FAO</name><externalurl>https://www.fao.org/</externalurl></url></activity>",
        "activities/resource_13/resource.xml": b"<activity><resource><name>Notes</name></resource></activity>",
        "activities/resource_13/inforef.xml": b"<inforef><fileref><file><id>7</id></file></fileref></inforef>",
        "activities/label_14/label.xml": b"<activity><label><name>Read first</name><intro>&lt;p&gt;Read this&lt;/p&gt;</intro></label></activity>",
        "files.xml": f'<files><file id="7"><contenthash>{HASH}</contenthash><component>mod_resource</component><filearea>content</filearea><filename>notes.pdf</filename></file></files>'.encode(),
        f"files/ab/{HASH}": b"%PDF-1.7 notes",
        "questions.xml": QUESTIONS.encode(),
    }


def tgz(files: dict[str, bytes], extra=None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as made:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            made.addfile(info, io.BytesIO(data))
        if extra:
            made.addfile(extra)
    return buffer.getvalue()


@pytest.mark.django_db
def test_a_moodle_backup_brings_its_content_and_questions(teacher, other_site):
    imported = import_file(teacher, other_site, tgz(backup_files()), "course.mbz")
    assert imported.status_code == 200, imported.content
    report = imported.json()
    assert report["format"] == "moodle_backup" and report["modules"] == 2
    modules = list(other_site.modules.order_by("position"))
    assert [m.title for m in modules] == ["Week 1", "Section 2"]
    assert [i.title for i in modules[0].items.order_by("position")] == [
        "About this section",
        "FAO",
        "Welcome",
    ]
    assert [i.kind for i in modules[1].items.order_by("position")] == ["file", "page"]
    assert modules[1].items.get(kind="file").original_name == "notes.pdf"
    assert "<img" not in modules[0].items.get(title="Welcome").body
    assert any("pictures" in w for w in report["warnings"])
    reasons = {s["title"]: s["reason"] for s in report["skipped"]}
    assert "Forums" in reasons["Chat"] and "ddwtos" in reasons["Drag it"]
    assert report["questions"] == 2
    bank = QuestionBank.objects.get(site=other_site)
    names = sorted(bank.questions.values_list("name", flat=True))
    assert names == ["Best soil", "Loam holds water"]  # the older version is not imported
    assert bank.questions.get(name="Loam holds water").latest.data["correct"] is True


@pytest.mark.django_db
def test_a_zipped_moodle_backup_is_read_too(teacher, other_site):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as made:
        for name, data in backup_files().items():
            made.writestr(name, data)
    report = import_file(teacher, other_site, buffer.getvalue(), "course.mbz").json()
    assert report["items"] == 5


@pytest.mark.django_db
def test_unsafe_moodle_backups_are_refused(teacher, other_site):
    link = tarfile.TarInfo("files/ab/link")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    assert (
        "link or device"
        in import_file(teacher, other_site, tgz(backup_files(), link), "c.mbz").json()["detail"]
    )
    escape = {**backup_files(), "../../outside.xml": b"<x/>"}
    assert "unsafe name" in import_file(teacher, other_site, tgz(escape), "c.mbz").json()["detail"]
    entities = {**backup_files(), "moodle_backup.xml": b'<!DOCTYPE x [<!ENTITY a "a">]><moodle_backup/>'}
    assert "entities" in import_file(teacher, other_site, tgz(entities), "c.mbz").json()["detail"]
    nothing = {"other.xml": b"<x/>"}
    assert "no moodle_backup.xml" in import_file(teacher, other_site, tgz(nothing), "c.mbz").json()["detail"]
    truncated = tgz(backup_files())[:200]
    assert "not a complete .mbz" in import_file(teacher, other_site, truncated, "c.mbz").json()["detail"]
    assert not other_site.modules.exists()
