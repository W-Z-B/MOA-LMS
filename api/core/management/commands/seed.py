"""Seed reference data for the LMS: roles and campuses. Sites and people come from the SRMS and HRMS."""

from django.core.management.base import BaseCommand

from iam.models import Role
from integration.models import CampusRef

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
        self.stdout.write(self.style.SUCCESS("Seed data applied: roles, campuses."))
