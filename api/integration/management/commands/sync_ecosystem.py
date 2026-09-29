"""Synchronise with the sibling systems: sites and class lists from the SRMS, marks and training back."""

from django.core.management.base import BaseCommand, CommandError

from courses.models import CourseSite
from integration.client import IntegrationError


class Command(BaseCommand):
    help = "Pull sites from the SRMS; optionally push coursework marks and staff training completions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all-terms", action="store_true", help="Include offerings outside the current term"
        )
        parser.add_argument("--push-marks", action="store_true", help="Send coursework totals to the SRMS")
        parser.add_argument("--push-training", action="store_true", help="Report completions to the HRMS")
        parser.add_argument("--site", help="Limit --push-marks to one site code")

    def handle(self, *args, **options):
        from integration import hrms, srms

        try:
            self.stdout.write(f"sites: {srms.sync_sites(current_only=not options['all_terms'])}")
            if options["push_marks"]:
                sites = CourseSite.objects.filter(source=CourseSite.Source.SRMS)
                if options["site"]:
                    sites = sites.filter(code=options["site"])
                for site in sites:
                    self.stdout.write(f"marks {site.code}: {srms.push_marks(site)}")
            if options["push_training"]:
                self.stdout.write(f"training: {hrms.push_training()}")
        except IntegrationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Ecosystem sync complete."))
