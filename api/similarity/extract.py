"""Reading the words of a hand-in (item 3.20): typed text, PDFs, Word and PowerPoint files.

Nothing is fetched and nothing is run. PDFs are read with pypdf; Word and PowerPoint files are zip packages
of XML read with the standard library, and a part that declares a document type or an entity is refused,
so no entity can be expanded. Every read is bounded: pages, parts, bytes and characters. Photographs and
scanned pages carry no text and are noted as not read; there is no OCR.
"""

import io
import re
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree

from django.utils.html import strip_tags

MAX_CHARS = 400_000  # about 70 000 words: far beyond any hand-in
MAX_PART_BYTES = 20 * 1024 * 1024  # the most read from one part of an Office package
MAX_PDF_PAGES = 400
MAX_SLIDES = 400
MAX_PARTS = 2000  # entries in an Office package (core.archives)
MAX_UNPACKED_BYTES = 200 * 1024 * 1024  # the whole package once unpacked, by the sizes it declares

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
SLIDE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
FORBIDDEN = (b"<!DOCTYPE", b"<!ENTITY")


class Unreadable(Exception):
    """The file's words cannot be read safely; the reason is said in words."""


@dataclass
class Extracted:
    text: str = ""
    notes: list[str] = field(default_factory=list)


def _part(package: zipfile.ZipFile, name: str) -> bytes:
    info = package.getinfo(name)
    if info.file_size > MAX_PART_BYTES:
        raise Unreadable("a part of it is too large to read")
    with package.open(info) as handle:
        data = handle.read(MAX_PART_BYTES + 1)
    if len(data) > MAX_PART_BYTES:
        raise Unreadable("a part of it is too large to read")
    upper = data.upper()
    if any(word in upper for word in FORBIDDEN):
        raise Unreadable("it declares a document type or an entity, which is not read")
    return data


def _paragraphs(data: bytes, paragraph: str, run: str) -> list[str]:
    try:
        root = ElementTree.fromstring(data)  # noqa: S314 - _part refused any DOCTYPE or ENTITY first
    except ElementTree.ParseError as error:
        raise Unreadable("its text could not be read") from error
    lines = []
    for block in root.iter(paragraph):
        words = "".join(node.text or "" for node in block.iter(run))
        if words.strip():
            lines.append(words)
    return lines


def _package(content: bytes) -> zipfile.ZipFile:
    """The Office package, once core.archives has checked it: parts, size once unpacked, zip bombs."""
    from core import archives

    try:
        package = archives.open_zip(io.BytesIO(content))
    except archives.ArchiveRefused as refused:
        raise Unreadable("it could not be opened") from refused
    try:
        archives.checked(package, max_entries=MAX_PARTS, max_bytes=MAX_UNPACKED_BYTES)
    except archives.ArchiveRefused as refused:
        package.close()
        raise Unreadable(str(refused).rstrip(".").lower()) from refused
    return package


def docx_text(content: bytes) -> str:
    with _package(content) as package:
        names = set(package.namelist())
        parts = ["word/document.xml"] + sorted(
            n for n in names if re.match(r"^word/(footnotes|endnotes)\.xml$", n)
        )
        lines = []
        for name in parts:
            if name in names:
                lines += _paragraphs(_part(package, name), f"{W_NS}p", f"{W_NS}t")
        return "\n".join(lines)


def pptx_text(content: bytes) -> str:
    with _package(content) as package:
        slides = sorted(
            ((int(m.group(1)), n) for n in package.namelist() if (m := SLIDE.match(n))), key=lambda s: s[0]
        )[:MAX_SLIDES]
        lines = []
        for _, name in slides:
            lines += _paragraphs(_part(package, name), f"{A_NS}p", f"{A_NS}t")
        return "\n".join(lines)


def pdf_text(content: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise Unreadable("it is protected by a password")
        pages, size = [], 0
        for page in reader.pages[:MAX_PDF_PAGES]:
            words = page.extract_text() or ""
            pages.append(words)
            size += len(words)
            if size > MAX_CHARS:
                break
        return "\n".join(pages)
    except (PdfReadError, ValueError, KeyError, TypeError) as error:
        raise Unreadable("it could not be read as a PDF") from error


READERS = {".pdf": pdf_text, ".docx": docx_text, ".pptx": pptx_text}
NOT_READ = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".xlsx"}


def file_text(name: str, content: bytes) -> str:
    """The words of one file, by its kind. Raises Unreadable with the reason."""
    suffix = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    reader = READERS.get(suffix)
    if reader is None:
        if suffix in {".xlsx"}:
            raise Unreadable("spreadsheets are not compared")
        raise Unreadable("photographs and scans carry no text to compare")
    try:
        return reader(content)
    except zipfile.BadZipFile as error:
        raise Unreadable("it could not be opened") from error


def attempt_text(attempt) -> Extracted:
    """Everything a hand-in says: its typed text, then each file's words, in the order handed in."""
    out = Extracted()
    pieces = [strip_tags(attempt.text or "")]
    for stored in attempt.files.all():
        try:
            with stored.file.open("rb") as handle:
                content = handle.read()
            pieces.append(file_text(stored.original_name, content))
        except Unreadable as reason:
            out.notes.append(f"{stored.original_name} was not read: {reason}.")
        except OSError:
            out.notes.append(f"{stored.original_name} was not read: the file could not be opened.")
    out.text = "\n".join(p for p in pieces if p.strip())[:MAX_CHARS]
    return out
