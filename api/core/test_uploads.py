"""Uploads are judged by their contents and size, and stored under names that say nothing about anyone."""

import io
import re
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import serializers

from core.uploads import (
    CONTENT,
    FEEDBACK,
    SUBMISSION,
    content_name,
    feedback_name,
    narrowed,
    original_name,
    sniff,
    submission_name,
    validate_upload,
)

PDF = b"%PDF-1.7\n%demo"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 "
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"


def office(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        for name in ("[Content_Types].xml", *names):
            package.writestr(name, "<x/>")
    return buffer.getvalue()


def upload(name: str, content: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content)


@pytest.mark.parametrize(
    ("name", "content", "kind"),
    [
        ("scan.pdf", PDF, "pdf"),
        ("photo.jpg", JPEG, "jpeg"),
        ("photo.JPEG", JPEG, "jpeg"),
        ("photo.png", PNG, "png"),
        ("photo.webp", WEBP, "webp"),
        ("photo.heic", HEIC, "heic"),
        ("report.docx", office("word/document.xml"), "docx"),
        ("results.xlsx", office("xl/workbook.xml"), "xlsx"),
        ("lecture.pptx", office("ppt/presentation.xml"), "pptx"),
    ],
)
@pytest.mark.parametrize("policy", [CONTENT, SUBMISSION])
def test_accepted_kinds(name, content, kind, policy):
    file = upload(name, content)
    assert sniff(file) == kind
    assert validate_upload(file, policy) is file
    assert file.read(4) == content[:4]  # the checks leave the file ready to be stored from the start


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("notes.pdf", b"<html><script>alert(1)</script></html>", "do not match its name"),
        ("notes.jpg", PDF, "do not match its name"),
        ("slides.pptx", office("word/document.xml"), "do not match its name"),
        ("notes.svg", b"<svg onload='alert(1)'/>", "Send a PDF"),
        ("setup.exe", b"MZ\x90\x00", "Send a PDF"),
        ("page.html", b"<html></html>", "Send a PDF"),
        ("macro.docx", office("word/document.xml", "word/vbaProject.bin"), "do not match its name"),
        ("macro.pptx", office("ppt/presentation.xml", "ppt/vbaProject.bin"), "do not match its name"),
        ("macro.pptm", office("ppt/presentation.xml", "ppt/vbaProject.bin"), "Send a PDF"),
        ("broken.docx", b"PK\x03\x04 not really a zip", "do not match its name"),
        ("noext", PDF, "Send a PDF"),
    ],
)
def test_refused_files_say_what_to_send(name, content, message):
    with pytest.raises(serializers.ValidationError) as refused:
        validate_upload(upload(name, content), SUBMISSION)
    assert message in str(refused.value.detail[0])


def test_size_limits_come_from_settings(settings):
    settings.UPLOAD_LIMIT_SUBMISSION_MB = 1
    big = upload("essay.pdf", PDF + b"0" * (1024 * 1024))
    with pytest.raises(serializers.ValidationError) as refused:
        validate_upload(big, SUBMISSION)
    assert str(refused.value.detail[0]) == "The file is larger than 1 MB."
    settings.UPLOAD_LIMIT_CONTENT_MB = 2
    assert validate_upload(big, CONTENT) is big


def test_the_default_limits():
    assert (CONTENT.limit_mb, SUBMISSION.limit_mb) == (50, 20)


def test_stored_names_are_random_and_keep_only_the_extension():
    first = submission_name(None, "Ravi Singh soil report.PDF")
    second = submission_name(None, "Ravi Singh soil report.PDF")
    assert first != second
    assert re.fullmatch(r"submissions/\d{4}/\d{2}/[0-9a-f]{32}\.pdf", first)
    assert "Ravi" not in first
    assert re.fullmatch(r"content/\d{4}/\d{2}/[0-9a-f]{32}\.pptx", content_name(None, "Week 1.pptx"))


def test_the_original_name_never_carries_a_folder():
    assert original_name(upload("C:\\Users\\ravi\\report.docx", b"")) == "report.docx"
    assert original_name(upload("week 1/notes.pdf", b"")) == "notes.pdf"


MP3_TAGGED = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 20
MP3_FRAME = b"\xff\xfb\x90\x64" + b"\x00" * 20
M4A = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00M4A mp42isom"
MP4_AUDIO = b"\x00\x00\x00\x20ftypmp42\x00\x00\x00\x00mp42isom"
OGG = b"OggS\x00\x02" + b"\x00" * 20
WEBM = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01\x42\xf2\x81\x04\x42\xf3\x81\x08\x42\x82\x84webm"
MATROSKA = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\x82\x88matroska"


@pytest.mark.parametrize(
    ("name", "content", "kind"),
    [
        ("feedback.mp3", MP3_TAGGED, "mp3"),
        ("feedback.mp3", MP3_FRAME, "mp3"),
        ("Voice memo.m4a", M4A, "m4a"),
        ("recording.mp4", MP4_AUDIO, "m4a"),
        ("note.ogg", OGG, "ogg"),
        ("note.opus", OGG, "ogg"),
        ("recorded in the page.webm", WEBM, "webm"),
        ("marked.pdf", PDF, "pdf"),
    ],
)
def test_feedback_takes_recordings_judged_by_their_contents(name, content, kind):
    """Item 2.24: spoken feedback recorded on a phone or in the browser."""
    file = upload(name, content)
    assert sniff(file) == kind
    assert validate_upload(file, FEEDBACK) is file


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("feedback.mp3", b"<html></html>", "do not match its name"),
        ("video.webm", MATROSKA, "do not match its name"),
        ("note.ogg", MP3_TAGGED, "do not match its name"),
        ("feedback.wav", b"RIFF\x00\x00\x00\x00WAVE", "sound recording"),
    ],
)
def test_feedback_refuses_what_is_not_a_recording(name, content, message):
    with pytest.raises(serializers.ValidationError) as refused:
        validate_upload(upload(name, content), FEEDBACK)
    assert message in str(refused.value.detail[0])


def test_students_cannot_hand_in_recordings_and_an_assignment_can_narrow_the_kinds():
    with pytest.raises(serializers.ValidationError):
        validate_upload(upload("feedback.mp3", MP3_TAGGED), SUBMISSION)
    only_pdf = narrowed(SUBMISSION, ["pdf"])
    assert only_pdf.accepts == "PDF" and only_pdf.limit_mb == SUBMISSION.limit_mb
    assert narrowed(SUBMISSION, ["pdf", "docx", "jpeg"]).accepts == "PDF, JPG or Word (.docx)"
    assert narrowed(SUBMISSION, []) is SUBMISSION and narrowed(SUBMISSION, ["mp3"]) is SUBMISSION
    with pytest.raises(serializers.ValidationError) as refused:
        validate_upload(upload("photo.jpg", JPEG), only_pdf)
    assert "Send PDF." in str(refused.value.detail[0])
    assert re.fullmatch(r"feedback/\d{4}/\d{2}/[0-9a-f]{32}\.m4a", feedback_name(None, "Voice memo.M4A"))
