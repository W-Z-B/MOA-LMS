"""Item 5.03: self-paced completion rules; 5.06: completions sent to the HRMS on completion; 5.08: the
certificate issued with it."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from assessments.models import Assignment, Mark, Submission
from audit.models import AuditLog
from certificates.models import Certificate
from courses.models import Completion, ContentItem, ItemCompletion, Membership
from notifications.models import Notification
from staffdev import completion
from staffdev.models import CatalogueEntry

CATALOGUE = "/api/v1/staff-development/catalogue/"


@pytest.fixture
def learner(staff, course):
    Membership.objects.create(site=course, person=staff, role="student")
    return staff


@pytest.mark.django_db
def test_completing_every_item_completes_the_course(
    learner, course, client_for, django_capture_on_commit_callbacks, settings, monkeypatch
):
    from integration import tasks

    settings.HRMS_API_URL, settings.HRMS_API_KEY = "http://hrms-api:8000", "k"
    deferred = []
    monkeypatch.setattr(tasks.report_completion, "defer", lambda **kw: deferred.append(kw))
    CatalogueEntry.objects.filter(site=course).update(validity_months=24)
    client = client_for(learner.user)
    first, second = ContentItem.objects.filter(module__site=course)
    with django_capture_on_commit_callbacks(execute=True):
        client.get(f"/api/v1/content/{first.pk}/")
    assert not Completion.objects.exists()
    progress = client.get(f"{CATALOGUE}{course.pk}/progress/").json()
    assert progress["complete"] is False and progress["rules"][0] == {
        "code": "all_items",
        "label": "Every item completed",
        "met": False,
        "done": 1,
        "total": 2,
    }
    with django_capture_on_commit_callbacks(execute=True):
        client.post(f"/api/v1/content/{second.pk}/complete/")
    done = Completion.objects.get(site=course, person=learner)
    today = timezone.localdate()
    assert done.how == "rules" and done.completed_on == today
    assert done.expires_on == completion.add_months(today, 24)
    assert deferred == [{"completion_id": done.pk}]  # sent to the HRMS at once (item 5.06)
    certificate = Certificate.objects.get(completion=done)
    assert done.certificate == certificate.reference and certificate.reference.startswith("GSA/LMS/")
    assert certificate.file.read(4) == b"%PDF"
    assert AuditLog.objects.filter(action="completed", entity_id=done.pk).exists()
    assert Notification.objects.filter(
        recipient=learner.user, title=f"You have completed {course.title}"
    ).exists()
    assert client.get(f"{CATALOGUE}{course.pk}/").json()["my_status"] == "completed"
    assert client.post(f"{CATALOGUE}{course.pk}/join/").json()["code"] == "already_enrolled"


@pytest.mark.django_db
def test_a_quiz_must_be_passed_at_its_pass_mark(learner, course, finish_items):
    from quizzes.models import Attempt, Quiz

    entry = CatalogueEntry.objects.get(site=course)
    entry.rule_quizzes_passed = True
    entry.save()
    quiz = Quiz.objects.create(site=course, title="Check", pass_mark=Decimal("60"), is_published=True)
    Quiz.objects.create(site=course, title="Practice", is_practice=True, pass_mark=50, is_published=True)
    finish_items(course, learner)
    now = timezone.now()
    attempt = Attempt.objects.create(
        quiz=quiz,
        student=learner,
        state="finished",
        started_at=now,
        submitted_at=now,
        score=Decimal("5"),
        max_score=Decimal("10"),
        is_released=True,
    )
    assert completion.evaluate(entry, learner) is None
    rules = {r.code: r for r in completion.progress(entry, learner).rules}
    assert rules["all_items"].met and not rules["quizzes_passed"].met and rules["quizzes_passed"].total == 1
    attempt.score = Decimal("6")
    attempt.save()
    assert completion.evaluate(entry, learner) is not None


@pytest.mark.django_db
def test_an_assignment_must_be_marked_at_least_the_percentage(learner, course, finish_items):
    entry = CatalogueEntry.objects.get(site=course)
    entry.rule_all_items, entry.rule_assignment_percent = False, Decimal("70")
    entry.issue_certificate = False
    entry.save()
    task = Assignment.objects.create(
        site=course, title="Risk assessment", due_at=timezone.now(), max_mark=20, is_published=True
    )
    submission = Submission.objects.create(
        assignment=task, student=learner, text="x", submitted_at=timezone.now()
    )
    mark = Mark.objects.create(submission=submission, mark=15, is_released=False)
    assert completion.evaluate(entry, learner) is None  # not released yet
    mark.is_released = True
    mark.mark = 13  # 65%
    mark.save()
    assert completion.evaluate(entry, learner) is None
    mark.mark = 14  # 70%
    mark.save()
    done = completion.evaluate(entry, learner)
    assert done is not None and not Certificate.objects.exists()
    rule = completion.progress(entry, learner).rules[0]
    assert rule.label == "Every assignment marked at least 70%"


@pytest.mark.django_db
def test_no_rules_means_no_automatic_completion(learner, course, finish_items):
    entry = CatalogueEntry.objects.get(site=course)
    entry.rule_all_items = False
    entry.save()
    finish_items(course, learner)
    assert completion.evaluate(entry, learner) is None
    assert completion.sweep()["completed"] == 0


@pytest.mark.django_db
def test_the_nightly_sweep_catches_what_was_missed(learner, course, finish_items):
    finish_items(course, learner)  # outside a request: no check ran when they were saved
    assert completion.sweep() == {"renewals_opened": 0, "completed": 1}
    assert completion.sweep()["completed"] == 0


@pytest.mark.django_db
def test_a_renewal_counts_only_work_done_since_it_opened(learner, course, finish_items, settings):
    settings.RENEWAL_WINDOW_DAYS = 30
    entry = CatalogueEntry.objects.get(site=course)
    entry.validity_months = 12
    entry.save()
    long_ago = timezone.now() - timedelta(days=400)
    finish_items(course, learner, at=long_ago)
    first = completion.evaluate(entry, learner)
    first.completed_on, first.expires_on = (
        date.today() - timedelta(days=350),
        date.today() + timedelta(days=10),
    )
    first.reported_at = timezone.now()
    first.save()
    # Inside the renewal window: the old progress is cleared once, and the course is open to join again.
    assert completion.open_renewals() == 1 and not ItemCompletion.objects.filter(person=learner).exists()
    assert completion.open_renewals() == 0
    assert AuditLog.objects.filter(action="renewal_opened").exists()
    assert completion.evaluate(entry, learner) is None
    finish_items(course, learner)
    renewed = completion.evaluate(entry, learner)
    assert renewed.pk == first.pk and renewed.completed_on == timezone.localdate()
    assert renewed.reported_at is None and renewed.external_ref.endswith(f":{timezone.localdate():%Y%m%d}")
    assert Certificate.objects.filter(person=learner).count() == 2
    assert AuditLog.objects.filter(action="renewed", entity_id=renewed.pk).exists()


@pytest.mark.django_db
def test_course_administrators_record_a_completion(course_admin, staff, course, client_for):
    url = f"{CATALOGUE}{course.pk}/record-completion/"
    future = (timezone.localdate() + timedelta(days=1)).isoformat()
    admin = client_for(course_admin)
    assert admin.post(url, {"person": staff.pk, "completed_on": future}, format="json").status_code == 400
    made = admin.post(url, {"person": staff.pk, "completed_on": "2026-09-01"}, format="json")
    assert made.status_code == 201 and made.json()["how"] == "recorded"
    assert client_for(staff.user).post(url, {"person": staff.pk}, format="json").status_code == 403
    progress = admin.get(f"{CATALOGUE}{course.pk}/progress/?person={staff.pk}")
    assert progress.json()["completed_on"] == "2026-09-01"
    assert client_for(staff.user).get(f"{CATALOGUE}{course.pk}/progress/?person=1").status_code == 403


@pytest.mark.django_db
def test_a_check_that_fails_after_saving_is_left_for_the_sweep(
    learner, course, finish_items, monkeypatch, django_capture_on_commit_callbacks
):
    def broken(*args, **kwargs):
        raise RuntimeError("PDF engine down")

    monkeypatch.setattr(completion, "evaluate", broken)
    with django_capture_on_commit_callbacks(execute=True):
        finish_items(course, learner)
    assert not Completion.objects.exists()
