"""Item 5.02: the staff-development catalogue, joining it, and enrolment approved through the approvals
engine."""

from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone

from approvals.models import Delegation
from audit.models import AuditLog
from courses.models import CourseSite, Membership
from notifications.models import Notification
from staffdev.models import EnrolmentRequest

CATALOGUE = "/api/v1/staff-development/catalogue/"


@pytest.mark.django_db
def test_staff_browse_the_published_catalogue(staff, student, course, make_course, client_for):
    make_course("SD-302", "Hidden draft", published=False)
    CourseSite.objects.create(code="ACAD-1", title="Academic", is_published=True)
    body = client_for(staff.user).get(CATALOGUE).json()
    assert [c["code"] for c in body["results"]] == ["SD-301"]
    row = body["results"][0]
    assert row["my_status"] == "none" and row["places_left"] is None and row["length_hours"] == "4.0"
    assert client_for(staff.user).get(f"{CATALOGUE}?q=nothing").json()["count"] == 0
    detail = client_for(staff.user).get(f"{CATALOGUE}{course.pk}/")
    assert detail.status_code == 200 and detail.json()["summary"] == "About Farm safety"
    # Students have no business with the staff catalogue.
    assert client_for(student.user).get(CATALOGUE).status_code == 403


@pytest.mark.django_db
def test_course_administrators_see_drafts_and_set_the_entry(
    course_admin, staff, course, make_course, client_for
):
    make_course("SD-302", "Hidden draft", published=False)
    admin = client_for(course_admin)
    listed = admin.get(CATALOGUE).json()["results"]
    assert {c["code"] for c in listed} == {"SD-301", "SD-302"} and listed[0]["my_status"] is None

    site = CourseSite.objects.create(code="SD-400", title="New one", kind="staff_development")
    entry = {
        "summary": "Pesticide handling",
        "audience": "Farm staff",
        "self_enrol": "approval",
        "capacity": 10,
    }
    saved = admin.put(f"{CATALOGUE}{site.pk}/entry/", entry, format="json")
    assert saved.status_code == 200 and saved.json()["capacity"] == 10
    assert AuditLog.objects.filter(entity="staffdev.catalogueentry", action="create").exists()
    changed = admin.put(f"{CATALOGUE}{site.pk}/entry/", {**entry, "capacity": 12}, format="json")
    assert changed.json()["capacity"] == 12
    assert AuditLog.objects.filter(entity="staffdev.catalogueentry", action="update").exists()

    academic = CourseSite.objects.create(code="ACAD-2", title="Academic")
    refused = admin.put(f"{CATALOGUE}{academic.pk}/entry/", entry, format="json")
    assert refused.status_code == 400 and refused.json()["code"] == "not_staff_development"
    assert client_for(staff.user).put(f"{CATALOGUE}{site.pk}/entry/", entry, format="json").status_code == 403


@pytest.mark.django_db
def test_joining_an_open_course_enrols_at_once(staff, course, client_for):
    client = client_for(staff.user)
    joined = client.post(f"{CATALOGUE}{course.pk}/join/", {}, format="json")
    assert joined.status_code == 201 and joined.json() == {"outcome": "enrolled", "request": None}
    membership = Membership.objects.get(site=course, person=staff)
    assert membership.role == "student" and membership.is_active
    assert AuditLog.objects.filter(action="enrolled", entity_id=membership.pk).exists()
    again = client.post(f"{CATALOGUE}{course.pk}/join/", {}, format="json")
    assert again.status_code == 409 and again.json()["code"] == "already_enrolled"
    assert client.get(f"{CATALOGUE}{course.pk}/").json()["my_status"] == "enrolled"


@pytest.mark.django_db
def test_closed_full_and_unlisted_courses_are_refused(staff, student, make_course, make_person, client_for):
    client = client_for(staff.user)
    closed = make_course("SD-310", "Closed", self_enrol="closed")
    assert client.post(f"{CATALOGUE}{closed.pk}/join/").json()["code"] == "closed"
    full = make_course("SD-311", "Full", capacity=1)
    Membership.objects.create(site=full, person=make_person("staff", "E0290", "Al", "Ready"), role="student")
    refused = client.post(f"{CATALOGUE}{full.pk}/join/")
    assert refused.status_code == 409 and refused.json()["code"] == "full"
    assert client.get(f"{CATALOGUE}{full.pk}/").json()["places_left"] == 0
    draft = make_course("SD-312", "Draft", published=False)
    assert client.post(f"{CATALOGUE}{draft.pk}/join/").status_code == 404
    student_join = client_for(student.user).post(f"{CATALOGUE}{full.pk}/join/")
    assert student_join.status_code == 403 and student_join.json()["code"] == "not_staff"


