"""Fictional people, accounts and one taught course site for the browser journeys (compose.e2e.yml).

seed_demo needs the HRMS and the SRMS to name the people and the classes. The journeys run the LMS on its
own, so this command creates its own small cast instead: a lecturer and two students with accounts, and one
course site taught with seed_demo's material (content, an announcement, two assignments, a released mark),
plus what the Homes show: work due this week for Kezia and a hand-in waiting to be marked for the lecturer.
The accounts share the password in DEMO_USER_PASSWORD. Teaching staff need an authenticator code (ADR 0013),
so the lecturer's authenticator is enrolled from DEMO_TOTP_SECRET, a fictional secret the journeys also hold
to compute the code. The draft privacy notice is published, so the journeys read and acknowledge it as
everyone does at their first sign-in. Never run it on a database that holds real records.
Idempotent: running it again changes nothing.

For the staff-development and administration journeys it also makes an administrator (with the same
fictional authenticator), two staff-development courses in the catalogue (one open to join, one Marlon has
completed, with its certificate and a fictional check code), and two new students whose accounts are open
but who have not chosen a password yet. Their invitation links, and the certificate's reference and code,
are written as JSON to the file JOURNEY_LINKS_FILE names, where the journeys read them: a link to choose a
password is signed afresh each time and is never printed.
"""

import json
import os
import re
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from assessments.models import Assignment, Submission
from certificates.models import Certificate
from core.management.commands.seed_demo import Command as SeedDemo
from courses.models import Completion, ContentItem, CourseSite, Membership, Module
from iam import accounts
from iam.models import Role, RoleScope, TotpDevice
from people.models import PersonRef
from privacy.models import PrivacyNotice
from staffdev.completion import record_completion
from staffdev.models import CatalogueEntry

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
# The administrator of the console journeys: username, first name, last name.
ADMINISTRATOR = ("ayesha.ramdin", "Ayesha", "Ramdin")
# New students with an account but no password yet: one invitation for each journey project.
INVITED = [("S2026903", "Rohan", "Singh"), ("S2026904", "Priya", "Bhagwandin")]
# Staff-development courses: code, title, how one joins, whether Marlon has completed it.
STAFF_COURSES = [
    ("SD-101", "Safe use of farm machinery", CatalogueEntry.Enrol.OPEN, False),
    ("SD-102", "First aid in the field", CatalogueEntry.Enrol.APPROVAL, True),
]
# Printed on the fictional certificate; the public check accepts it.
CERTIFICATE_CODE = "JRNY-0000-2026"


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
            self._homes(site)
            PrivacyNotice.objects.filter(published_at__isnull=True).update(published_at=timezone.now())
            self._administrator(password, secret)
            certificate = self._staff_development()
            links = self._invitations()
        target = os.environ.get("JOURNEY_LINKS_FILE", "")
        if target:
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(target, "w", encoding="utf-8") as out:
                json.dump({"invitations": links, "certificate": certificate}, out)
        self.stdout.write(
            self.style.SUCCESS(f"Journey data ready: {len(CAST)} accounts in {site.code} ({site.title}).")
        )

    @staticmethod
    def _homes(site: CourseSite) -> None:
        """What the Homes show beyond seed_demo (items 2.07 to 2.09). _teach marks both students' first
        assignment, so Kezia gets a short piece due in three days that nobody has handed in, and Tevin has
        handed in the second assignment, which waits for the lecturer to mark it."""
        now = timezone.now()
        Assignment.objects.get_or_create(
            site=site,
            title="Field notebook check",
            defaults={
                "instructions": "Hand in a photograph of this week's pages of your field notebook.",
                "opens_at": now - timedelta(days=4),
                "due_at": now + timedelta(days=3),
                "max_mark": 10,
                "weight": 1,
                "is_published": True,
            },
        )
        tevin = PersonRef.objects.get(kind=PersonRef.Kind.STUDENT, external_id="S2026902")
        calendar = Assignment.objects.get(site=site, title="Crop calendar for a kitchen garden")
        Submission.objects.get_or_create(
            assignment=calendar,
            student=tevin,
            defaults={"text": "Demonstration submission.", "submitted_at": now - timedelta(days=1)},
        )

    @staticmethod
    def _administrator(password: str, secret: str) -> None:
        username, first, last = ADMINISTRATOR
        user, created = get_user_model().objects.get_or_create(
            username=username,
            defaults={"first_name": first, "last_name": last, "email": f"{username}@gsa.example"},
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
        RoleScope.objects.get_or_create(
            user=user, role=Role.objects.get(code=Role.ADMINISTRATOR), campus_code=""
        )
        TotpDevice.objects.get_or_create(
            user=user, defaults={"secret": secret, "confirmed_at": timezone.now()}
        )

    @staticmethod
    def _staff_development() -> dict:
        """Two courses in the catalogue; Marlon has completed the second, so it has a certificate."""
        marlon = PersonRef.objects.get(kind=PersonRef.Kind.STAFF, external_id="E0901")
        found = None
        for code, title, enrol, completed in STAFF_COURSES:
            site, made = CourseSite.objects.get_or_create(
                code=code,
                defaults={
                    "title": title,
                    "kind": CourseSite.Kind.STAFF_DEVELOPMENT,
                    "source": "local",
                    "is_published": True,
                    "campus_code": "MRP",
                    "description": f"{title}, for every member of staff who works on the farm.",
                },
            )
            if made:
                module = Module.objects.create(site=site, title="What to know")
                ContentItem.objects.create(
                    module=module, title="Before you start", body="<p>Read this first.</p>"
                )
            entry, _ = CatalogueEntry.objects.get_or_create(
                site=site,
                defaults={
                    "summary": f"A short course: {title.lower()}.",
                    "audience": "All farm staff",
                    "length_hours": Decimal("3"),
                    "self_enrol": enrol,
                    "validity_months": 24,
                },
            )
            if completed:
                if not Completion.objects.filter(site=site, person=marlon).exists():
                    record_completion(entry, marlon, how=Completion.How.RECORDED)
                certificate = Certificate.objects.get(site=site, person=marlon)
                if certificate.check_code != CERTIFICATE_CODE:
                    certificate.check_code = CERTIFICATE_CODE
                    certificate.save(update_fields=["check_code"])
                found = {"reference": certificate.reference, "code": CERTIFICATE_CODE}
        return found

    @staticmethod
    def _invitations() -> list[str]:
        """Open the new students' accounts, without a password, and sign an invitation link for each."""
        links = []
        for number, first, last in INVITED:
            person, _ = PersonRef.objects.get_or_create(
                kind=PersonRef.Kind.STUDENT,
                external_id=number,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": f"{number.lower()}@gsa.example",
                    "campus_code": "MRP",
                },
            )
            user = person.user or accounts.open_account(person)
            if not accounts.never_used(user):
                continue  # the journey has chosen a password already: the link would open it again
            if not person.invited_at:
                person.invited_at = timezone.now()
                person.save(update_fields=["invited_at", "updated_at"])
            link = accounts.password_link(user, accounts.invitation_tokens())
            links.append(link[link.index("/#/") :])
        return links

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
