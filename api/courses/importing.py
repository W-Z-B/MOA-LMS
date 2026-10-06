"""Bringing existing teaching material into a course site (item 7.14).

A lecturer's material usually sits on a shared drive or a memory stick as one folder per week or topic. Put
that folder tree on the server and import it:

- each folder directly inside the one named becomes a module of the site, in name order ("01 Week 1",
  "02 Week 2" ...); files directly inside the named folder go into a module called "General material";
- every file in a module's folder, and in the folders inside it, becomes a file item, titled from its name;
- every file passes the same checks as an upload through the web app (core.uploads.CONTENT: a PDF, a
  photograph, or a Word, Excel or PowerPoint file, within UPLOAD_LIMIT_CONTENT_MB, its contents matching its
  name) and must fit the site's storage allowance. A file that fails is refused and listed with the reason;
  nothing about it is kept;
- whose material each file is cannot be known from a folder, so each item is marked "Not yet known" for its
  licence, with a note to check it, and kept as a draft that students do not see until the lecturer has
  checked it and published it (item 2.19);
- running it again skips files already imported from the same place, so an interrupted import can simply be
  run again. System files (names starting with a dot, Thumbs.db, desktop.ini) are skipped.

Each module and item made is in the audit log. The report lists every file with what happened to it.
"""

from dataclasses import dataclass
from pathlib import Path

from django.core.files import File
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import serializers

from audit.services import record, snapshot
from core.uploads import CONTENT, validate_upload
from courses import storage
from courses.models import ContentItem, CourseSite, Module

GENERAL = "General material"
SYSTEM_FILES = {"thumbs.db", "desktop.ini"}
REASON = "import_folder"

IMPORTED, WOULD_IMPORT, REFUSED, SKIPPED = "imported", "would import", "refused", "skipped"


@dataclass
class Row:
    path: str
    module: str
    outcome: str
    detail: str = ""


def tidy(name: str, limit: int = 160) -> str:
    """A title from a file or folder name: underscores as spaces, no doubled spaces."""
    return " ".join(name.replace("_", " ").split())[:limit] or "Untitled"


def _is_system(path: Path) -> bool:
    return path.name.startswith(".") or path.name.lower() in SYSTEM_FILES


def plan(root: Path) -> list[tuple[str, list[Path]]]:
    """The modules to make, in order, with the files that go in each."""
    general = [p for p in sorted(root.iterdir()) if p.is_file()]
    modules = [(GENERAL, general)] if general else []
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and not _is_system(p)):
        files = sorted(p for p in folder.rglob("*") if p.is_file())
        modules.append((tidy(folder.name), files))
    return modules


def _title(root: Path, path: Path) -> str:
    """The file's name without its extension, after the folders it sits in below the module's own."""
    parts = [*path.relative_to(root).parts[1:-1], path.stem]
    return tidy(" / ".join(parts))


def _refusal(upload: File) -> str | None:
    try:
        validate_upload(upload, CONTENT)
    except serializers.ValidationError as exc:
        return " ".join(str(m) for m in exc.detail)
    return None


def import_folder(site: CourseSite, root: Path, *, dry_run: bool = False) -> list[Row]:
    """Import the folder tree into the site; return one row per file."""
    rows: list[Row] = []
    today = timezone.localdate()
    planned_bytes = 0
    for module_title, files in plan(root):
        module = Module.objects.filter(site=site, title=module_title).first()
        for path in files:
            relative = path.relative_to(root).as_posix()
            if _is_system(path):
                rows.append(Row(relative, module_title, SKIPPED, "A system file, not teaching material."))
                continue
            origin = f"Imported from {relative} on "
            if module is not None and module.items.filter(source__startswith=origin).exists():
                rows.append(Row(relative, module_title, SKIPPED, "Already imported."))
                continue
            with path.open("rb") as handle:
                upload = File(handle, name=path.name)
                reason = _refusal(upload) or storage.refusal(site, upload.size + planned_bytes)
                if reason:
                    rows.append(Row(relative, module_title, REFUSED, reason))
                    continue
                if dry_run:
                    planned_bytes += upload.size
                    rows.append(Row(relative, module_title, WOULD_IMPORT))
                    continue
                with transaction.atomic():
                    if module is None:
                        last = Module.objects.filter(site=site).aggregate(last=Max("position"))["last"] or 0
                        module = Module.objects.create(site=site, title=module_title, position=last + 1)
                        record(None, "create", module, after=snapshot(module), reason=REASON)
                    last = module.items.aggregate(last=Max("position"))["last"] or 0
                    item = ContentItem.objects.create(
                        module=module,
                        kind=ContentItem.Kind.FILE,
                        title=_title(root, path),
                        file=upload,
                        original_name=path.name[:255],
                        file_size=upload.size,
                        position=last + 1,
                        is_published=False,
                        licence=ContentItem.Licence.UNKNOWN,
                        source=f"{origin}{today:%d/%m/%Y}. Licence not yet known: check whose material this "
                        "is before publishing it.",
                    )
                    record(None, "create", item, after=snapshot(item), reason=REASON)
                rows.append(Row(relative, module_title, IMPORTED))
    return rows
