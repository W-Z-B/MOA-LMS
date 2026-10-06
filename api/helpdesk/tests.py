"""Item 7.17: asking for help from the page one is on; course administrators answer."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from audit.models import AuditLog
from helpdesk.models import HelpRequest
from notifications.models import Notification

URL = "/api/v1/help-requests/"
ASK = {
    "subject": "Cannot find my quiz",
    "message": "The quiz is not on the Quizzes tab.",
    "page": "/sites/4/quizzes",
}


@pytest.fixture
def campus_admin(make_user):
    from iam.models import Role, RoleScope

    user = make_user("ca.essequibo", email="ca@gsa.edu.gy")
    RoleScope.objects.create(user=user, role=Role.objects.get(code="course_admin"), campus_code="ESQ")
    return user


@pytest.mark.django_db
def test_a_student_asks_for_help_and_course_administrators_are_told(
    student, course_admin, campus_admin, client_for
):
    client = client_for(student.user)
    sent = client.post(URL, ASK, format="json")
    assert sent.status_code == 201, sent.content
    body = sent.json()
    assert body["status"] == "open" and body["page"] == "/sites/4/quizzes" and body["mine"] is True
    assert body["asked_by_name"] == "Ravi Singh"
    # The course administrator for every campus is told; the one for another campus is not.
    notes = Notification.objects.filter(link=f"/help/requests/{body['id']}")
    assert [n.recipient for n in notes] == [course_admin]
    note = notes.get()
    assert note.kind == "approval" and "Ravi Singh" in note.title and "/sites/4/quizzes" in note.body
    assert AuditLog.objects.filter(entity="helpdesk.helprequest", action="create").count() == 1
    # It waits in the course administrator's To do.
    todo = client_for(course_admin).get("/api/v1/to-do/").json()
    assert [t["link"] for t in todo if t["kind"] == "help_request"] == [f"/help/requests/{body['id']}"]


@pytest.mark.django_db
def test_with_no_course_administrator_the_administrators_are_told(student, make_user, client_for):
    admin = make_user("sys.admin", "administrator")
    sent = client_for(student.user).post(URL, ASK, format="json")
    assert sent.status_code == 201
    assert list(Notification.objects.values_list("recipient", flat=True)) == [admin.pk]


@pytest.mark.django_db
def test_a_request_needs_a_subject_a_message_and_an_address_inside_the_lms(student, client_for):
    client = client_for(student.user)
    empty = client.post(URL, {"subject": "  ", "message": " ", "page": ""}, format="json")
    assert empty.status_code == 400 and {"subject", "message"} <= set(empty.json())
    outside = client.post(URL, {**ASK, "page": "https://example.com/phish"}, format="json")
    assert outside.status_code == 400 and "inside the LMS" in outside.json()["page"][0]
    assert not HelpRequest.objects.exists()


@pytest.mark.django_db
def test_sending_again_from_the_offline_queue_changes_nothing(student, course_admin, client_for):
    client = client_for(student.user)
    key = str(uuid.uuid4())
    written = (timezone.now() - timedelta(hours=2)).isoformat()
    first = client.post(URL, {**ASK, "client_sent_at": written}, format="json", HTTP_IDEMPOTENCY_KEY=key)
    again = client.post(URL, {**ASK, "client_sent_at": written}, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == again.status_code == 201
    assert again["Idempotent-Replay"] == "true"
    assert HelpRequest.objects.count() == 1 and Notification.objects.count() == 1
    assert HelpRequest.objects.get().client_sent_at is not None


@pytest.mark.django_db
def test_too_many_requests_in_an_hour_are_refused(student, client_for, settings):
    settings.HELP_REQUESTS_PER_HOUR = 2
    client = client_for(student.user)
    assert client.post(URL, ASK, format="json").status_code == 201
    assert client.post(URL, ASK, format="json").status_code == 201
    third = client.post(URL, ASK, format="json")
    assert third.status_code == 429 and third.json()["code"] == "too_many_help_requests"


@pytest.mark.django_db
def test_people_see_their_own_requests_and_answerers_see_all(
    student, other_student, course_admin, client_for
):
    client_for(student.user).post(URL, ASK, format="json")
    client_for(other_student.user).post(URL, {**ASK, "subject": "Password"}, format="json")
    mine = client_for(student.user).get(URL).json()
    assert [r["subject"] for r in mine] == ["Cannot find my quiz"]
    theirs = HelpRequest.objects.get(subject="Password")
    assert client_for(student.user).get(f"{URL}{theirs.pk}/").status_code == 404
    everyone = client_for(course_admin).get(URL, {"status": "open"}).json()
    assert {r["subject"] for r in everyone} == {"Cannot find my quiz", "Password"}
    assert all(r["mine"] is False for r in everyone)
    assert client_for(course_admin).get(f"{URL}{theirs.pk}/").json()["asked_by_name"] == "Devi Ramnarine"
    assert client_for(course_admin).get(URL, {"mine": "1"}).json() == []


@pytest.mark.django_db
def test_a_course_administrator_answers_and_the_person_is_told(student, course_admin, client_for):
    asked = client_for(student.user).post(URL, ASK, format="json").json()
    admin = client_for(course_admin)
    blank = admin.post(f"{URL}{asked['id']}/answer/", {"answer": " "}, format="json")
    assert blank.status_code == 400
    answered = admin.post(
        f"{URL}{asked['id']}/answer/", {"answer": "It opens on Monday at 08:00."}, format="json"
    )
    assert answered.status_code == 200, answered.content
    assert answered.json()["status"] == "answered" and answered.json()["answered_by_name"] == "course.admin"
    note = Notification.objects.get(recipient=student.user)
    assert note.body == "It opens on Monday at 08:00." and note.link == "/help/requests"
    assert AuditLog.objects.filter(entity="helpdesk.helprequest", action="answered").count() == 1
    # Answered once only, and it leaves To do.
    again = admin.post(f"{URL}{asked['id']}/answer/", {"answer": "Again"}, format="json")
    assert again.status_code == 409 and again.json()["code"] == "already_answered"
    assert not [t for t in admin.get("/api/v1/to-do/").json() if t["kind"] == "help_request"]
    # The student sees the answer on their own list.
    assert client_for(student.user).get(URL).json()[0]["answer"] == "It opens on Monday at 08:00."


@pytest.mark.django_db
def test_only_answerers_answer_and_never_their_own_request(student, course_admin, make_user, client_for):
    asked = client_for(student.user).post(URL, ASK, format="json").json()
    refused = client_for(student.user).post(f"{URL}{asked['id']}/answer/", {"answer": "Fixed"}, format="json")
    assert refused.status_code == 403
    other_admin = make_user("course.admin2", "course_admin")
    own = client_for(course_admin).post(URL, {**ASK, "page": ""}, format="json").json()
    assert Notification.objects.filter(recipient=other_admin, link=f"/help/requests/{own['id']}").exists()
    assert not Notification.objects.filter(
        recipient=course_admin, link=f"/help/requests/{own['id']}"
    ).exists()
    self_answer = client_for(course_admin).post(
        f"{URL}{own['id']}/answer/", {"answer": "Done"}, format="json"
    )
    assert self_answer.status_code == 403
    assert not [
        t
        for t in client_for(course_admin).get("/api/v1/to-do/").json()
        if t["link"].endswith(f"/{own['id']}")
    ]
