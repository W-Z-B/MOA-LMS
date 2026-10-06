"""Item 7.16: the student orientation course, made by seed_orientation, and enrolment at first sign-in."""

from io import StringIO

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from audit.models import AuditLog
from conftest import PASSWORD
from courses.models import Completion, ContentItem, CourseSite, ItemCompletion, Membership
from notifications.models import Notification
from quizzes.models import Quiz
from quizzes.services import quiz_problems, start_attempt
from staffdev import completion, orientation
from staffdev.models import CatalogueEntry


def seed() -> str:
    out = StringIO()
    call_command("seed_orientation", stdout=out)
    return out.getvalue()


def sign_in(username: str):
    client = APIClient()
    response = client.post("/api/v1/auth/login/", {"username": username, "password": PASSWORD}, format="json")
    assert response.status_code == 200, response.content
    return client


@pytest.mark.django_db
def test_seed_orientation_makes_the_course_once(settings):
    first = seed()
    assert "added the course" in first
    course = CourseSite.objects.get(code=settings.ORIENTATION_SITE_CODE)
    assert course.title == "Getting started with the GSA LMS" and course.is_published
    assert course.kind == CourseSite.Kind.STAFF_DEVELOPMENT
    entry = CatalogueEntry.objects.get(site=course)
    assert entry.rule_all_items and entry.self_enrol == "open" and not entry.issue_certificate
    pages = ContentItem.objects.filter(module__site=course)
    assert pages.count() == 9 and set(pages.values_list("kind", flat=True)) == {"page"}
    assert "Practice: write a logbook entry" in pages.values_list("title", flat=True)
    quiz = Quiz.objects.get(site=course)
    assert quiz.is_practice and quiz.is_published and quiz.attempts_allowed == 0
    assert quiz.slots.count() == 4 and quiz_problems(quiz) == []
    # Running it again changes nothing, and keeps what a course administrator edited.
    ContentItem.objects.filter(title="Quizzes").update(body="<p>Edited by GSA.</p>")
    logged = AuditLog.objects.count()
    assert "nothing changed" in seed()
    assert ContentItem.objects.filter(module__site=course).count() == 9
    assert ContentItem.objects.get(title="Quizzes").body == "<p>Edited by GSA.</p>"
    assert Quiz.objects.filter(site=course).count() == 1 and AuditLog.objects.count() == logged


@pytest.mark.django_db
def test_seed_orientation_adds_only_what_is_missing():
    seed()
    ContentItem.objects.filter(title="Quizzes").delete()
    Quiz.objects.all().delete()
    out = seed()
    assert "page Quizzes" in out and "the practice quiz" in out and "the course" not in out.split(":")[1]


@pytest.mark.django_db
def test_a_new_student_is_enrolled_at_first_sign_in_only_once(student, settings):
    seed()
    course = orientation.site()
    sign_in(student.external_id)
    membership = Membership.objects.get(site=course, person=student)
    assert membership.role == "student" and membership.is_active
    assert AuditLog.objects.filter(action="enrolled", entity="courses.membership").count() == 1
    # A course administrator takes them off; signing in again does not put them back.
    Membership.objects.filter(pk=membership.pk).update(is_active=False)
    sign_in(student.external_id)
    assert Membership.objects.filter(site=course, person=student, is_active=True).count() == 0
    # The student sees it among their courses.
    Membership.objects.filter(pk=membership.pk).update(is_active=True)
    client = sign_in(student.external_id)
    codes = [s["code"] for s in client.get("/api/v1/sites/").json()["results"]]
    assert settings.ORIENTATION_SITE_CODE in codes


@pytest.mark.django_db
def test_no_enrolment_when_switched_off_unmade_or_not_a_student(student, make_person, settings):
    sign_in(student.external_id)  # the course is not made yet
    assert not Membership.objects.exists()
    seed()
    settings.ORIENTATION_AUTO_ENROL = False
    sign_in(student.external_id)
    assert not Membership.objects.filter(person=student).exists()
    settings.ORIENTATION_AUTO_ENROL = True
    staff = make_person("staff", "E0042", "Nadia", "Khan")
    sign_in(staff.external_id)
    assert not Membership.objects.filter(person=staff).exists()
    assert orientation.enrol_new_student(None) is None


@pytest.mark.django_db
def test_signing_in_works_even_if_enrolment_fails(student, monkeypatch):
    seed()

    def broken(*args, **kwargs):
        raise RuntimeError("database trouble")

    monkeypatch.setattr(orientation, "enrol_new_student", broken)
    sign_in(student.external_id)
    assert not Membership.objects.filter(person=student).exists()


@pytest.mark.django_db
def test_reading_every_page_completes_it_and_the_practice_quiz_never_counts(student):
    seed()
    course = orientation.site()
    orientation.enrol_new_student(student)
    entry = CatalogueEntry.objects.get(site=course)
    quiz = Quiz.objects.get(site=course)
    attempt, _ = start_attempt(quiz, student, student.user)
    assert attempt.max_score > 0
    pages = list(ContentItem.objects.filter(module__site=course))
    for page in pages[:-1]:
        ItemCompletion.objects.create(person=student, item=page, completed_at=page.created_at, how="marked")
    assert completion.evaluate(entry, student) is None
    ItemCompletion.objects.create(
        person=student, item=pages[-1], completed_at=pages[-1].created_at, how="marked"
    )
    done = completion.evaluate(entry, student)
    assert isinstance(done, Completion) and done.how == "rules"
    note = Notification.objects.get(recipient=student.user, title__startswith="You have completed")
    # A student is not told it goes to the HRMS, and is sent back to the course.
    assert note.body == "Well done." and note.link == f"/sites/{course.pk}"
