"""Item 5.04: learning paths; item 5.05: required training, with due dates, reminders, renewal and the
overdue report."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from audit.models import AuditLog
from courses.models import Completion, Membership
from notifications.models import Notification
from staffdev import completion, required
from staffdev.models import CatalogueEntry, RequiredTraining, TrainingAssignment

PATHS = "/api/v1/staff-development/paths/"
REQUIRED = "/api/v1/staff-development/required/"


@pytest.fixture
def induction(course_admin, make_course, client_for):
    first = make_course("SD-501", "Welcome to GSA")
    second = make_course("SD-502", "Teaching basics")
    made = client_for(course_admin).post(
        PATHS,
        {
            "code": "induction",
            "title": "New lecturer induction",
            "sites": [first.pk, second.pk],
            "is_published": True,
        },
        format="json",
    )
    assert made.status_code == 201, made.json()
    return made.json()["id"], first, second


@pytest.mark.django_db
def test_a_path_opens_its_courses_one_after_another(staff, induction, client_for, finish_items):
    path_id, first, second = induction
    client = client_for(staff.user)
    assert client.get(PATHS).json()["count"] == 1
    joined = client.post(f"{PATHS}{path_id}/join/").json()
    assert joined["joined"] and [s["state"] for s in joined["steps"]] == ["open", "locked"]
    assert Membership.objects.filter(site=first, person=staff, is_active=True).exists()
    locked = client.post(f"/api/v1/staff-development/catalogue/{second.pk}/join/")
    assert locked.status_code == 409 and locked.json()["code"] == "path_locked"
    assert "Welcome to GSA" in locked.json()["detail"]

    finish_items(first, staff)
    completion.sweep()
    progress = client.get(f"{PATHS}{path_id}/progress/").json()
    assert [s["state"] for s in progress["steps"]] == ["done", "open"] and progress["done"] == 1
    assert progress["steps"][1]["enrolled"] is True  # put forward for the next course at once
    assert Notification.objects.filter(
        recipient=staff.user, title__startswith="Next on New lecturer"
    ).exists()
    finish_items(second, staff)
    completion.sweep()
    assert client.get(f"{PATHS}{path_id}/progress/").json()["complete"] is True


@pytest.mark.django_db
def test_only_course_administrators_make_paths(
    staff, student, course_admin, induction, make_course, client_for
):
    path_id, first, second = induction
    attempt = {"code": "x", "title": "X", "sites": [first.pk]}
    assert client_for(staff.user).post(PATHS, attempt, format="json").status_code == 403
    admin = client_for(course_admin)
    assert admin.post(PATHS, {**attempt, "sites": []}, format="json").status_code == 400
    assert admin.post(PATHS, {**attempt, "sites": [first.pk, first.pk]}, format="json").status_code == 400
    third = make_course("SD-503", "Assessment")
    changed = admin.patch(f"{PATHS}{path_id}/", {"sites": [third.pk, first.pk]}, format="json")
    assert [s["title"] for s in changed.json()["steps"]] == ["Assessment", "Welcome to GSA"]
    assert AuditLog.objects.filter(entity="staffdev.learningpath", action="update").exists()
    assert admin.patch(f"{PATHS}{path_id}/", {"is_published": False}, format="json").status_code == 200
    assert client_for(staff.user).get(PATHS).json()["count"] == 0
    assert client_for(student.user).get(PATHS).status_code == 403
    assert client_for(student.user).post(f"{PATHS}{path_id}/join/").status_code in (403, 404)


@pytest.fixture
def farm_safety(make_course):
    return make_course("SD-601", "Farm safety", self_enrol="closed")


@pytest.mark.django_db
def test_required_training_is_assigned_by_post(staff, lecturer, course_admin, farm_safety, client_for):
    admin = client_for(course_admin)
    made = admin.post(
        REQUIRED,
        {"site": farm_safety.pk, "post_title": "farm supervisor", "due_days": 14, "renewal_months": 12},
        format="json",
    )
    assert made.status_code == 201 and made.json()["applies_to"] == "post farm supervisor"
    assignment = TrainingAssignment.objects.get()
    assert assignment.person == staff and assignment.due_on == timezone.localdate() + timedelta(days=14)
    # Required: they are put on the course, closed to joining or not.
    assert Membership.objects.filter(site=farm_safety, person=staff, is_active=True).exists()
    assert Notification.objects.filter(recipient=staff.user, title="Required training: Farm safety").exists()
    mine = client_for(staff.user).get(f"{REQUIRED}mine/").json()
    assert mine[0]["state"] == "due" and mine[0]["site_title"] == "Farm safety"
    assert client_for(lecturer.user).get(f"{REQUIRED}mine/").json() == []
    assert client_for(staff.user).get(REQUIRED).status_code == 403
    assert client_for(staff.user).post(REQUIRED, {"site": farm_safety.pk}, format="json").status_code == 403
    assert admin.post(f"{REQUIRED}{made.json()['id']}/assign/").json() == {"assigned": 0}

    # A requirement must be a staff-development course.
    from courses.models import CourseSite

    academic = CourseSite.objects.create(code="ACAD-9", title="Academic")
    assert admin.post(REQUIRED, {"site": academic.pk}, format="json").status_code == 400


@pytest.mark.django_db
def test_reminders_overdue_report_completion_and_renewal(
    staff, course_admin, farm_safety, client_for, finish_items, settings
):
    settings.REQUIRED_TRAINING_REMIND_DAYS, settings.RENEWAL_WINDOW_DAYS = 7, 30
    requirement = RequiredTraining.objects.create(
        site=farm_safety, unit_code="FARM", due_days=5, renewal_months=12
    )
    today = timezone.localdate()
    ran = required.daily(today)
    assert (ran["assigned"], ran["due_soon"], ran["overdue"]) == (1, 1, 0)
    assert required.remind(today) == {"due_soon": 0, "overdue": 0}  # once per due date
    later = today + timedelta(days=6)
    assert required.remind(later) == {"due_soon": 0, "overdue": 1}
    TrainingAssignment.objects.update(due_on=today - timedelta(days=1))
    report = client_for(course_admin).get(f"{REQUIRED}overdue/?campus_code=MRP").json()
    assert report["count"] == 1 and report["results"][0]["employee_no"] == "E0201"
    assert report["results"][0]["state"] == "overdue"
    assert client_for(staff.user).get(f"{REQUIRED}overdue/").status_code == 403

    # Completing the course completes the assignment; the completion lasts as long as the requirement says.
    finish_items(farm_safety, staff)
    completion.sweep()
    assignment = TrainingAssignment.objects.get()
    assert assignment.completed_on == today
    done = Completion.objects.get(person=staff, site=farm_safety)
    assert done.expires_on == completion.add_months(today, 12)
    assert required.overdue().count() == 0

    # As the expiry comes near the assignment opens again, due on the day it runs out.
    Completion.objects.filter(pk=done.pk).update(expires_on=today + timedelta(days=20))
    assert required.reopen_renewals(today) == 1
    assignment.refresh_from_db()
    assert assignment.completed_on is None and assignment.due_on == today + timedelta(days=20)
    assert Notification.objects.filter(recipient=staff.user, title="Time to renew: Farm safety").exists()
    assert required.reopen_renewals(today) == 0
    assert requirement.describe() == "unit FARM"


@pytest.mark.django_db
def test_someone_who_already_completed_is_assigned_as_done(staff, farm_safety):
    Completion.objects.create(site=farm_safety, person=staff, completed_on=date(2026, 9, 1))
    requirement = RequiredTraining.objects.create(site=farm_safety, campus_code="MRP")
    assert required.assign(requirement) == 1
    assert TrainingAssignment.objects.get().completed_on == date(2026, 9, 1)
    assert not Membership.objects.filter(site=farm_safety, person=staff).exists()
    inactive = RequiredTraining.objects.create(site=farm_safety, is_active=False)
    assert required.assign(inactive) == 0
    other_campus = RequiredTraining(site=farm_safety, campus_code="COR")
    assert not required.matches(other_campus, staff)
    assert CatalogueEntry.objects.get(site=farm_safety).self_enrol == "closed"


def test_months_are_added_to_the_end_of_a_short_month():
    assert completion.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert completion.add_months(date(2026, 11, 30), 14) == date(2028, 1, 30)


@pytest.mark.django_db
def test_the_scheduled_runs(staff, farm_safety):
    from approvals.tasks import chase_decisions
    from staffdev.tasks import completion_sweep, required_training

    RequiredTraining.objects.create(site=farm_safety)
    assert required_training()["assigned"] == 1
    assert completion_sweep()["completed"] == 0
    assert chase_decisions() == {"reminded": 0, "escalated": 0}
