"""Seed reference data for the LMS: roles, campuses, the retention schedule and a first draft of the privacy
notice. Sites and people come from the SRMS and HRMS."""

from django.core.management.base import BaseCommand

from iam.models import Role
from integration.models import CampusRef
from privacy import notice_text
from privacy.models import PrivacyNotice
from privacy.retention import seed_rules

CAMPUSES = [("MRP", "Mon Repos Campus", "Region 4"), ("ESQ", "Essequibo Campus", "Region 2")]


class Command(BaseCommand):
    help = "Seed LMS reference data for the Guyana School of Agriculture (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--country", default="GY")

    def handle(self, *args, **options):
        for code, name in Role.CODES:
            Role.objects.update_or_create(code=code, defaults={"name": name})
        for code, name, region in CAMPUSES:
            CampusRef.objects.update_or_create(code=code, defaults={"name": name, "region": region})
        seed_rules()  # periods proposed in docs/privacy/dpia.md, to be confirmed by GSA (item 1.19)
        if not PrivacyNotice.objects.exists():  # a draft for GSA to review and publish (item 1.18)
            PrivacyNotice.objects.create(version=1, title=notice_text.TITLE, body=notice_text.BODY)
        self.stdout.write(
            self.style.SUCCESS("Seed data applied: roles, campuses, retention, privacy notice.")
        )
