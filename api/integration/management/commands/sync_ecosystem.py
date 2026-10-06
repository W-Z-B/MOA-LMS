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
        parser.add_argument("--staff", action="store_true", help="Read the staff directory from the HRMS")
        parser.add_argument(
            "--training-requirements",
            action="store_true",
            help="Read required training from the HRMS (decision D13; scope training:read)",
        )

    def handle(self, *args, **options):
        from integration import hrms, srms

        try:
            if options["staff"]:
                self.stdout.write(f"staff: {hrms.sync_staff(trigger='command')}")
            if options["training_requirements"]:
                result = hrms.sync_training_requirements(trigger="command")
                self.stdout.write(f"training requirements: {result}")
            self.stdout.write(f"sites: {srms.sync_sites(current_only=not options['all_terms'])}")
            if options["push_marks"]:
                sites = CourseSite.objects.filter(source=CourseSite.Source.SRMS)
                if options["site"]:
                    sites = sites.filter(code=options["site"])
                for site in sites:
                    self.stdout.write(f"marks {site.code}: {srms.push_marks(site)}")
            if options["push_training"]:
                self.stdout.write(f"training: {hrms.push_training(trigger='command')}")
        except IntegrationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Ecosystem sync complete."))
