"""To do and search (items 2.07 to 2.09) carry what staff development and accounts leave people waiting on:
enrolment requests to decide, required training due, people to invite; and the catalogue is searchable."""

from datetime import timedelta

import pytest
from django.utils import timezone

from people.models import PersonRef
from staffdev.models import EnrolmentRequest, RequiredTraining, TrainingAssignment

TODO = "/api/v1/to-do/"


@pytest.mark.django_db
def test_the_supervisor_sees_requests_to_decide_and_the_course_admin_those_without_one(
    staff, supervisor, course_admin, make_person, make_course, client_for
):
    course = make_course("SD-701", "Leadership", self_enrol="approval")
    EnrolmentRequest.objects.create(
        site=course, person=staff, approver=supervisor, waiting_since=timezone.now()
    )
    other = make_person("staff", "E0270", "No", "Boss")
    EnrolmentRequest.objects.create(site=course, person=other, waiting_since=timezone.now())
    mine = client_for(supervisor.user).get(TODO).json()
    assert [(i["kind"], i["title"]) for i in mine] == [("enrolment", "Joy Lall: Leadership")]
    admin = client_for(course_admin).get(TODO).json()
    assert [(i["kind"], i["title"]) for i in admin] == [("enrolment", "No Boss: Leadership")]
    assert [i["kind"] for i in client_for(staff.user).get(TODO).json()] == []


@pytest.mark.django_db
def test_staff_see_required_training_falling_due(staff, make_course, client_for, settings):
    settings.REQUIRED_TRAINING_REMIND_DAYS = 7
    soon, later = make_course("SD-702", "Fire drill"), make_course("SD-703", "First aid")
    today = timezone.localdate()
    for site, due in ((soon, today - timedelta(days=1)), (later, today + timedelta(days=30))):
        requirement = RequiredTraining.objects.create(site=site)
        TrainingAssignment.objects.create(
            requirement=requirement, person=staff, assigned_on=today, due_on=due
        )
    items = client_for(staff.user).get(TODO).json()
    assert [(i["kind"], i["title"], i["overdue"]) for i in items] == [
        ("required_training", "Fire drill", True)
    ]


@pytest.mark.django_db
def test_administrators_see_people_still_to_invite(make_user, client_for):
    admin = make_user("admin", "administrator")
    assert [i["kind"] for i in client_for(admin).get(TODO).json()] == []
    PersonRef.objects.create(kind="student", external_id="26MRP0900", email="new@x.gy", campus_code="MRP")
    items = client_for(admin).get(TODO).json()
    assert [(i["kind"], i["title"]) for i in items] == [
        ("accounts", "1 person has no account yet: invite them")
    ]


@pytest.mark.django_db
def test_search_finds_catalogue_courses_for_staff_only(staff, student, course_admin, make_course, client_for):
    make_course("SD-704", "Pesticide handling", audience="Farm staff")
    make_course("SD-705", "Pesticide draft", published=False)
    found = client_for(staff.user).get("/api/v1/search/?q=pesticide").json()["catalogue"]
    assert [(h["title"], h["sub"]) for h in found] == [("Pesticide handling", "Farm staff")]
    assert len(client_for(course_admin).get("/api/v1/search/?q=pesticide").json()["catalogue"]) == 1
    assert client_for(student.user).get("/api/v1/search/?q=pesticide").json()["catalogue"] == []
