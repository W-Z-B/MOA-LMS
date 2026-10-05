"""Messages (item 4.11): students write to teaching staff, never to other students unless GSA asks; staff
write to members, a group or the whole site; read receipts; notices; the phone's offline queue."""

import uuid

import pytest

from audit.models import AuditLog
from forums.tests import accept
from messaging.models import Conversation, Message
from notifications.models import Notification


@pytest.fixture
def teacher(client_for, lecturer):
    accept(lecturer.user)
    return client_for(lecturer.user)


@pytest.fixture
def learner(client_for, student):
    accept(student.user)
    return client_for(student.user)


@pytest.fixture
def classmate(client_for, other_student):
    accept(other_student.user)
    return client_for(other_student.user)


@pytest.fixture
def assistant(make_person, site):
    from courses.models import Membership

    person = make_person("staff", "E0002", "Kevin", "Bacchus")
    Membership.objects.create(site=site, person=person, role="assistant")
    return person


def start(client, site, **body):
    data = {"site": site.id, "subject": "Soil test results", "body": "When are they back?", **body}
    return client.post("/api/v1/conversations/", data, format="json")


@pytest.mark.django_db
def test_a_student_writes_to_all_the_teaching_staff_and_they_answer(
    site, learner, teacher, lecturer, assistant, student, client_for
):
    made = start(learner, site)
    assert made.status_code == 201 and made.json()["audience"] == "direct" and made.json()["may_send"]
    conversation = Conversation.objects.get()
    assert set(conversation.participants.values_list("user_id", flat=True)) == {
        student.user_id,
        lecturer.user_id,
        assistant.user_id,
    }
    assert Message.objects.get().body == "<p>When are they back?</p>"
    assert (
        Notification.objects.filter(recipient=lecturer.user, dedupe_key__startswith="message:").count() == 1
    )
    assert not Notification.objects.filter(recipient=student.user).exists()
    assert AuditLog.objects.filter(entity="messaging.message", action="create").exists()

    mine = teacher.get("/api/v1/conversations/").json()
    assert mine[0]["unread"] == 1
    answered = teacher.post(
        f"/api/v1/conversations/{conversation.id}/messages/", {"body": "Friday."}, format="json"
    )
    assert answered.status_code == 201
    assert teacher.get("/api/v1/conversations/").json()[0]["unread"] == 0  # sending reads it
    assert learner.get("/api/v1/conversations/").json()[0]["unread"] == 1

    detail = learner.get(f"/api/v1/conversations/{conversation.id}/").json()
    first = detail["messages"][0]
    assert first["mine"] and first["read_by"] == ["Asha Persaud"]
    learner.post(f"/api/v1/conversations/{conversation.id}/read/")
    assert learner.get("/api/v1/conversations/").json()[0]["unread"] == 0
    seen = teacher.get(f"/api/v1/conversations/{conversation.id}/").json()["messages"][1]
    assert seen["read_by"] == ["Ravi Singh"]
    assert learner.get(f"/api/v1/conversations/?site={site.id}").json()[0]["id"] == conversation.id

    # Only participants see a conversation.
    kevin = client_for(assistant.user)
    assert kevin.get(f"/api/v1/conversations/{conversation.id}/").status_code == 200
    outsider_conv = start(teacher, site, recipients=[student.id]).json()
    assert kevin.get(f"/api/v1/conversations/{outsider_conv['id']}/").status_code == 404


@pytest.mark.django_db
def test_students_do_not_write_to_other_students_unless_gsa_turns_it_on(
    site, learner, other_student, lecturer, settings
):
    refused = start(learner, site, recipients=[other_student.id])
    assert refused.status_code == 403
    names = {r["name"] for r in learner.get(f"/api/v1/conversations/recipients/?site={site.id}").json()}
    assert names == {"Asha Persaud"}
    chosen = start(learner, site, recipients=[lecturer.id])
    assert chosen.status_code == 201

    settings.MESSAGING_STUDENT_TO_STUDENT = True
    assert start(learner, site, recipients=[other_student.id]).status_code == 201
    assert start(learner, site, recipients=[999999]).status_code == 400


