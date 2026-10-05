"""Checks on every uploaded file, and the names files are stored under.

A file is accepted only when its name and its first bytes agree on one of the kinds a policy allows,
and it is no larger than the policy's limit. The name alone proves nothing: an HTML page renamed
`notes.pdf` is refused. Office files are accepted only without macros.

Stored names are random, so a file name never carries a person's name or details onto the disk; the
name the person chose is kept on the record (ContentItem.original_name, Submission.original_name) and
used for downloads.
"""

import uuid
import zipfile
from dataclasses import dataclass
from pathlib import PurePath

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

HEAD_BYTES = 32
MAX_ZIP_ENTRIES = 2000

# Kind -> the extensions that may carry it.
EXTENSIONS = {
    "pdf": {".pdf"},
    "jpeg": {".jpg", ".jpeg"},
    "png": {".png"},
    "webp": {".webp"},
    "heic": {".heic", ".heif"},
    "docx": {".docx"},
    "xlsx": {".xlsx"},
    "pptx": {".pptx"},
}
HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}
# Office packages by the folder their main part lives in.
OFFICE_FOLDERS = (("word/", "docx"), ("xl/", "xlsx"), ("ppt/", "pptx"))

PAPERS = frozenset({"pdf", "jpeg", "png", "webp", "heic", "docx", "xlsx", "pptx"})
PAPERS_IN_WORDS = "a PDF, a photograph (JPG, PNG, HEIC), or a Word, Excel or PowerPoint file"


@dataclass(frozen=True)
class UploadPolicy:
    kinds: frozenset[str]
    limit_setting: str  # name of the setting holding the size limit in megabytes
    accepts: str  # how the allowed kinds are described to people

    @property
    def limit_mb(self) -> int:
        return int(getattr(settings, self.limit_setting))


# Course material put up by teaching staff: handouts, slides, worksheets and photographs.
CONTENT = UploadPolicy(PAPERS, "UPLOAD_LIMIT_CONTENT_MB", PAPERS_IN_WORDS)
# Work handed in by students: the same kinds, with a smaller limit.
SUBMISSION = UploadPolicy(PAPERS, "UPLOAD_LIMIT_SUBMISSION_MB", PAPERS_IN_WORDS)


def _office_kind(upload) -> str | None:
    """docx, xlsx or pptx when the file is an Office Open XML package without macros; otherwise None."""
    try:
        with zipfile.ZipFile(upload) as package:
            names = package.namelist()
    except (zipfile.BadZipFile, OSError, ValueError):
        return None
    finally:
        upload.seek(0)
    if len(names) > MAX_ZIP_ENTRIES or "[Content_Types].xml" not in names:
        return None
    if any(name.lower().endswith("vbaproject.bin") for name in names):
        return None  # a macro-enabled file renamed to .docx, .xlsx or .pptx
    for folder, kind in OFFICE_FOLDERS:
        if any(name.startswith(folder) for name in names):
            return kind
    return None


def sniff(upload) -> str | None:
    """The kind of file its first bytes show, or None when it is none of the known kinds."""
    upload.seek(0)
    head = upload.read(HEAD_BYTES)
    upload.seek(0)
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[4:8] == b"ftyp" and head[8:12] in HEIF_BRANDS:
        return "heic"
    if head.startswith(b"PK\x03\x04"):
        return _office_kind(upload)
    return None


def validate_upload(upload, policy: UploadPolicy):
    """Raise a ValidationError that says what to send instead, or return the upload unchanged."""
    if upload.size > policy.limit_mb * 1024 * 1024:
        raise serializers.ValidationError(f"The file is larger than {policy.limit_mb} MB.")
    extension = PurePath(upload.name).suffix.lower()
    allowed = {ext for kind in policy.kinds for ext in EXTENSIONS[kind]}
    if extension not in allowed:
        raise serializers.ValidationError(f"Send {policy.accepts}.")
    kind = sniff(upload)
    if kind is None or kind not in policy.kinds or extension not in EXTENSIONS[kind]:
        raise serializers.ValidationError(
            f"The file's contents do not match its name. Save it again as {policy.accepts} and send that."
        )
    return upload


def original_name(upload) -> str:
    """The name the person's file had, without any folder, cut to fit the record."""
    return PurePath(str(upload.name).replace("\\", "/")).name[:255]


def _stored(folder: str, filename: str) -> str:
    extension = PurePath(filename).suffix.lower()[:10]
    now = timezone.now()
    return f"{folder}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{extension}"


def content_name(instance, filename: str) -> str:
    """upload_to for course material: content/<year>/<month>/<random>.<ext>."""
    return _stored("content", filename)


def submission_name(instance, filename: str) -> str:
    """upload_to for students' work: submissions/<year>/<month>/<random>.<ext>."""
    return _stored("submissions", filename)
