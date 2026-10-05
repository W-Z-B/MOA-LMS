"""Fictional people, accounts and one taught course site for the browser journeys (compose.e2e.yml).

seed_demo needs the HRMS and the SRMS to name the people and the classes. The journeys run the LMS on its
own, so this command creates its own small cast instead: a lecturer and two students with accounts, and one
course site taught with seed_demo's material (content, an announcement, two assignments, a released mark),
plus what the Homes show: work due this week for Kezia and a hand-in waiting to be marked for the lecturer.
The accounts share the password in DEMO_USER_PASSWORD. Teaching staff need an authenticator code (ADR 0013),
so the lecturer's authenticator is enrolled from DEMO_TOTP_SECRET, a fictional secret the journeys also hold
to compute the code. The draft privacy notice is published, so the journeys read and acknowledge it as
everyone does at their first sign-in. Never run it on a database that holds real records.
A second site, AGR205 Soil Science and Fertility, is for the marking journeys (web/e2e/marking.spec.ts): two
more students, one for the desktop run and one for the phone run, have each handed in a PDF a day late for an
assignment marked with a rubric and a late penalty, and a short test whose marks come from a spreadsheet.
Idempotent: running it again changes nothing.
"""

import hashlib
import os
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from assessments import rules
from assessments.models import Assignment, Submission, SubmissionAttempt, SubmissionFile
from core.management.commands.seed_demo import Command as SeedDemo
from courses.models import CourseSite, Membership
from iam.models import Role, RoleScope, TotpDevice
from people.models import PersonRef
from privacy.models import PrivacyNotice
from rubrics.models import Rubric
from rubrics.services import replace_criteria

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

# The marking journeys' course and its students: the desktop run marks the first, the phone run the second.
MARKING_SITE = {
    "code": "AGR205-2026-27-S1-MRP",
    "title": "Soil Science and Fertility",
    "term_code": "2026-27-S1",
    "campus_code": "MRP",
    "description": "Soils, their testing and how to feed them.",
}
MARKING_CAST = [
    ("ria.ramdial", PersonRef.Kind.STUDENT, "S2026911", "Ria", "Ramdial", Role.STUDENT, "student"),
    ("andre.fung", PersonRef.Kind.STUDENT, "S2026912", "Andre", "Fung", Role.STUDENT, "student"),
]
# A one-page PDF, so the marking screen shows the work beside the mark.
PROFILE_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
)
RUBRIC = [
    (
        "Profile description",
        [(0, "Missing"), (5, "Some horizons described"), (10, "Every horizon described")],
    ),
    ("Interpretation", [(0, "None"), (5, "Some reasoning"), (10, "Clear and supported by the profile")]),
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
            self._marking(password)
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

    def _marking(self, password: str) -> None:
        """The marking journeys' course: a report marked by rubric, handed in a day late (5% a day is taken),
        and a short test for marks from a spreadsheet. Handed in two hours ago, so the lecturer's Home still
        lists AGR101's older hand-in first."""
        site, _ = CourseSite.objects.get_or_create(
            code=MARKING_SITE["code"],
            defaults={**{k: v for k, v in MARKING_SITE.items() if k != "code"}, "source": "local"},
        )
        if not site.is_published:
            site.is_published = True
            site.save(update_fields=["is_published", "updated_at"])
        lecturer = PersonRef.objects.get(kind=PersonRef.Kind.STAFF, external_id="E0901")
        Membership.objects.get_or_create(site=site, person=lecturer, defaults={"role": "lecturer"})
        students = []
        for username, kind, external_id, first, last, role, site_role in MARKING_CAST:
            person = self._person(username, kind, external_id, first, last, role, password)
            Membership.objects.get_or_create(site=site, person=person, defaults={"role": site_role})
            students.append(person)
        rubric = Rubric.objects.filter(site=site, title="Soil profile report rubric").first()
        if rubric is None:
            rubric = Rubric.objects.create(
                site=site, title="Soil profile report rubric", kind=Rubric.Kind.SCORED
            )
            replace_criteria(
                rubric,
                [
                    {"title": title, "levels": [{"points": p, "description": d} for p, d in levels]}
                    for title, levels in RUBRIC
                ],
            )
        now = timezone.now()
        handed_at = now - timedelta(hours=2)
        report, _ = Assignment.objects.get_or_create(
            site=site,
            title="Soil profile report",
            defaults={
                "instructions": "Describe your soil profile, horizon by horizon, and what it means.",
                "opens_at": now - timedelta(days=14),
                "due_at": handed_at - timedelta(days=1),
                "max_mark": 20,
                "weight": 2,
                "is_published": True,
                "accepted_kinds": ["pdf"],
                "max_files": 3,
                "requires_integrity": True,
                "late_penalty": Assignment.LatePenalty.PER_DAY,
                "late_penalty_percent": 5,
                "late_penalty_cap": 20,
                "rubric": rubric,
            },
        )
        test, _ = Assignment.objects.get_or_create(
            site=site,
            title="Soil texture test",
            defaults={
                "instructions": "Feel test of three samples: name each texture.",
                "opens_at": now - timedelta(days=7),
                "due_at": now + timedelta(days=2),
                "max_mark": 10,
                "weight": 1,
                "is_published": True,
            },
        )
        for person in students:
            self._handed_in(report, person, handed_at, is_late=True, pdf=True)
            self._handed_in(test, person, handed_at, is_late=False, pdf=False)

    @staticmethod
    def _handed_in(assignment, person, at, *, is_late: bool, pdf: bool) -> None:
        if Submission.objects.filter(assignment=assignment, student=person).exists():
            return
        text = "" if pdf else "Sandy loam, clay, silt loam."
        name = f"{person.external_id}-profile.pdf"
        files = [(name, hashlib.sha256(PROFILE_PDF).hexdigest())] if pdf else []
        submission = Submission.objects.create(
            assignment=assignment, student=person, text=text, submitted_at=at, is_late=is_late
        )
        attempt = SubmissionAttempt.objects.create(
            submission=submission,
            number=1,
            submitted_by=person,
            submitted_at=at,
            text=text,
            is_late=is_late,
            receipt=rules.new_receipt(),
            content_hash=rules.content_hash(text, files),
            integrity_statement=rules.INTEGRITY_STATEMENT if assignment.requires_integrity else "",
        )
        if pdf:
            stored = SubmissionFile(
                attempt=attempt, original_name=name, size=len(PROFILE_PDF), sha256=files[0][1]
            )
            stored.file.save(name, ContentFile(PROFILE_PDF), save=True)
            submission.file, submission.original_name = stored.file.name, name
            submission.save(update_fields=["file", "original_name"])

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
