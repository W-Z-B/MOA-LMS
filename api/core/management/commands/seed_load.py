"""A whole class for the load test (item 7.08): `python manage.py seed_load --fictional --students 60`.

One published course site with a lecturer and the class, four modules of pages, announcements, an assignment
and a quiz open now (twenty multiple-choice questions, five to a page, any number of attempts so the test can
be run again). Students are load.student01 and onwards, the lecturer load.lecturer; they share the password
in LOAD_USER_PASSWORD; the lecturer's authenticator is enrolled from LOAD_TOTP_SECRET when it is set.
loadtest/locustfile.py signs them in and has the class sit the quiz while others browse.

Fictional people only, for a test stack: never run it on a database that holds real records. Idempotent.
"""

import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from assessments.models import Assignment
from courses.models import Announcement, ContentItem, CourseSite, Membership, Module
from iam.models import Role, RoleScope, TotpDevice
from people.models import PersonRef
from quizzes import schemas
from quizzes.models import Question, QuestionBank, QuestionCategory, QuestionVersion, Quiz, QuizSlot

SITE = "LOAD101-2026-27-S1-MRP"
PAGE = (
    "<h2>{title}</h2><p>Soil holds water and nutrients for the crop. Its texture, from sand to clay, decides "
    "how fast water drains and how much the roots can reach.</p><ul><li>Sand drains fast.</li><li>Clay holds "
    "water.</li><li>Loam is between the two.</li></ul><p>Read the notes before the practical.</p>"
)


class Command(BaseCommand):
    help = "Load-test data: one course, its class and a quiz open now (fictional people only)."

    def add_arguments(self, parser):
        parser.add_argument("--fictional", action="store_true", help="Required: this database is a test")
        parser.add_argument("--students", type=int, default=60)
        parser.add_argument("--questions", type=int, default=20)

    def handle(self, *args, **options):
        if not options["fictional"]:
            raise CommandError("Add --fictional: this command makes fictional people for a test stack.")
        password = os.environ.get("LOAD_USER_PASSWORD", "")
        if len(password) < 12:
            raise CommandError("Set LOAD_USER_PASSWORD (12 characters or more) for the fictional accounts.")
        call_command("seed", "--country", "GY", verbosity=0)
        with transaction.atomic():
            site = self._site()
            lecturer = self._person(
                "load.lecturer", "staff", "E9000", "Load", "Lecturer", Role.LECTURER, password
            )
            Membership.objects.get_or_create(site=site, person=lecturer, defaults={"role": "lecturer"})
            secret = os.environ.get("LOAD_TOTP_SECRET", "")
            if (
                secret
            ):  # the lecturer's authenticator, so the test can sign in as teaching staff do (ADR 0013)
                TotpDevice.objects.get_or_create(
                    user=lecturer.user, defaults={"secret": secret, "confirmed_at": timezone.now()}
                )
            for n in range(1, options["students"] + 1):
                student = self._person(
                    f"load.student{n:02d}",
                    "student",
                    f"L2026{n:03d}",
                    "Student",
                    f"{n:02d}",
                    Role.STUDENT,
                    password,
                )
                Membership.objects.get_or_create(site=site, person=student, defaults={"role": "student"})
            self._content(site, lecturer)
            quiz = self._quiz(site, options["questions"])
        self.stdout.write(
            f"Load-test data: {site.code} with {options['students']} students and quiz {quiz.pk} "
            f"({options['questions']} questions)."
        )

    @staticmethod
    def _site() -> CourseSite:
        site, _ = CourseSite.objects.get_or_create(
            code=SITE,
            defaults={
                "title": "LOAD101 Soil and Water (load test)",
                "term_code": "2026-27-S1",
                "campus_code": "MRP",
                "is_published": True,
            },
        )
        return site

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

    @staticmethod
    def _content(site, lecturer) -> None:
        if site.modules.exists():
            return
        for m in range(1, 5):
            module = Module.objects.create(site=site, title=f"Week {m}: Soil and water", position=m)
            for p in range(1, 6):
                title = f"Notes {m}.{p}"
                ContentItem.objects.create(
                    module=module, title=title, body=PAGE.format(title=title), position=p
                )
        for n in range(1, 4):
            Announcement.objects.create(
                site=site, title=f"Week {n} reminders", body="Bring your field notebook.", author=lecturer
            )
        Assignment.objects.create(
            site=site,
            title="Soil texture report",
            due_at=timezone.now() + timedelta(days=14),
            max_mark=50,
            is_published=True,
        )

    @staticmethod
    def _quiz(site, count: int) -> Quiz:
        quiz = Quiz.objects.filter(site=site, title="Class test: soil and water").first()
        if quiz is not None:
            return quiz
        bank = QuestionBank.objects.create(site=site, name="LOAD101 questions")
        category = QuestionCategory.objects.create(bank=bank, name="Soil and water")
        quiz = Quiz.objects.create(
            site=site,
            title="Class test: soil and water",
            opens_at=timezone.now() - timedelta(hours=1),
            closes_at=timezone.now() + timedelta(days=30),
            time_limit_minutes=60,
            attempts_allowed=0,
            questions_per_page=5,
        )
        for n in range(1, count + 1):
            text = f"Question {n}: which soil holds the most water?"
            data = schemas.validate_question(
                "multichoice",
                text,
                {
                    "single": True,
                    "shuffle": True,
                    "choices": [
                        {"id": "a", "text": "Clay", "fraction": 1, "feedback": "Yes."},
                        {"id": "b", "text": "Sand", "fraction": 0, "feedback": "No."},
                        {"id": "c", "text": "Gravel", "fraction": 0, "feedback": "No."},
                        {"id": "d", "text": "Silt", "fraction": 0, "feedback": "Not the most."},
                    ],
                },
            )
            question = Question.objects.create(
                bank=bank, category=category, qtype="multichoice", name=f"Q{n}"
            )
            QuestionVersion.objects.create(question=question, text=text, data=data, default_mark=1)
            QuizSlot.objects.create(quiz=quiz, position=n, question=question)
        Quiz.objects.filter(pk=quiz.pk).update(is_published=True)
        return quiz
