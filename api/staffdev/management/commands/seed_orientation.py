"""Make the student orientation course, "Getting started with the GSA LMS" (item 7.16).

Safe to run on any database, including production, and safe to run again: it adds only what is missing and
changes nothing a course administrator has edited. New students are enrolled on it at their first sign-in
while ORIENTATION_AUTO_ENROL is on (the default).
"""

from django.core.management.base import BaseCommand

from staffdev.orientation import ensure_course


class Command(BaseCommand):
    help = "Make the self-paced orientation course for new students and staff, or add what is missing."

    def handle(self, *args, **options):
        made = ensure_course()
        site = made.site
        if made.added:
            self.stdout.write(f"{site.code} {site.title}: added " + "; ".join(made.added) + ".")
        else:
            self.stdout.write(f"{site.code} {site.title} is already complete; nothing changed.")
