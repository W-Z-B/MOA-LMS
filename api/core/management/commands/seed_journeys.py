"""Fictional people, accounts and one taught course site for the browser journeys (compose.e2e.yml).

seed_demo needs the HRMS and the SRMS to name the people and the classes. The journeys run the LMS on its
own, so this command creates its own small cast instead: a lecturer and two students with accounts, and one
course site taught with seed_demo's material (content, an announcement, two assignments, a released mark),
plus what the Homes show: work due this week for Kezia and a hand-in waiting to be marked for the lecturer.
For copying a course (item 2.18) the lecturer also teaches last year's offering of a second course, with dated
content and an assignment, and this year's offering of it, empty and unpublished.

For the forums, messages, classes and calendar journeys (items 4.08 to 4.15) it adds two forums, three
classes (two running now) and two lab groups.

For the practicals journeys (items 3.12 to 3.15) it adds a practical task with its checklist and a competency
framework the course follows.

For the quiz journeys (feature 10) it adds the course's question bank with one category, where the
journeys write their questions.
The accounts share the password in DEMO_USER_PASSWORD. Teaching staff need an authenticator code (ADR 0013),
so the lecturer's authenticator is enrolled from DEMO_TOTP_SECRET, a fictional secret the journeys also hold
to compute the code. The draft privacy notice is published, so the journeys read and acknowledge it as
everyone does at their first sign-in. Never run it on a database that holds real records.
A second site, AGR205 Soil Science and Fertility, is for the marking journeys (web/e2e/marking.spec.ts): two
more students, one for the desktop run and one for the phone run, have each handed in a PDF a day late for an
assignment marked with a rubric and a late penalty, and a short test whose marks come from a spreadsheet.
Idempotent: running it again changes nothing.

For the staff-development and administration journeys it also makes an administrator (with the same
fictional authenticator), two staff-development courses in the catalogue (one open to join, one Marlon has
completed, with its certificate and a fictional check code), and two new students whose accounts are open
but who have not chosen a password yet. Their invitation links, and the certificate's reference and code,
are written as JSON to the file JOURNEY_LINKS_FILE names, where the journeys read them: a link to choose a
password is signed afresh each time and is never printed.

For the similarity, peer review and paper quiz journeys (items 3.20, 3.24, 4.13) it adds AGR210 Pasture and
Forage: three students' essays, one copying a passage of another, each checked, and given out for peer review;
and a quiz to print. For the open short course journeys (item 5.07) it adds an open course and two
registrations waiting for their links, which go in JOURNEY_LINKS_FILE too (open_courses).
"""

import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from assessments import rules
from assessments.models import Assignment, Submission, SubmissionAttempt, SubmissionFile
from certificates.models import Certificate
from core.management.commands.seed_demo import Command as SeedDemo
from courses.models import Completion, ContentItem, CourseSite, Membership, Module
from iam import accounts
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
from quizzes.models import QuestionBank, QuestionCategory
from rubrics.models import Rubric
from rubrics.services import replace_criteria
from staffdev.completion import record_completion
from staffdev.models import CatalogueEntry

SITE = {
    "code": "AGR101-2026-27-S1-MRP",
    "title": "Introduction to Crop Production",
    "term_code": "2026-27-S1",
    "campus_code": "MRP",
    "description": "How crops grow, from seed to harvest.",
}