@pytest.mark.django_db
def test_without_a_supervisor_the_course_administrators_decide(staff, course_admin, make_course, client_for):
    course = make_course("SD-320", "Records", self_enrol="approval")
    client = client_for(staff.user)
    asked = client.post(f"{CATALOGUE}{course.pk}/join/", {"reason": "My post needs it"}, format="json")
    assert asked.status_code == 201 and asked.json()["outcome"] == "requested"
    request = EnrolmentRequest.objects.get(pk=asked.json()["request"])
    assert request.approver is None and request.waiting_since is not None
    assert Notification.objects.filter(recipient=course_admin, kind="approval").exists()
    assert client.post(f"{CATALOGUE}{course.pk}/join/").json()["code"] == "already_requested"
    assert client.get(f"{CATALOGUE}{course.pk}/").json()["my_status"] == "requested"

    # The person who asked never decides; the course administrators do, and must say why they refuse.
    mine = client.get("/api/v1/staff-development/requests/?mine=1").json()["results"][0]
    assert mine["allowed_actions"] == ["withdraw"]
    assert client.post(f"/api/v1/staff-development/requests/{request.pk}/approve/").status_code == 403
    admin = client_for(course_admin)
    waiting = admin.get("/api/v1/approvals/waiting/").json()
    assert waiting[0]["kind"] == "enrolment" and waiting[0]["overdue"] is False
    no_reason = admin.post(f"/api/v1/staff-development/requests/{request.pk}/reject/", {}, format="json")
    assert no_reason.status_code == 400 and no_reason.json()["code"] == "comment_required"
    approved = admin.post(f"/api/v1/staff-development/requests/{request.pk}/approve/", {}, format="json")
    assert approved.status_code == 200 and approved.json()["state"] == "approved"
    assert Membership.objects.filter(site=course, person=staff, is_active=True).exists()
    assert Notification.objects.filter(recipient=staff.user, title__startswith="You can start").exists()
    assert AuditLog.objects.filter(action="transition:approve", entity_id=request.pk).exists()
    late = admin.post(
        f"/api/v1/staff-development/requests/{request.pk}/reject/", {"comment": "x"}, format="json"
    )
    assert late.status_code == 409


@pytest.mark.django_db
def test_the_supervisor_or_their_stand_in_decides(
    staff, supervisor, course_admin, make_person, make_course, client_for
):
    staff.supervisor = supervisor
    staff.save()
    course = make_course("SD-321", "Leadership", self_enrol="approval")
    asked = client_for(staff.user).post(f"{CATALOGUE}{course.pk}/join/").json()
    request = EnrolmentRequest.objects.get(pk=asked["request"])
    assert request.approver == supervisor
    url = f"/api/v1/staff-development/requests/{request.pk}/"
    # A course administrator is only the stand-in while there is no supervisor to go to.
    assert client_for(course_admin).post(f"{url}approve/").status_code == 403
    colleague = make_person("staff", "E0203", "Stand", "In")
    assert client_for(colleague.user).get(url).status_code == 404  # not theirs to see
    today = timezone.localdate()
    Delegation.objects.create(delegator=supervisor, delegate=colleague, starts=today, ends=today)
    seen = client_for(colleague.user).get("/api/v1/approvals/waiting/").json()
    assert seen[0]["for_whom"] == "standing in for Mark Boss"
    rejected = client_for(colleague.user).post(f"{url}reject/", {"comment": "Not this term"}, format="json")
    assert rejected.status_code == 200 and rejected.json()["state"] == "rejected"
    assert Notification.objects.filter(recipient=staff.user, body="Not this term").exists()


@pytest.mark.django_db
def test_a_supervisor_who_cannot_sign_in_is_passed_over(staff, supervisor, make_course, client_for):
    supervisor.user.is_active = False
    supervisor.user.save()
    staff.supervisor = supervisor
    staff.save()
    course = make_course("SD-322", "Leadership", self_enrol="approval")
    asked = client_for(staff.user).post(f"{CATALOGUE}{course.pk}/join/").json()
    assert EnrolmentRequest.objects.get(pk=asked["request"]).approver is None


@pytest.mark.django_db
def test_the_owner_withdraws_and_a_full_course_cannot_be_approved(
    staff, course_admin, make_person, make_course, client_for
):
    course = make_course("SD-323", "Small", self_enrol="approval", capacity=1)
    first = client_for(staff.user).post(f"{CATALOGUE}{course.pk}/join/").json()["request"]
    other = make_person("staff", "E0291", "Second", "Person")
    second = client_for(other.user).post(f"{CATALOGUE}{course.pk}/join/").json()["request"]
    admin = client_for(course_admin)
    assert admin.post(f"/api/v1/staff-development/requests/{first}/approve/").status_code == 200
    full = admin.post(f"/api/v1/staff-development/requests/{second}/approve/")
    assert full.status_code == 409 and full.json()["code"] == "full"
    withdrawn = client_for(other.user).post(f"/api/v1/staff-development/requests/{second}/withdraw/")
    assert withdrawn.json()["state"] == "withdrawn"
    states = client_for(course_admin).get("/api/v1/staff-development/requests/?state=withdrawn").json()
    assert states["count"] == 1


