"""What the Common Cartridge and Moodle importers share (item 6.08): reading archives safely, and making the
course's modules, items and questions with a report of what came in and what did not.

Archives are never unpacked onto the disk. A zip (a cartridge, or an older Moodle backup) is checked entry by
entry as packages are (packages.archive.entries: names that stay inside, no links, no zip bombs, size and
count limits). A Moodle backup in its usual form is a gzipped tar file; it is read as a stream, member by
member, refusing links, devices and unsafe names and holding to the same limits. XML is parsed only after
any document type or entity declaration has been refused (quizzes.formats.parse_xml).
"""

import re
import tarfile
import zipfile
from dataclasses import dataclass, field

from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import Max

from audit.services import record, snapshot
from core.uploads import CONTENT, validate_upload
from courses import richtext, storage
from courses.models import ContentItem, Module
from packages import archive
from quizzes.formats import FormatError, parse_xml

MB = 1024 * 1024
MAX_XML_BYTES = 20 * MB
MAX_TAR_MEMBERS = 20_000
IMAGE = re.compile(r"<img[^>]*>", re.IGNORECASE)
TAG = re.compile(r"<[^>]+>")


class ImportRefused(ValueError):
    """The file as a whole cannot be imported; the message says why."""


@dataclass
class Report:
    modules: int = 0
    items: int = 0
    questions: int = 0
    imported: list[dict] = field(default_factory=list)  # {"kind", "title", "module"}
    skipped: list[dict] = field(default_factory=list)  # {"title", "reason"}
    warnings: list[str] = field(default_factory=list)

    def skip(self, title: str, reason: str) -> None:
        self.skipped.append({"title": (title or "(no title)")[:200], "reason": reason})

    def as_dict(self) -> dict:
        return {
            "modules": self.modules,
            "items": self.items,
            "questions": self.questions,
            "imported": self.imported,
            "skipped": self.skipped,
            "warnings": self.warnings,
        }


def xml(data: bytes, what: str):
    """Parse XML from an archive, refusing document types and entities."""
    if len(data) > MAX_XML_BYTES:
        raise ImportRefused(f"{what} is too large to read.")
    try:
        return parse_xml(data.decode("utf-8-sig"))
    except UnicodeDecodeError as error:
        raise ImportRefused(f"{what} is not saved as UTF-8 text.") from error
    except FormatError as error:
        raise ImportRefused(f"{what} cannot be read: {error}") from error


def local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def children(element, name: str):
    return [child for child in element if local(child.tag) == name] if element is not None else []


def child(element, name: str):
    found = children(element, name)
    return found[0] if found else None


def text(element, path: str = "") -> str:
    """The text of the first element down a path of local names ('a/b'), or of the element itself."""
    node = element
    for step in [s for s in path.split("/") if s]:
        node = child(node, step)
        if node is None:
            return ""
    return "".join(node.itertext()).strip() if node is not None else ""


class ZipSource:
    """A checked zip archive, read by entry name."""

    def __init__(self, upload):
        try:
            self.zip = zipfile.ZipFile(upload)
        except (zipfile.BadZipFile, OSError, ValueError) as error:
            raise ImportRefused("The file is not a complete zip file; export it again.") from error
        try:
            self.entries = archive.entries(self.zip)
        except archive.PackageRefused as refused:
            raise ImportRefused(str(refused)) from refused

    def has(self, name: str) -> bool:
        return name in self.entries

    def read(self, name: str) -> bytes:
        try:
            return archive.read(self.zip, self.entries[name])
        except archive.PackageRefused as refused:
            raise ImportRefused(str(refused)) from refused

    def size(self, name: str) -> int:
        return self.entries[name].file_size


