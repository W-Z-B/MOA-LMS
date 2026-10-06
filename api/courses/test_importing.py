"""Item 7.14: importing a folder of existing teaching material into a course site."""

import csv
import io
import zipfile
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from audit.models import AuditLog
from courses.importing import GENERAL, plan, tidy
from courses.models import ContentItem, Module

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def docx_with_macros() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("word/document.xml", "<w:document/>")
        package.writestr("word/vbaProject.bin", "macros")
    return buffer.getvalue()


@pytest.fixture
def folder(tmp_path):
    root = tmp_path / "AGR101"
    (root / "01 Week 1").mkdir(parents=True)
    (root / "02 Week_2" / "Lab sheets").mkdir(parents=True)
    (root / "Course outline.pdf").write_bytes(PDF)
    (root / "01 Week 1" / "Seed and germination.pdf").write_bytes(PDF)
    (root / "01 Week 1" / "Germination photo.png").write_bytes(PNG)
    (root / "01 Week 1" / "Thumbs.db").write_bytes(b"cache")
    (root / "02 Week_2" / "Lab sheets" / "Soil test.pdf").write_bytes(PDF)
    (root / "02 Week_2" / "notes.pdf").write_bytes(b"not really a PDF")
    (root / "02 Week_2" / "setup.exe").write_bytes(b"MZ\x90\x00")
    (root / "02 Week_2" / "Marks.docx").write_bytes(docx_with_macros())
    return root


def run(site, folder, *args) -> tuple[str, str]:
    out, err = StringIO(), StringIO()
    call_command("import_folder", site.code, str(folder), *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_names_become_titles_and_folders_become_modules(folder):
    assert tidy("02 Week_2  ") == "02 Week 2" and tidy("") == "Untitled"
    assert [title for title, _ in plan(folder)] == [GENERAL, "01 Week 1", "02 Week 2"]


@pytest.mark.django_db
def test_a_folder_tree_becomes_draft_file_items_whose_licence_is_to_check(site, folder, tmp_path):
    report = tmp_path / "report.csv"
    out, err = run(site, folder, "--report", str(report))
    assert "4 imported as drafts, 3 refused, 1 skipped" in out
    modules = list(Module.objects.filter(site=site).order_by("position"))
    assert [m.title for m in modules] == [GENERAL, "01 Week 1", "02 Week 2"]
    items = ContentItem.objects.filter(module__site=site).order_by("module__position", "position")
    assert [i.title for i in items] == [
        "Course outline",
        "Germination photo",
        "Seed and germination",
        "Lab sheets / Soil test",
    ]
    for item in items:
        assert item.kind == "file" and not item.is_published and item.licence == "unknown"
        assert "Licence not yet known" in item.source and item.file_size > 0 and item.file.name
    assert items[3].original_name == "Soil test.pdf"
    assert "Imported from 02 Week_2/Lab sheets/Soil test.pdf on " in items[3].source
    rows = {row["file"]: row for row in csv.DictReader(report.open(encoding="utf-8"))}
    assert rows["02 Week_2/notes.pdf"]["outcome"] == "refused"
    assert "contents do not match" in rows["02 Week_2/notes.pdf"]["detail"]
    assert "Send a PDF" in rows["02 Week_2/setup.exe"]["detail"]
    assert rows["02 Week_2/Marks.docx"]["outcome"] == "refused"  # a macro-enabled file renamed .docx
    assert rows["01 Week 1/Thumbs.db"]["outcome"] == "skipped"
    assert "Refused files are listed" in err
    assert (
        AuditLog.objects.filter(entity="courses.contentitem", action="create", reason="import_folder").count()
        == 4
    )
    assert AuditLog.objects.filter(entity="courses.module", action="create").count() == 3
    # Students see none of it until the licence is checked and the lecturer publishes it.


@pytest.mark.django_db
def test_running_it_again_skips_what_was_imported(site, folder):
    run(site, folder)
    out, _ = run(site, folder)
    assert "0 imported as drafts, 3 refused, 5 skipped" in out
    assert ContentItem.objects.filter(module__site=site).count() == 4
    assert Module.objects.filter(site=site).count() == 3


@pytest.mark.django_db
def test_a_dry_run_checks_everything_and_changes_nothing(site, folder):
    out, _ = run(site, folder, "--dry-run")
    assert "4 would be imported, 3 refused, 1 skipped" in out
    assert "02 Week_2/notes.pdf,02 Week 2,refused" in out
    assert not Module.objects.filter(site=site).exists()


@pytest.mark.django_db
def test_files_that_do_not_fit_the_storage_allowance_are_refused(site, folder, settings):
    site.storage_allowance_mb = 0
    site.save()
    out, _ = run(site, folder)
    assert "0 imported as drafts, 7 refused" in out and "storage allowance" in out


@pytest.mark.django_db
def test_an_unknown_site_or_folder_is_refused(site, tmp_path):
    with pytest.raises(CommandError, match="no course site"):
        call_command("import_folder", "NOPE", str(tmp_path))
    with pytest.raises(CommandError, match="is not a folder"):
        call_command("import_folder", site.code, str(tmp_path / "missing"))
