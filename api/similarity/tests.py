"""The similarity check (item 3.20; decision D4): reading, comparing, the report and who may see what."""

import io
import zipfile
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from assessments.models import Assignment, Submission, SubmissionAttempt
from audit.models import AuditLog
from courses.models import CourseSite, Membership, SiteGroup
from similarity import engine, extract, services, tasks
from similarity.models import Fingerprint, SimilarityDocument, SimilarityMatch

ESSAY = (
    "Soil sampling begins with a plan of the field drawn to scale. Walk the field in a zigzag pattern and "
    "take cores from fifteen to twenty places at the same depth, avoiding gateways, manure heaps and the "
    "edges of drains. Mix the cores in a clean plastic bucket, take out about half a kilogram and label the "
    "bag with the field name and the date before sending it to the laboratory at Mon Repos."
)
OWN = (
    "Cassava grows well on light sandy loam with good drainage. Farmers in Region Two plant stem cuttings at "
    "the start of the rainy season and weed twice in the first three months, which keeps yields steady."
)


def _docx(paragraphs: list[str], extra: bytes = b"") -> bytes:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = extra + f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'.encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("word/document.xml", xml)
    return buffer.getvalue()


def _pptx(slides: list[str]) -> bytes:
    ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        for number, words in enumerate(slides, start=1):
            package.writestr(
                f"ppt/slides/slide{number}.xml",
                f'<p:sld xmlns:p="x" xmlns:a="{ns}"><a:p><a:r><a:t>{words}</a:t></a:r></a:p></p:sld>',
            )
    return buffer.getvalue()


def _pdf(words: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=f"<p>{words}</p>").write_pdf()


def _submit(client, assignment, **data):
    response = client.post(f"/api/v1/assignments/{assignment.id}/submit/", data, format="multipart")
    assert response.status_code == 201, response.json()
    return Submission.objects.get(pk=response.json()["id"])


def _check(submission) -> SimilarityDocument:
    return services.check(submission.attempts.order_by("number").last())


@pytest.fixture
def second_site(make_person, student):
    """Another course, taught by another lecturer, which the first student also takes."""
    other_lecturer = make_person("staff", "E0002", "Kamla", "Ramdass", "lecturer")
    site = CourseSite.objects.create(code="AGR201-2025-26-S1-MRP", title="AGR201 Soils", is_published=True)
    Membership.objects.create(site=site, person=other_lecturer, role="lecturer")
    Membership.objects.create(site=site, person=student, role="student")
    assignment = Assignment.objects.create(
        site=site, title="Field sampling", due_at=timezone.now() + timedelta(days=3), is_published=True
    )
    return site, assignment, other_lecturer


# ---------------------------------------------------------------------------------------------------------
# Comparing


def test_winnowing_keeps_a_fingerprint_of_every_long_enough_shared_passage():
    words = engine.words_of(ESSAY)
    hashes = engine.shingles(words)
    kept = engine.winnow(hashes)
    assert 0 < len(kept) < len(hashes)
    # Any W consecutive shingles hold at least one kept fingerprint: W + K - 1 shared words are always found.
    positions = {p for _, p in kept}
    for start in range(len(hashes) - engine.W + 1):
        assert positions & set(range(start, start + engine.W))
    assert engine.winnow([]) == [] and engine.winnow([5, 3]) == [(3, 1)]


def test_compare_finds_the_passage_and_leaves_out_quotations_and_instructions():
    copied = "My introduction is my own. " + ESSAY[:220] + " And my own conclusion follows here."
    found = engine.compare(engine.words_of(copied), engine.words_of(ESSAY))
    assert found.passages and found.shared_a >= 30
    assert "zigzag pattern" in engine.passage_text(engine.words_of(copied), found.passages[0]["a"])
    # The same words inside quotation marks are the student saying they are someone else's.
    quoted = f'As the handbook says, "{ESSAY[:220]}" and I agree.'
    assert engine.compare(engine.words_of(quoted), engine.words_of(ESSAY)).passages == []
    # Words of the assignment's instructions are never counted, however many students repeat them.
    question = "Describe how soil sampling begins with a plan of the field drawn to scale."
    excluded = engine.instruction_hashes(question)
    a, b = engine.words_of(question + " " + OWN), engine.words_of(question + " Something else entirely.")
    assert engine.compare(a, b, excluded).passages == []
    assert engine.compare(a, b).passages  # without the exclusion they would match
    assert engine.covered([[0, 5], [3, 9], [20, 22]]) == 11


