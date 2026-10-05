"""Fictional people, accounts and one taught course site for the browser journeys (compose.e2e.yml).

seed_demo needs the HRMS and the SRMS to name the people and the classes. The journeys run the LMS on its
own, so this command creates its own small cast instead: a lecturer and two students with accounts, and one
course site taught with seed_demo's material (content, an announcement, two assignments, a released mark).
The accounts share the password in DEMO_USER_PASSWORD. Teaching staff need an authenticator code (ADR 0013),
so the lecturer's authenticator is enrolled from DEMO_TOTP_SECRET, a fictional secret the journeys also hold
to compute the code. The draft privacy notice is published, so the journeys read and acknowledge it as
everyone does at their first sign-in. Never run it on a database that holds real records.
Idempotent: running it again changes nothing.
"""

import os
import re

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.management.commands.seed_demo import Command as SeedDemo
from courses.models import CourseSite, Membership
from iam.models import Role, RoleScope, TotpDevice
from people.models import PersonRef
from privacy.models import PrivacyNotice

SITE = {
    "code": "AGR101-2026-27-S1-MRP",
    "title": "Introduction to Crop Production",
    "term_code": "2026-27-S1",
    "campus_code": "MRP",
    "description": "How crops grow, from seed to harvest.",
}

# username, kind, external id, first name, last name, system role, role in the site
CAST = [
    ("marlon.bacchus", PersonRef.Kind.STAFF, "E0901", "Marlon", "Bacchus", Role.LECTURER, "lecturer"),
    ("kezia.persaud", PersonRef.Kind.STUDENT, "S2026901", "Kezia", "Persaud", Role.STUDENT, "student"),
    ("tevin.joseph", PersonRef.Kind.STUDENT, "S2026902", "Tevin", "Joseph", Role.STUDENT, "student"),
]


class Command(BaseCommand):
    help = "Load the fictional cast and course of the browser journeys. Requires --fictional."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fictional",
            action="store_true",
            help="Required: confirms this database is for testing, never for real records",
        )

    def handle(self, *args, **options):
        if not options["fictional"]:
            raise CommandError(
                "This creates invented people with a shared password. "
                "Pass --fictional to confirm the database is for testing only."
            )
        password = os.environ.get("DEMO_USER_PASSWORD", "")
        if len(password) < 12:
            raise CommandError("Set DEMO_USER_PASSWORD (12 characters or more) for the journey accounts.")
        secret = os.environ.get("DEMO_TOTP_SECRET", "")
        if not re.fullmatch(r"[A-Z2-7]{32}", secret):
            raise CommandError("Set DEMO_TOTP_SECRET to 32 base32 characters (A to Z, 2 to 7).")
        call_command("seed", verbosity=0)
        with transaction.atomic():
            site, _ = CourseSite.objects.get_or_create(
                code=SITE["code"],
                defaults={**{k: v for k, v in SITE.items() if k != "code"}, "source": "local"},
            )
            for username, kind, external_id, first, last, role, site_role in CAST:
                person = self._person(username, kind, external_id, first, last, role, password)
                Membership.objects.get_or_create(site=site, person=person, defaults={"role": site_role})
                if site_role == "lecturer":
                    TotpDevice.objects.get_or_create(
                        user=person.user, defaults={"secret": secret, "confirmed_at": timezone.now()}
                    )
            SeedDemo()._teach(site)
            PrivacyNotice.objects.filter(published_at__isnull=True).update(published_at=timezone.now())
        self.stdout.write(
            self.style.SUCCESS(f"Journey data ready: {len(CAST)} accounts in {site.code} ({site.title}).")
        )

    @staticmethod
    def _person(username, kind, external_id, first, last, role, password) -> PersonRef:
        user, created = get_user_model().objects.get_or_create(
            username=username,
            defaults={"first_name": first, "last_name": last, "email": f"{username}@gsa.example"},
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
        RoleScope.objects.get_or_create(user=user, role=Role.objects.get(code=role), campus_code="MRP")
        person, _ = PersonRef.objects.get_or_create(
            kind=kind,
            external_id=external_id,
            defaults={
                "first_name": first,
                "last_name": last,
                "email": user.email,
                "campus_code": "MRP",
                "user": user,
            },
        )
        return person
