"""Import a folder of existing teaching material into a course site (item 7.14). See courses.importing.

    python manage.py import_folder AGR101-2026-27-S1-MRP /srv/import/AGR101 --dry-run
    python manage.py import_folder AGR101-2026-27-S1-MRP /srv/import/AGR101 --report /srv/import/AGR101.csv

The guide for the people doing it is docs/migration-guide.md.
"""

import csv
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from courses.importing import IMPORTED, REFUSED, SKIPPED, WOULD_IMPORT, import_folder
from courses.models import CourseSite


class Command(BaseCommand):
    help = (
        "Import a folder tree into a course site: one folder per module, every file a draft file item whose "
        "licence is still to be checked. Files that fail the upload checks are refused and reported."
    )

    def add_arguments(self, parser):
        parser.add_argument("site", help="The course site's code, e.g. AGR101-2026-27-S1-MRP")
        parser.add_argument("folder", help="The folder holding one folder per module")
        parser.add_argument(
            "--dry-run", action="store_true", help="Check every file and report; change nothing"
        )
        parser.add_argument("--report", help="Also write the report to this CSV file")

    def handle(self, *args, site, folder, dry_run, report, **options):
        course = CourseSite.objects.filter(code=site).first()
        if course is None:
            raise CommandError(f"There is no course site with the code {site}.")
        root = Path(folder)
        if not root.is_dir():
            raise CommandError(f"{folder} is not a folder.")
        rows = import_folder(course, root, dry_run=dry_run)
        table = [
            ["file", "module", "outcome", "detail"],
            *([r.path, r.module, r.outcome, r.detail] for r in rows),
        ]
        csv.writer(_Lines(self.stdout)).writerows(table)
        if report:
            with open(report, "w", newline="", encoding="utf-8") as out:
                csv.writer(out).writerows(table)
        counts = Counter(row.outcome for row in rows)
        done = WOULD_IMPORT if dry_run else IMPORTED
        summary = (
            f"{course.code}: {counts[done]} {'would be imported' if dry_run else 'imported as drafts'}, "
            f"{counts[REFUSED]} refused, {counts[SKIPPED]} skipped."
        )
        self.stdout.write(summary)
        if counts[REFUSED]:
            self.stderr.write("Refused files are listed above with the reason. Save them again and re-run.")


class _Lines:
    """csv.writer into a management command's stdout, which adds its own line endings."""

    def __init__(self, stdout):
        self.stdout = stdout

    def write(self, text):
        self.stdout.write(text.rstrip("\r\n"))