def test_word_and_powerpoint_files_are_read_and_entities_refused():
    assert "zigzag" in extract.file_text("report.docx", _docx(["Field plan", ESSAY]))
    assert extract.file_text("talk.pptx", _pptx(["Soil sampling", "Cores at one depth"])).splitlines() == [
        "Soil sampling",
        "Cores at one depth",
    ]
    bomb = _docx(["x"], extra=b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa">]>')
    with pytest.raises(extract.Unreadable, match="entity"):
        extract.file_text("bomb.docx", bomb)
    with pytest.raises(extract.Unreadable, match="photographs"):
        extract.file_text("photo.jpg", b"\xff\xd8\xff")
    with pytest.raises(extract.Unreadable, match="spreadsheets"):
        extract.file_text("marks.xlsx", b"PK")
    with pytest.raises(extract.Unreadable, match="opened"):
        extract.file_text("broken.docx", b"not a zip")
    with pytest.raises(extract.Unreadable, match="PDF"):
        extract.file_text("broken.pdf", b"%PDF-1.7 nothing more")


def test_a_pdf_is_read():
    assert "zigzag" in extract.file_text("report.pdf", _pdf(ESSAY))


# ---------------------------------------------------------------------------------------------------------
# The check and the report


@pytest.mark.django_db
def test_copied_work_is_found_across_courses_and_named_only_to_staff_of_both(
    site, assignment, student, other_student, lecturer, second_site, client_for, make_person
):
    other_site, other_assignment, other_lecturer = second_site
    # Last year, on another course, the first student handed in the original, as a Word file.
    original = _submit(
        client_for(student.user),
        other_assignment,
        text="",
        files=[SimpleUploadedFile("sampling.docx", _docx(["Field sampling report", ESSAY]))],
    )
    Submission.objects.filter(pk=original.pk).update(submitted_at=timezone.now() - timedelta(days=400))
    first = _check(original)
    assert first.status == "done" and first.overall_percent == 0 and first.fingerprints.exists()

    copy = _submit(client_for(other_student.user), assignment, text=OWN + ' "A quoted line here." ' + ESSAY)
    document = _check(copy)
    assert document.status == "done" and document.word_count > 60
    assert 50 < document.overall_percent < 100

    # The lecturer of this course does not teach the other: the other work is not named.
    teacher = client_for(lecturer.user)
    report = teacher.get(f"/api/v1/submissions/{copy.id}/similarity/").json()
    assert report["overall_percent"] == str(document.overall_percent)
    assert "evidence for a person to judge, not a verdict" in report["statement"]
    match = report["matches"][0]
    year = (timezone.now() - timedelta(days=400)).year
    assert match["other"]["known"] is False and match["other"]["student"] is None
    assert match["other"]["label"] == f"Another GSA submission, {year}"
    assert (
        "zigzag pattern" in match["passages"][0]["mine"]
        and "zigzag pattern" in match["passages"][0]["theirs"]
    )
    assert AuditLog.objects.filter(action="similarity_viewed", entity_id=copy.id).exists()

    # Someone who teaches both courses sees who and where.
    Membership.objects.create(site=other_site, person=lecturer, role="assistant")
    teacher = client_for(lecturer.user)  # a change of roles signs the person out
    named = teacher.get(f"/api/v1/submissions/{copy.id}/similarity/").json()["matches"][0]["other"]
    assert named["known"] is True and named["site"] == other_site.code and "Ravi Singh" in named["student"]

    # The earlier work's report shows the later copy too, from its own side.
    earlier = client_for(other_lecturer.user).get(f"/api/v1/submissions/{original.id}/similarity/").json()
    assert earlier["matches"][0]["other"]["known"] is False and float(earlier["overall_percent"]) > 80

    # The assignment's list for the lecturer, highest first.
    rows = teacher.get(f"/api/v1/assignments/{assignment.id}/similarity/").json()
    assert rows[0]["submission"] == copy.id and rows[0]["matches"] == 1


@pytest.mark.django_db
def test_students_never_see_a_report_and_strangers_find_nothing(
    site, assignment, student, lecturer, client_for, make_person
):
    submission = _submit(client_for(student.user), assignment, text=ESSAY)
    _check(submission)
    learner = client_for(student.user)
    assert learner.get(f"/api/v1/submissions/{submission.id}/similarity/").status_code == 403
    assert learner.post(f"/api/v1/submissions/{submission.id}/similarity/").status_code == 403
    assert learner.get(f"/api/v1/assignments/{assignment.id}/similarity/").status_code == 403
    stranger = make_person("staff", "E0009", "Neil", "Outsider", "lecturer")
    other = client_for(stranger.user)
    assert other.get(f"/api/v1/submissions/{submission.id}/similarity/").status_code == 404
    assert other.get(f"/api/v1/assignments/{assignment.id}/similarity/").status_code == 404


@pytest.mark.django_db
def test_checking_again_unreadable_files_and_deletion_with_the_submission(
    site, assignment, student, other_student, lecturer, client_for, settings
):
    teacher = client_for(lecturer.user)
    photo = SimpleUploadedFile("page.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00")
    scanned = _submit(client_for(student.user), assignment, text="", files=[photo])
    # Not checked yet: the report says so.
    assert teacher.get(f"/api/v1/submissions/{scanned.id}/similarity/").json()["status"] == "not_checked"
    report = teacher.post(f"/api/v1/submissions/{scanned.id}/similarity/").json()
    assert report["status"] == "no_text" and "page.jpg was not read" in report["notes"][0]
    assert AuditLog.objects.filter(action="similarity_checked", entity_id=scanned.id).exists()

    pdf_work = _submit(
        client_for(other_student.user),
        assignment,
        text="",
        files=[SimpleUploadedFile("work.pdf", _pdf(ESSAY))],
    )
    _check(pdf_work)
    typed = _submit(client_for(student.user), assignment, text=ESSAY)  # a second hand-in replaces the first
    document = _check(typed)
    assert document.attempt_number == 2 and document.matches.count() == 1
    assert SimilarityDocument.objects.get(submission=pdf_work).overall_percent > 90

    # Retention: the fingerprints and matches go with the submission.
    assert Fingerprint.objects.filter(document__submission=typed).exists()
    typed.delete()
    assert not Fingerprint.objects.filter(document__submission_id=typed.id).exists()
    assert not SimilarityMatch.objects.filter(other__submission_id=typed.id).exists()

    settings.SIMILARITY_CHECKS = False
    refused = teacher.post(f"/api/v1/submissions/{pdf_work.id}/similarity/")
    assert refused.status_code == 409 and refused.json()["code"] == "checks_off"
    assert services.check(pdf_work.attempts.last()) is None


@pytest.mark.django_db
def test_nothing_handed_in_and_a_failed_check(site, assignment, student, lecturer, client_for, monkeypatch):
    submission = Submission.objects.create(
        assignment=assignment, student=student, submitted_at=timezone.now()
    )
    teacher = client_for(lecturer.user)
    refused = teacher.post(f"/api/v1/submissions/{submission.id}/similarity/")
    assert refused.status_code == 409 and refused.json()["code"] == "nothing_handed_in"
    handed = _submit(client_for(student.user), assignment, text=ESSAY)

    def broken(attempt):
        raise RuntimeError("disk")

    monkeypatch.setattr(services, "check", broken)
    assert services.check_safely(handed.attempts.last()) is None
    assert SimilarityDocument.objects.get(submission=handed).status == "failed"


@pytest.mark.django_db
def test_group_members_work_is_not_compared_with_itself(site, assignment, student, other_student, client_for):
    group = SiteGroup.objects.create(site=site, name="Team A")
    group.members.set(Membership.objects.filter(site=site, role="student"))
    assignment.is_group = True
    assignment.save()
    first = _submit(client_for(student.user), assignment, text=ESSAY)
    _check(first)
    second = _submit(client_for(other_student.user), assignment, text=ESSAY + " With a last line.")
    document = _check(second)
    assert document.matches.count() == 0 and document.overall_percent == 0


@pytest.mark.django_db
def test_each_hand_in_queues_one_background_check(
    site, assignment, student, client_for, monkeypatch, django_capture_on_commit_callbacks
):
    queued = []
    monkeypatch.setattr(tasks.check_attempt, "defer", lambda **kw: queued.append(kw))
    with django_capture_on_commit_callbacks(execute=True):
        submission = _submit(client_for(student.user), assignment, text=ESSAY)
    attempt = SubmissionAttempt.objects.get(submission=submission)
    assert queued == [{"attempt_id": attempt.id}]
    # The job checks the latest hand-in, skips one that was replaced, and survives a deleted one.
    assert tasks.check_attempt(attempt.id) == "done"
    with django_capture_on_commit_callbacks(execute=True):
        _submit(client_for(student.user), assignment, text=OWN)
    assert tasks.check_attempt(attempt.id) == "superseded"
    assert tasks.check_attempt(999999) == "gone"
