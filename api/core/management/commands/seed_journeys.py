"""Fictional people, accounts and one taught course site for the browser journeys (compose.e2e.yml).

seed_demo needs the HRMS and the SRMS to name the people and the classes. The journeys run the LMS on its
own, so this command creates its own small cast instead: a lecturer and two students with accounts, and one
course site taught with seed_demo's material (content, an announcement, two assignments, a released mark),
plus what the Homes show: work due this week for Kezia and a hand-in waiting to be marked for the lecturer,
and a practical task with its checklist and a competency framework for the practicals journeys.
The accounts share the password in DEMO_USER_PASSWORD. Teaching staff need an authenticator code (ADR 0013),
so the lecturer's authenticator is enrolled from DEMO_TOTP_SECRET, a fictional secret the journeys also hold
to compute the code. The draft privacy notice is published, so the journeys read and acknowledge it as
everyone does at their first sign-in. Never run it on a database that holds real records.
Idempotent: running it again changes nothing.
"""

import os
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from assessments.models import Assignment, Submission
from core.management.commands.seed_demo import Command as SeedDemo
from courses.models import CourseSite, Membership
from iam.models import Role, RoleScope, TotpDevice
from people.models import PersonRef
from practicals.models import (
    CompetencyFramework,
    PerformanceCriterion,
    PracticalCriterion,
    PracticalTask,
    SiteFramework,
)
from practicals.serializers import FrameworkImportSerializer
from privacy.models import PrivacyNotice

SITE = {
    "code": "AGR101-2026-27-S1-MRP",
    "title": "Introduction to Crop Production",
    "term_code": "2026-27-S1",
    "campus_code": "MRP",
    "description": "How crops grow, from seed to harvest.",
}

# A small occupational standard for the practicals journeys (fictional codes, in the Council for TVET's form).
FRAMEWORK = {
    "code": "AGR-CROP-L2",
    "title": "Crop Production Level 2",
    "source": "Council for TVET occupational standard",
    "version": "2024.1",
    "units": [
        {
            "code": "U1",
            "title": "Prepare land for planting",
            "elements": [
                {
                    "code": "E1.1",
                    "title": "Prepare beds",
                    "criteria": [
                        {"code": "PC1.1.1", "text": "Beds are formed to the specified width"},
                        {"code": "PC1.1.2", "text": "Tools are cleaned and stored after use"},
                    ],
                }
            ],
        }
    ],
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
            self._homes(site)
            self._practicals(site)
            PrivacyNotice.objects.filter(published_at__isnull=True).update(published_at=timezone.now())
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
    def _practicals(site: CourseSite) -> None:
        """What the practicals journeys use (items 3.12 to 3.15): a published field task with a
        three-criterion checklist, and a competency framework the site follows, its first performance
        criterion mapped to the critical criterion. The task does not count in coursework (weight 0), so the
        gradebook and Home figures the other journeys check stay as they are, whatever the practicals
        journeys record."""
        framework = CompetencyFramework.objects.filter(
            code=FRAMEWORK["code"], version=FRAMEWORK["version"]
        ).first()
        if framework is None:
            data = FrameworkImportSerializer(data=FRAMEWORK)
            data.is_valid(raise_exception=True)
            framework = data.save()
        SiteFramework.objects.get_or_create(site=site, framework=framework)
        task, created = PracticalTask.objects.get_or_create(
            site=site,
            title="Prepare a vegetable bed",
            defaults={
                "instructions": "Form a raised bed 1.2 m wide on your plot, work the soil to a fine tilth, "
                "then clean and store the tools.",
                "unit_type": "crop_plot",
                "location": "Plot 7",
                "weight": 0,
                "max_attempts": 6,
                "is_published": True,
            },
        )
        if created:
            bed = PracticalCriterion.objects.create(
                task=task, position=1, text="Bed formed to 1.2 m wide", is_critical=True
            )
            bed.performance_criteria.add(
                PerformanceCriterion.objects.get(element__unit__framework=framework, code="PC1.1.1")
            )
            PracticalCriterion.objects.create(
                task=task,
                position=2,
                text="Soil worked to a fine tilth",
                kind="scored",
                max_score=5,
                pass_score=3,
            )
            PracticalCriterion.objects.create(task=task, position=3, text="Tools cleaned and stored")

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