@pytest.mark.django_db
def test_waiting_requests_are_chased_then_sent_up_the_line(
    staff, supervisor, make_person, make_course, settings
):
    from approvals.time_limits import chase

    settings.DECISION_DAYS, settings.ESCALATE_AFTER_DAYS = 3, 2
    big_boss = make_person("staff", "E0204", "Big", "Boss")
    supervisor.supervisor = big_boss
    supervisor.save()
    course = make_course("SD-330", "Slow", self_enrol="approval")
    request = EnrolmentRequest.objects.create(
        site=course, person=staff, approver=supervisor, waiting_since=timezone.now()
    )
    monday = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
    start = timezone.make_aware(datetime.combine(monday - timedelta(days=7), time.min))
    EnrolmentRequest.objects.filter(pk=request.pk).update(waiting_since=start)
    # Monday a week ago to this Friday: 9 working days, past the reminder and the escalation.
    friday = monday + timedelta(days=4)
    assert chase(monday + timedelta(days=-2)) == {"reminded": 1, "escalated": 0}  # Saturday: 4 working days
    assert Notification.objects.filter(recipient=supervisor.user, title__startswith="Waiting").exists()
    assert chase(friday) == {"reminded": 0, "escalated": 1}
    request.refresh_from_db()
    assert request.approver == big_boss
    assert Notification.objects.filter(recipient=staff.user, title__contains="sent on to Big Boss").exists()
    assert AuditLog.objects.filter(action="escalated", entity_id=request.pk).exists()

    # With nobody above, it goes to the course administrators, and from there they are reminded.
    EnrolmentRequest.objects.filter(pk=request.pk).update(waiting_since=start)
    assert chase(friday) == {"reminded": 0, "escalated": 1}
    request.refresh_from_db()
    assert request.approver is None
    EnrolmentRequest.objects.filter(pk=request.pk).update(waiting_since=start)
    assert chase(friday) == {"reminded": 1, "escalated": 0}


def test_working_days_skip_weekends():
    from datetime import date

    from approvals.time_limits import working_days

    assert working_days(date(2026, 10, 5), date(2026, 10, 11)) == 5  # Monday to Sunday
    assert working_days(date(2026, 10, 10), date(2026, 10, 11)) == 0
    assert working_days(date(2026, 10, 12), date(2026, 10, 5)) == 0
    assert working_days(date(2026, 10, 5), date(2026, 10, 19)) == 11


@pytest.mark.django_db
def test_stand_ins_are_named_checked_and_ended(staff, supervisor, make_person, course_admin, client_for):
    url = "/api/v1/approvals/delegations/"
    today = timezone.localdate()
    client = client_for(supervisor.user)
    period = {"starts": today.isoformat(), "ends": (today + timedelta(days=5)).isoformat()}
    assert client.post(url, {"delegate": supervisor.pk, **period}, format="json").status_code == 400
    gone = make_person("staff", "E0205", "Gone", "Soon")
    gone.is_active = False
    gone.save()
    assert client.post(url, {"delegate": gone.pk, **period}, format="json").status_code == 400
    past = {"starts": "2020-01-01", "ends": "2020-01-02"}
    assert client.post(url, {"delegate": staff.pk, **past}, format="json").status_code == 400
    backwards = {"starts": period["ends"], "ends": period["starts"]}
    assert client.post(url, {"delegate": staff.pk, **backwards}, format="json").status_code == 400
    made = client.post(url, {"delegate": staff.pk, "reason": "Leave", **period}, format="json")
    assert made.status_code == 201 and made.json()["in_force"] is True
    assert Notification.objects.filter(recipient=staff.user, title="You stand in for Mark Boss").exists()
    overlap = client.post(url, {"delegate": staff.pk, **period}, format="json")
    assert overlap.status_code == 400
    # Only the person who named a stand-in, or a course administrator, names one for someone else or ends it.
    other = client_for(staff.user).post(url, {"delegator": supervisor.pk, "delegate": staff.pk, **period})
    assert other.status_code == 400
    assert client_for(staff.user).get(url).json()["count"] == 1  # the delegate sees it too
    assert client_for(staff.user).post(f"{url}{made.json()['id']}/end/").status_code == 403
    assert client_for(course_admin).get(f"{url}?person={supervisor.pk}").json()["count"] == 1
    ended = client.post(f"{url}{made.json()['id']}/end/")
    assert ended.status_code == 200 and ended.json()["cancelled"] is True
    assert client.post(f"{url}{made.json()['id']}/end/").status_code == 409


@pytest.mark.django_db
def test_the_engine_refuses_a_move_it_does_not_know(staff, course_admin, make_course, rf):
    from approvals.engine import WorkflowError
    from staffdev.enrolment import WORKFLOW

    course = make_course("SD-340", "X", self_enrol="approval")
    request = EnrolmentRequest.objects.create(site=course, person=staff, state="approved")
    web = rf.post("/")
    web.user = course_admin
    with pytest.raises(WorkflowError) as refused:
        WORKFLOW.apply(request, "approve", request=web)
    assert refused.value.code == "invalid_transition"