# Last year's offering of a second course and this year's, for copying a course with its dates moved.
EARLIER = {
    "code": "AGR102-2025-26-S1-MRP",
    "title": "Soils and Plant Nutrition (2025-26)",
    "term_code": "2025-26-S1",
    "campus_code": "MRP",
    "description": "Last year's offering, to copy from.",
}
NEXT = {
    "code": "AGR102-2026-27-S1-MRP",
    "title": "Soils and Plant Nutrition",
    "term_code": "2026-27-S1",
    "campus_code": "MRP",
    "description": "This year's offering, empty until it is copied.",
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

# --- assessment extras (items 3.20, 3.24, 4.13, 5.07): the similarity, peer review and paper quiz journeys'
# course, and an open short course. The desktop run reviews as Lisa, the phone run as Omar.
FORAGE_SITE = {
    "code": "AGR210-2026-27-S1-MRP",
    "title": "Pasture and Forage",
    "term_code": "2026-27-S1",
    "campus_code": "MRP",
    "description": "Grasses, legumes and grazing for cattle, sheep and goats.",
}
FORAGE_CAST = [
    ("lisa.thomas", PersonRef.Kind.STUDENT, "S2026921", "Lisa", "Thomas", Role.STUDENT, "student"),
    ("omar.khan", PersonRef.Kind.STUDENT, "S2026922", "Omar", "Khan", Role.STUDENT, "student"),
    ("nadia.ali", PersonRef.Kind.STUDENT, "S2026923", "Nadia", "Ali", Role.STUDENT, "student"),
]
_GRAZING = (
    "The pasture is divided into six paddocks with electric fencing, and the herd moves to a fresh paddock "
    "every four days so that each paddock rests for at least twenty days before it is grazed again. "
    "During the dry season the stocking rate falls to one animal for each hectare and a half, and the "
    "animals get cut grass and molasses blocks in the afternoon when the pasture is short."
)
FORAGE_ESSAYS = [
    "My grazing plan for the school farm. " + _GRAZING + " Water troughs are cleaned every week.",
    "This plan rests on Brachiaria and a legume such as Leucaena planted along the drains, cut and carried "
    "to the pen twice a day in the dry months, with the herd kept off the wettest ground near the trench.",
    "A dry season plan. " + _GRAZING + " I would also plant Leucaena near the pens for extra protein.",
]
FORAGE_RUBRIC = [
    ("Knowledge of pasture", [(0, "Missing"), (5, "Some knowledge shown"), (10, "Thorough and accurate")]),
    ("Use of the farm's records", [(0, "None"), (5, "Some use"), (10, "Plan built on the records")]),
]
FORAGE_QUESTIONS = [
    (
        "multichoice",
        "Which is a legume grown for forage?",
        {
            "single": True,
            "choices": [
                {"id": "a", "text": "Leucaena", "fraction": 1},
                {"id": "b", "text": "Brachiaria", "fraction": 0},
                {"id": "c", "text": "Sugar cane", "fraction": 0},
            ],
        },
    ),
    ("truefalse", "A rested paddock grows back faster than one grazed every day.", {"correct": True}),
    (
        "multichoice",
        "How long should a paddock rest in the dry season, at least?",
        {
            "single": True,
            "choices": [
                {"id": "a", "text": "Two days", "fraction": 0},
                {"id": "b", "text": "Twenty days", "fraction": 1},
            ],
        },
    ),
]
OPEN_COURSE = {
    "code": "OPEN-POULTRY-2026",
    "title": "Backyard poultry keeping",
    "description": "A short course for farmers and extension officers.",
}
# Fictional people registering for the open course: one for each journey project.
OPEN_LEARNERS = [
    ("farmer.desktop@example.org", "Sita", "Persaud"),
    ("farmer.phone@example.org", "Dev", "Ramsaran"),
]
# --- end assessment extras ---


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
            self._to_copy(Membership.objects.get(site=site, role="lecturer").person)
            self._talk(site)
            self._practicals(site)
            self._question_bank(site)
            PrivacyNotice.objects.filter(published_at__isnull=True).update(published_at=timezone.now())
            self._administrator(password, secret)
            certificate = self._staff_development()
            links = self._invitations()
            open_links = self._assessment_extras(password)
        target = os.environ.get("JOURNEY_LINKS_FILE", "")
        if target:
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(target, "w", encoding="utf-8") as out:
                json.dump({"invitations": links, "certificate": certificate, "open_courses": open_links}, out)
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
    def _to_copy(lecturer: PersonRef) -> None:
        """Last year's offering of AGR102, with a module shown from a date, a page and an assignment, and this
        year's, empty: the lecturer copies one into the other with every date moved (item 2.18)."""
        local = timezone.get_current_timezone()
        earlier, _ = CourseSite.objects.get_or_create(
            code=EARLIER["code"],
            defaults={
                **{k: v for k, v in EARLIER.items() if k != "code"},
                "source": "local",
                "is_published": True,
            },
        )
        later, _ = CourseSite.objects.get_or_create(
            code=NEXT["code"], defaults={**{k: v for k, v in NEXT.items() if k != "code"}, "source": "local"}
        )
        for site in (earlier, later):
            Membership.objects.get_or_create(site=site, person=lecturer, defaults={"role": "lecturer"})
        module, _ = Module.objects.get_or_create(
            site=earlier,
            title="Week 1: Soil texture",
            defaults={"position": 1, "available_from": datetime(2025, 10, 6, 8, 0, tzinfo=local)},
        )
        ContentItem.objects.get_or_create(
            module=module,
            title="Sand, silt and clay",
            defaults={"body": "<p>Feel the soil between your fingers: sand is gritty, silt smooth.</p>"},
        )
        Assignment.objects.get_or_create(
            site=earlier,
            title="Soil texture report",
            defaults={
                "instructions": "Describe the texture of three soils from the farm.",
                "opens_at": datetime(2025, 10, 1, 13, 0, tzinfo=local),
                "due_at": datetime(2025, 10, 15, 13, 0, tzinfo=local),
                "max_mark": 20,
                "weight": 1,
                "is_published": True,
            },
        )

    @staticmethod
    def _talk(site: CourseSite) -> None:
        """Forums, classes and groups for the journeys of items 4.08 to 4.15. A question-and-answer forum
        where Tevin has answered already (Kezia sees his answer once she posts hers), a class discussion
        for the moderation journey, two classes running now (one for the register, one for check-in, so
        neither journey changes the other's) and one tomorrow, and a lab group with self-sign-up."""
        from attendance.models import ClassSession
        from courses.groups import GroupSignUp
        from courses.models import SiteGroup
        from forums.models import Forum, Post, Thread

        now = timezone.now()
        users = {p.user.username: p.user for p in PersonRef.objects.filter(memberships__site=site)}
        lecturer, kezia, tevin = users["marlon.bacchus"], users["kezia.persaud"], users["tevin.joseph"]
        question, _ = Forum.objects.get_or_create(
            site=site,
            title="Questions on germination",
            defaults={
                "forum_type": Forum.Type.QUESTION,
                "description": "<p>Answer each question in your own words.</p>",
            },
        )
        talk, _ = Forum.objects.get_or_create(
            site=site, title="Class discussion", defaults={"description": "<p>Anything about the course.</p>"}
        )
        for forum, title, opening, replies in (
            (
                question,
                "Why did some seeds not germinate?",
                "<p>In the trial, a third of the bean seeds did not come up. Give one reason.</p>",
                [(tevin, "<p>The tray was watered too often, so the seeds rotted.</p>")],
            ),
            (talk, "Where do you buy your seed?", "<p>Tell the class where you buy seed, and why.</p>", []),
        ):
            thread, made = Thread.objects.get_or_create(
                forum=forum, title=title, defaults={"author": lecturer, "last_post_at": now}
            )
            if made:
                first = Post.objects.create(thread=thread, author=lecturer, body=opening)
                for author, body in replies:
                    Post.objects.create(thread=thread, parent=first, author=author, body=body)
        for title, starts, hours, place in (
            ("Soil science lecture", now - timedelta(minutes=30), 5, "Room 4"),
            ("Field practical: seed sowing", now - timedelta(minutes=45), 5, "Plot 2"),
            ("Irrigation (online)", now + timedelta(days=1), 1, ""),
        ):
            ClassSession.objects.get_or_create(
                site=site,
                title=title,
                defaults={
                    "starts_at": starts,
                    "ends_at": starts + timedelta(hours=hours),
                    "location": place,
                    "meeting_url": "" if place else "https://meet.example.org/agr101",
                },
            )
        lab_a, made = SiteGroup.objects.get_or_create(site=site, name="Lab group A")
        if made:
            lab_a.members.add(*site.memberships.filter(person__user=kezia))
        lab_b, _ = SiteGroup.objects.get_or_create(site=site, name="Lab group B")
        GroupSignUp.objects.get_or_create(group=lab_b, defaults={"max_size": 3})

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
    def _question_bank(site: CourseSite) -> None:
        """An empty bank for the course, with one category: the quiz journeys (feature 10) write a question
        in it, build a quiz and publish it. No quiz is seeded, so nothing new is due on the Homes."""
        bank, _ = QuestionBank.objects.get_or_create(site=site, name="Crop production questions")
        QuestionCategory.objects.get_or_create(bank=bank, name="Week 1: What a crop needs")

    # --- assessment extras: similarity, peer review, paper quizzes, open courses (3.20, 3.24, 4.13, 5.07) ---
    def _assessment_extras(self, password: str) -> list[str]:
        """AGR210 Pasture and Forage, for the similarity, peer review and paper quiz journeys: three students
        have handed in an essay marked by rubric, an hour ago, after its due date passed; Nadia's copies a
        long passage of Lisa's, and every hand-in has been checked. The work is given out for peer review
        (two pieces each, due in five days), and the course has a published quiz to print. Also a published
        open short course, and two registrations waiting for their emailed link, one for each journey project:
        the links are returned for JOURNEY_LINKS_FILE."""
        from opencourses.models import OpenRegistration
        from peerreview.models import PeerReviewSetup
        from peerreview.services import allocate
        from quizzes import schemas
        from quizzes.models import Question, QuestionVersion, Quiz, QuizSlot
        from similarity.models import SimilarityDocument
        from similarity.services import check

        site, _ = CourseSite.objects.get_or_create(
            code=FORAGE_SITE["code"],
            defaults={
                **{k: v for k, v in FORAGE_SITE.items() if k != "code"},
                "source": "local",
                "is_published": True,
            },
        )
        lecturer = PersonRef.objects.get(kind=PersonRef.Kind.STAFF, external_id="E0901")
        Membership.objects.get_or_create(site=site, person=lecturer, defaults={"role": "lecturer"})
        students = []
        for username, kind, external_id, first, last, role, site_role in FORAGE_CAST:
            person = self._person(username, kind, external_id, first, last, role, password)
            Membership.objects.get_or_create(site=site, person=person, defaults={"role": site_role})
            students.append(person)
        rubric = Rubric.objects.filter(site=site, title="Grazing plan rubric").first()
        if rubric is None:
            rubric = Rubric.objects.create(site=site, title="Grazing plan rubric", kind=Rubric.Kind.SCORED)
            replace_criteria(
                rubric,
                [
                    {"title": title, "levels": [{"points": p, "description": d} for p, d in levels]}
                    for title, levels in FORAGE_RUBRIC
                ],
            )
        now = timezone.now()
        essay, made = Assignment.objects.get_or_create(
            site=site,
            title="Grazing plan essay",
            defaults={
                "instructions": "Write a grazing plan for the school's pasture for the dry season.",
                "opens_at": now - timedelta(days=10),
                "due_at": now - timedelta(minutes=90),
                "max_mark": 20,
                "weight": 1,
                "is_published": True,
                "requires_integrity": True,
                "rubric": rubric,
            },
        )
        for person, text in zip(students, FORAGE_ESSAYS, strict=True):
            if Submission.objects.filter(assignment=essay, student=person).exists():
                continue
            at = now - timedelta(hours=1)
            submission = Submission.objects.create(
                assignment=essay, student=person, text=text, submitted_at=at, is_late=True
            )
            SubmissionAttempt.objects.create(
                submission=submission,
                number=1,
                submitted_by=person,
                submitted_at=at,
                text=text,
                is_late=True,
                receipt=rules.new_receipt(),
                content_hash=rules.content_hash(text, []),
                integrity_statement=rules.INTEGRITY_STATEMENT,
            )
        for submission in essay.submissions.order_by("student__external_id"):
            if not SimilarityDocument.objects.filter(submission=submission).exists():
                check(submission.attempts.get())
        setup, _ = PeerReviewSetup.objects.get_or_create(
            assignment=essay,
            defaults={
                "reviews_each": 2,
                "reviews_due_at": now + timedelta(days=5),
                "peer_weight": Decimal(20),
            },
        )
        if setup.allocated_at is None:
            allocate(setup)
        bank, _ = QuestionBank.objects.get_or_create(site=site, name="Pasture questions")
        category, _ = QuestionCategory.objects.get_or_create(bank=bank, name="Forage")
        quiz, made = Quiz.objects.get_or_create(
            site=site, title="Forage quiz", defaults={"is_published": True, "weight": 0}
        )
        if made:
            for position, (qtype, text, data) in enumerate(FORAGE_QUESTIONS, start=1):
                question = Question.objects.create(bank=bank, category=category, qtype=qtype, name=text[:60])
                QuestionVersion.objects.create(
                    question=question, text=text, data=schemas.validate_question(qtype, text, data)
                )
                QuizSlot.objects.create(quiz=quiz, position=position, question=question)
        # The open short course and its waiting registrations (item 5.07; on in the journey stack only).
        course, made = CourseSite.objects.get_or_create(
            code=OPEN_COURSE["code"],
            defaults={
                **{k: v for k, v in OPEN_COURSE.items() if k != "code"},
                "kind": CourseSite.Kind.OPEN,
                "source": "local",
                "is_published": True,
            },
        )
        if made:
            module = Module.objects.create(site=course, title="Week 1: Housing")
            ContentItem.objects.create(
                module=module, title="A dry, airy house", body="<p>Keep the litter dry.</p>"
            )
        CatalogueEntry.objects.get_or_create(
            site=course,
            defaults={
                "summary": "Housing, feeding and keeping a small flock healthy.",
                "audience": "Farmers and extension officers",
                "length_hours": Decimal("6"),
                "self_enrol": CatalogueEntry.Enrol.OPEN,
            },
        )
        links = []
        for email, first, last in OPEN_LEARNERS:
            if get_user_model().objects.filter(username=email).exists():
                continue  # the journey has registered already
            token = secrets.token_urlsafe(32)
            OpenRegistration.objects.create(
                email=email,
                first_name=first,
                last_name=last,
                site=course,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                notice_version=PrivacyNotice.objects.order_by("-version")
                .values_list("version", flat=True)
                .first(),
            )
            links.append(f"/#/open-courses/confirm/{token}")
        return links

    # --- end assessment extras ---

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
