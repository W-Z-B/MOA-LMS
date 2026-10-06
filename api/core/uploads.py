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

HEAD_BYTES = 64  # enough for a WebM header to name its document type
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
    # Recorded audio, for spoken feedback (item 2.24): phones save M4A (MP4 audio), MP3 or Ogg; browsers
    # recording in the page save WebM or Ogg.
    "m4a": {".m4a", ".mp4"},
    "mp3": {".mp3"},
    "ogg": {".ogg", ".oga", ".opus"},
    "webm": {".webm"},
}
HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}
# MP4 brands that carry audio as phones and browsers save it.
MP4_AUDIO_BRANDS = {b"M4A ", b"M4B ", b"mp41", b"mp42", b"isom", b"iso2", b"iso5", b"dash"}
# Office packages by the folder their main part lives in.
OFFICE_FOLDERS = (("word/", "docx"), ("xl/", "xlsx"), ("ppt/", "pptx"))

PAPERS = frozenset({"pdf", "jpeg", "png", "webp", "heic", "docx", "xlsx", "pptx"})
PAPERS_IN_WORDS = "a PDF, a photograph (JPG, PNG, HEIC), or a Word, Excel or PowerPoint file"
AUDIO = frozenset({"m4a", "mp3", "ogg", "webm"})
# How each kind is named to people, in lists of what an assignment accepts.
KIND_NAMES = {
    "pdf": "PDF",
    "jpeg": "JPG",
    "png": "PNG",
    "webp": "WebP",
    "heic": "HEIC",
    "docx": "Word (.docx)",
    "xlsx": "Excel (.xlsx)",
    "pptx": "PowerPoint (.pptx)",
    "m4a": "M4A audio",
    "mp3": "MP3 audio",
    "ogg": "Ogg audio",
    "webm": "WebM audio",
}


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
# Feedback returned by markers: feedback sheets, marked-up work and recorded audio (item 2.24).
FEEDBACK = UploadPolicy(
    PAPERS | AUDIO,
    "UPLOAD_LIMIT_SUBMISSION_MB",
    f"{PAPERS_IN_WORDS}, or a sound recording (M4A, MP3, Ogg or WebM)",
)


def kinds_in_words(kinds) -> str:
    """'PDF, JPG or Word (.docx)': the kinds named in the order KIND_NAMES lists them."""
    names = [label for kind, label in KIND_NAMES.items() if kind in kinds]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"


def narrowed(policy: UploadPolicy, kinds) -> UploadPolicy:
    """The policy limited to some of its kinds, such as an assignment that takes only PDFs (item 2.22)."""
    chosen = frozenset(kinds or ()) & policy.kinds
    if not chosen or chosen == policy.kinds:
        return policy
    return UploadPolicy(chosen, policy.limit_setting, kinds_in_words(chosen))


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
    if head[4:8] == b"ftyp" and head[8:12] in MP4_AUDIO_BRANDS:
        return "m4a"
    if head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "mp3"  # a tagged file, or one that starts straight at an MPEG audio frame
    if head.startswith(b"OggS"):
        return "ogg"
    if head.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in head:
        return "webm"  # an EBML header naming WebM; other Matroska files are not accepted
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


def feedback_name(instance, filename: str) -> str:
    """upload_to for markers' feedback files and recordings: feedback/<year>/<month>/<random>.<ext>."""
    return _stored("feedback", filename)