def tar_members(upload, wanted=None):
    """Yield (name, bytes) for the regular files of a gzipped tar stream that `wanted(name, size)` accepts.
    Refuses the whole file for an unsafe name, a link or device, or too many or too large members."""
    upload.seek(0)
    total, count = 0, 0
    limit = settings.PACKAGE_MAX_UNPACKED_MB * MB
    try:
        with tarfile.open(fileobj=upload, mode="r|gz") as stream:
            for member in stream:
                count += 1
                if count > MAX_TAR_MEMBERS:
                    raise ImportRefused(f"The backup holds more than {MAX_TAR_MEMBERS} files.")
                name = archive.clean_name(member.name.removeprefix("./"))
                if name is None:
                    raise ImportRefused(
                        f"The backup holds a file with an unsafe name ({member.name[:80]!r})."
                    )
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ImportRefused(
                        f"The backup holds a link or device ({name[:80]}), which is not accepted."
                    )
                total += member.size
                if total > limit:
                    raise ImportRefused(
                        f"The backup unpacks to more than {settings.PACKAGE_MAX_UNPACKED_MB} MB, "
                        "so it was refused."
                    )
                if wanted is not None and not wanted(name, member.size):
                    continue
                handle = stream.extractfile(member)
                data = handle.read(member.size + 1) if handle else b""
                if len(data) != member.size:
                    raise ImportRefused(f"{name[:80]} is damaged in the backup.")
                yield name, data
    except (tarfile.TarError, OSError, EOFError) as error:
        raise ImportRefused("The backup is not a complete .mbz file; make the backup again.") from error


# ---------------------------------------------------------------------------------------------------------
# Making the course's content


class Builder:
    """Adds modules and draft items to a site, each audited, and keeps the report."""

    def __init__(self, site, request, report: Report):
        self.site, self.request, self.report = site, request, report
        self.user = request.user
        self.position = (site.modules.aggregate(last=Max("position"))["last"] or 0) + 1

    def module(self, title: str) -> Module:
        module = Module.objects.create(
            site=self.site,
            title=(title or "Imported")[:160],
            position=self.position,
            created_by=self.user,
            updated_by=self.user,
        )
        self.position += 1
        self.report.modules += 1
        record(self.request, "create", module, after={**snapshot(module), "imported": True})
        return module

    def _item(self, module: Module, kind: str, title: str, **fields) -> ContentItem:
        last = module.items.aggregate(last=Max("position"))["last"] or 0
        fields.setdefault("licence", ContentItem.Licence.UNKNOWN)
        upload = fields.pop("_upload", None)
        item = ContentItem(
            module=module,
            kind=kind,
            title=(title or "Untitled")[:160],
            position=last + 1,
            is_published=False,
            created_by=self.user,
            updated_by=self.user,
            **fields,
        )
        if upload is not None:
            item.file.save(upload.name, upload, save=False)
        item.save()
        self.report.items += 1
        self.report.imported.append({"kind": kind, "title": item.title, "module": module.title})
        record(self.request, "create", item, after={**snapshot(item), "imported": True})
        return item

    def page(self, module: Module, title: str, html: str, **fields) -> ContentItem | None:
        if "@@PLUGINFILE@@" in html or "<img" in html.lower():
            self.report.warnings.append(f"{title}: pictures in the page were not imported; add them again.")
        # Pictures point into the other system's files, which do not come with the page.
        cleaned = richtext.clean(IMAGE.sub("", html))
        if richtext.errors(richtext.check(cleaned)):
            cleaned = richtext.text_to_html(TAG.sub(" ", cleaned))
        return self._item(module, ContentItem.Kind.PAGE, title, body=cleaned, **fields)

    def link(self, module: Module, title: str, url: str, **fields) -> ContentItem | None:
        if not url.lower().startswith(("http://", "https://")):
            self.report.skip(title, "The link is not a web address (http or https).")
            return None
        return self._item(module, ContentItem.Kind.LINK, title, url=url[:200], **fields)

    def file(self, module: Module, title: str, filename: str, data: bytes, **fields) -> ContentItem | None:
        upload = ContentFile(data, name=filename[-120:] or "file")
        try:
            validate_upload(upload, CONTENT)
        except Exception as refused:  # noqa: BLE001 - the upload check's own sentence goes in the report
            detail = getattr(refused, "detail", None)
            reason = str(detail[0] if isinstance(detail, list) and detail else refused)
            self.report.skip(title, f"The file was not imported: {reason}")
            return None
        reason = storage.refusal(self.site, len(data))
        if reason:
            self.report.skip(title, reason)
            return None
        return self._item(
            module,
            ContentItem.Kind.FILE,
            title,
            original_name=filename[-255:],
            file_size=len(data),
            _upload=upload,
            **fields,
        )
