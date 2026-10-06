"""Invite everyone not yet invited on a campus or in a term to choose a password (item 1.22)."""

from django.core.management.base import BaseCommand, CommandError

from iam import accounts


class Command(BaseCommand):
    help = "Open accounts for people of a campus or term and email each a link to choose a password."

    def add_arguments(self, parser):
        parser.add_argument("--campus", default="", help="Campus code, such as MRP")
        parser.add_argument("--term", default="", help="Term code, such as 2026-27-S1")
        parser.add_argument("--dry-run", action="store_true", help="Count who would be invited; send nothing")

    def handle(self, *args, **options):
        if not options["campus"] and not options["term"]:
            raise CommandError("Name a campus (--campus), a term (--term), or both.")
        if options["dry_run"]:
            count = accounts.uninvited(campus_code=options["campus"], term_code=options["term"]).count()
            self.stdout.write(f"{count} people would be invited.")
            return
        counts = accounts.invite_all(None, campus_code=options["campus"], term_code=options["term"])
        self.stdout.write(self.style.SUCCESS(f"Invitations: {counts}"))
