"""Uploads are judged by their contents and size, and stored under names that say nothing about anyone."""

import io
import re
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import serializers

from core.uploads import (
    CONTENT,
    SUBMISSION,
    content_name,
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