@pytest.mark.django_db
def test_teaching_staff_send_notices_to_a_group_or_the_site_and_students_cannot_reply_in_them(
    site, teacher, learner, classmate, student, other_student
):
    from courses.models import Membership, SiteGroup

    group = SiteGroup.objects.create(site=site, name="Field group 1")
    group.members.add(Membership.objects.get(site=site, person=student))
    assert start(teacher, site).status_code == 400  # a direct message needs recipients
    no_group = start(teacher, site, audience="group", group=999999)
    assert no_group.status_code == 400
    empty = SiteGroup.objects.create(site=site, name="Empty")
    assert start(teacher, site, audience="group", group=empty.id).status_code == 400

    notice = start(teacher, site, audience="group", group=group.id, subject="Boots tomorrow").json()
    assert notice["may_send"] is True
    assert Notification.objects.filter(recipient=student.user).count() == 1
    assert not Notification.objects.filter(recipient=other_student.user).exists()
    seen = learner.get("/api/v1/conversations/").json()
    assert seen[0]["may_send"] is False
    no_reply = learner.post(f"/api/v1/conversations/{notice['id']}/messages/", {"body": "OK"}, format="json")
    assert no_reply.status_code == 403
    assert classmate.get(f"/api/v1/conversations/{notice['id']}/").status_code == 404

    whole = start(teacher, site, audience="site", subject="Farm closed Monday")
    assert whole.status_code == 201
    assert Notification.objects.filter(recipient=other_student.user).count() == 1
    assert start(learner, site, audience="site").status_code == 403


@pytest.mark.django_db
def test_sending_needs_the_conduct_statement_and_membership(site, client_for, student, make_person, lecturer):
    fresh = client_for(student.user)
    refused = start(fresh, site)
    assert refused.status_code == 403 and refused.json()["code"] == "conduct_not_accepted"
    outsider = make_person("student", "26MRP0700", "Not", "Here", "student")
    accept(outsider.user)
    assert start(client_for(outsider.user), site).status_code == 400  # the site reads as unknown
    accept(student.user)
    conversation = start(fresh, site).json()
    from courses.models import Membership

    Membership.objects.filter(person=student).update(is_active=False)
    gone = fresh.post(
        f"/api/v1/conversations/{conversation['id']}/messages/", {"body": "Hello?"}, format="json"
    )
    assert gone.status_code == 403


@pytest.mark.django_db
def test_a_message_sent_twice_from_the_phone_queue_is_saved_once(site, learner):
    from practicals.conftest import now_iso

    conversation = start(learner, site).json()
    key = str(uuid.uuid4())
    url = f"/api/v1/conversations/{conversation['id']}/messages/"
    body = {"body": "Sent from the field", "client_sent_at": now_iso(hours=-2)}
    first = learner.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    again = learner.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == again.status_code == 201 and again["Idempotent-Replay"] == "true"
    assert Message.objects.filter(body="<p>Sent from the field</p>").count() == 1
    old = learner.post(url, {"body": "Too old", "client_sent_at": now_iso(days=-8)}, format="json")
    assert old.status_code == 400 and old.json()["code"] == "client_time_too_old"


@pytest.mark.django_db
def test_starting_a_conversation_is_idempotent_under_one_key(site, learner):
    key = str(uuid.uuid4())
    body = {"site": site.id, "subject": "Once", "body": "Hello"}
    for _ in range(2):
        made = learner.post("/api/v1/conversations/", body, format="json", HTTP_IDEMPOTENCY_KEY=key)
        assert made.status_code == 201
    assert Conversation.objects.filter(subject="Once").count() == 1


@pytest.mark.django_db
def test_a_course_administrator_sends_a_site_notice_and_auditors_send_nothing(
    site, client_for, course_admin, make_user, other_student
):
    accept(course_admin)
    admin = client_for(course_admin)
    assert start(admin, site, audience="site").status_code == 201
    assert Notification.objects.filter(recipient=other_student.user).exists()
    auditor = make_user("auditor.two", "auditor")
    accept(auditor)
    assert start(client_for(auditor), site).status_code == 403
    assert client_for(auditor).get(f"/api/v1/conversations/recipients/?site={site.id}").json() == []
