"""Privacy rights (item 1.18): the notice and its acknowledgement, a person's own record, and corrections;
and the notice says what the LMS records about activity (item 1.20)."""

import json
from datetime import timedelta

import pytest
from django.utils import timezone

from audit.models import AuditLog
from conftest import PASSWORD
from notifications.models import Notification
from privacy import notice_text
from privacy.models import CorrectionRequest, NoticeAcknowledgement, PrivacyNotice

NOTICE = {"title": "How the GSA LMS uses your personal data", "body": "The LMS holds your coursework."}


@pytest.fixture
def dpo(make_user):
    return make_user("the.dpo", "dpo")


@pytest.fixture
def administrator(make_user):
    return make_user("sys.admin", "administrator")


@pytest.fixture
def published(administrator):
    return PrivacyNotice.objects.create(
        version=2, published_at=timezone.now(), published_by=administrator, **NOTICE
    )


@pytest.fixture
def marked(student, other_student, lecturer, assignment):
    """Ravi's work with a released mark, and Devi's with a mark not yet released."""
    from assessments.models import Mark, Submission

    mine = Submission.objects.create(
        assignment=assignment, student=student, text="Soil pH was 6.2", submitted_at=timezone.now()
    )
    Mark.objects.create(
        submission=mine, mark=41, feedback="Clear method.", marked_by=lecturer, is_released=True
    )
    theirs = Submission.objects.create(
        assignment=assignment, student=other_student, text="Loam", submitted_at=timezone.now()
    )
    Mark.objects.create(submission=theirs, mark=30, feedback="Devi's feedback", marked_by=lecturer)
    return mine, theirs


# ---------------------------------------------------------------------------------------------- the notice


@pytest.mark.django_db
def test_the_seeded_draft_says_what_is_recorded_and_waits_for_publication(student, client_for):
    draft = PrivacyNotice.objects.get(version=1)
    assert draft.published_at is None and draft.title == notice_text.TITLE
    body = draft.body.lower()
    for recorded in (
        "you sign in",
        "download a course file",
        "each submission",
        "how long you spend on a page",
    ):
        assert recorded in body
    me = client_for(student.user).get("/api/v1/auth/me/").json()
    assert me["privacy_notice_due"] is None  # nothing is shown until GSA publishes a version


@pytest.mark.django_db
def test_the_notice_is_written_published_and_read_once_per_version(administrator, dpo, student, client_for):
    admin = client_for(administrator)
    me = client_for(student.user)
    draft = admin.post("/api/v1/privacy/notices/", NOTICE, format="json").json()
    assert draft["version"] == 2 and draft["published_at"] is None  # version 1 is the seeded draft
    edited = admin.patch(f"/api/v1/privacy/notices/{draft['id']}/", {"title": "Your data"}, format="json")
    assert edited.json()["title"] == "Your data"
    assert me.post("/api/v1/privacy/notices/", NOTICE, format="json").status_code == 403

    published = admin.post(f"/api/v1/privacy/notices/{draft['id']}/publish/").json()
    assert published["published_at"] and published["published_by"] == "sys.admin"
    frozen = admin.patch(f"/api/v1/privacy/notices/{draft['id']}/", {"title": "Changed"}, format="json")
    assert frozen.status_code == 400
    assert admin.post(f"/api/v1/privacy/notices/{draft['id']}/publish/").json()["code"] == "published"
    older = PrivacyNotice.objects.get(version=1)
    refused = admin.post(f"/api/v1/privacy/notices/{older.id}/publish/")
    assert refused.status_code == 409 and refused.json()["code"] == "older"

    assert me.get("/api/v1/auth/me/").json()["privacy_notice_due"] == 2
    current = me.get("/api/v1/privacy/notice/").json()
    assert current["notice"]["title"] == "Your data" and current["acknowledged"] is False
    wrong = me.post("/api/v1/privacy/notice/acknowledge/", {"version": 1}, format="json")
    assert wrong.status_code == 409 and wrong.json()["code"] == "not_current"
    assert me.post("/api/v1/privacy/notice/acknowledge/", {"version": 2}, format="json").json()[
        "acknowledged"
    ]
    assert me.post("/api/v1/privacy/notice/acknowledge/", {"version": 2}, format="json").status_code == 200
    assert NoticeAcknowledgement.objects.filter(user=student.user).count() == 1
    assert AuditLog.objects.filter(action="notice_acknowledged", actor=student.user).count() == 1
    assert me.get("/api/v1/auth/me/").json()["privacy_notice_due"] is None

    third = client_for(dpo).post("/api/v1/privacy/notices/", NOTICE, format="json").json()
    client_for(dpo).post(f"/api/v1/privacy/notices/{third['id']}/publish/")
    assert me.get("/api/v1/auth/me/").json()["privacy_notice_due"] == 3  # a new version is read again
    assert AuditLog.objects.filter(action="notice_published").count() == 2


@pytest.mark.django_db
def test_the_notice_is_due_at_first_sign_in(published, student):
    from rest_framework.test import APIClient

    client = APIClient()
    signed_in = client.post(
        "/api/v1/auth/login/", {"username": "26MRP0001", "password": PASSWORD}, format="json"
    )
    assert signed_in.json()["privacy_notice_due"] == 2


# ---------------------------------------------------------------------------------------------- own record


@pytest.mark.django_db
def test_a_student_reads_and_downloads_everything_held_about_them(student, marked, site, client_for):
    from courses.models import Completion

    Completion.objects.create(site=site, person=student, completed_on=timezone.localdate())
    Notification.objects.create(recipient=student.user, title="Marks released")
    AuditLog.objects.create(
        action="login", entity="auth.user", entity_id=student.user.pk, source_ip="10.1.1.1"
    )
    me = client_for(student.user)

    data = me.get("/api/v1/privacy/my-record/").json()
    person = data["person"]
    assert (person["number"], person["kind"]) == ("26MRP0001", "Student (SRMS student number)")
    assert [m["site"] for m in person["memberships"]] == [site.code]
    assert person["submissions"][0]["assignment"] == "Soil sampling report"
    assert person["submissions"][0]["text_length"] == len("Soil pH was 6.2")
    assert "Soil pH was 6.2" not in json.dumps(data)  # metadata only: the work is opened from the course
    assert person["released_marks"] == [
        {
            "site": site.code,
            "assignment": "Soil sampling report",
            "mark": "41.00",
            "out_of": "50.00",
            "feedback": "Clear method.",
            "marked_by": "Asha Persaud",
        }
    ]
    assert person["completions"][0]["site"] == site.code
    assert data["account"]["notifications"][0]["title"] == "Marks released"
    assert data["account"]["sign_ins"][0]["from"] == "10.1.1.1"
    assert data["account"]["roles"][0]["role"] == "Student"
    assert data["teaching_actions"] is None
    assert "Devi" not in json.dumps(data)  # nothing of another student
    assert AuditLog.objects.filter(action="record_viewed", subject=student.pk).exists()

    download = me.get("/api/v1/privacy/my-record/download/")
    assert download.status_code == 200
    assert download["Content-Disposition"].startswith('attachment; filename="gsa-lms-my-data-')
    assert json.loads(download.content)["person"]["number"] == "26MRP0001"
    assert AuditLog.objects.filter(action="record_downloaded", actor=student.user).exists()


@pytest.mark.django_db
def test_an_unreleased_mark_is_not_in_the_students_copy(other_student, marked, client_for):
    data = client_for(other_student.user).get("/api/v1/privacy/my-record/").json()
    assert data["person"]["released_marks"] == [] and len(data["person"]["submissions"]) == 1


@pytest.mark.django_db
def test_a_lecturer_sees_their_memberships_and_teaching_actions(lecturer, marked, client_for):
    from assessments.models import Submission

    submission = Submission.objects.get(student__external_id="26MRP0002")
    teacher = client_for(lecturer.user)
    teacher.post(
        f"/api/v1/submissions/{submission.id}/mark/",
        {"mark": "33", "feedback": "Fine", "is_released": False},
        format="json",
    )
    data = teacher.get("/api/v1/privacy/my-record/").json()
    assert data["person"]["memberships"][0]["role"] == "Lecturer"
    assert "submissions" not in data["person"]
    assert [a["action"] for a in data["teaching_actions"]] == ["Marked"]


@pytest.mark.django_db
def test_a_student_cannot_read_another_persons_record(student, other_student, dpo, client_for):
    me = client_for(student.user)
    refused = me.get(f"/api/v1/privacy/people/{other_student.id}/record/")
    assert refused.status_code == 403 and refused.json()["code"] == "permission_denied"
    assert client_for(other_student.user).get("/api/v1/privacy/my-record/").json()["person"]["number"] == (
        "26MRP0002"
    )

    produced = client_for(dpo).get(f"/api/v1/privacy/people/{other_student.id}/record/")
    assert produced.status_code == 200 and produced.json()["person"]["number"] == "26MRP0002"
    assert AuditLog.objects.get(action="record_produced").subject == other_student.id
    assert client_for(dpo).get("/api/v1/privacy/people/999999/record/").status_code == 404


@pytest.mark.django_db
def test_an_account_with_no_person_gets_the_account_only(make_user, client_for):
    auditor = make_user("the.auditor", "auditor")
    data = client_for(auditor).get("/api/v1/privacy/my-record/").json()
    assert data["person"] is None and data["account"]["roles"][0]["role"] == "Auditor"


# ---------------------------------------------------------------------------------------------- corrections


@pytest.mark.django_db
def test_a_correction_is_asked_for_answered_and_told(student, course_admin, client_for, settings):
    settings.PRIVACY_RESPONSE_DAYS = 30
    me = client_for(student.user)
    asked = me.post(
        "/api/v1/privacy/corrections/",
        {"subject": "mark", "wrong": "My report shows as late.", "should_be": "Submitted on time"},
        format="json",
    )
    assert asked.status_code == 201, asked.content
    correction = asked.json()
    assert correction["state_name"] == "With a course administrator" and correction["is_mine"] is True
    assert correction["due_by"] == (timezone.localdate() + timedelta(days=30)).isoformat()
    assert Notification.objects.filter(
        recipient=course_admin, title="Correction requested: Ravi Singh"
    ).exists()

    url = f"/api/v1/privacy/corrections/{correction['id']}/decide/"
    assert me.post(url, {"outcome": "corrected"}, format="json").status_code == 403

    admin = client_for(course_admin)
    queue = admin.get("/api/v1/privacy/corrections/", {"state": "open"}).json()["results"]
    assert [c["person_number"] for c in queue] == ["26MRP0001"]
    no_reason = admin.post(url, {"outcome": "declined"}, format="json")
    assert no_reason.status_code == 400 and no_reason.json()["note"] == ["Say why the record is not changed."]
    answered = admin.post(
        url, {"outcome": "declined", "note": "The upload was after the deadline."}, format="json"
    )
    assert answered.json()["state_name"] == "Not changed"
    assert admin.post(url, {"outcome": "corrected"}, format="json").status_code == 409
    told = Notification.objects.get(recipient=student.user, title="Your correction request was not changed")
    assert "after the deadline" in told.body
    assert AuditLog.objects.get(action="correction_declined").reason == "The upload was after the deadline."
    assert me.get("/api/v1/privacy/corrections/").json()["results"][0]["decided_by_name"] == "course.admin"


@pytest.mark.django_db
def test_corrections_stay_with_the_person(student, other_student, course_admin, client_for):
    me = client_for(student.user)
    about_someone_else = {"person": other_student.id, "subject": "mark", "wrong": "x", "should_be": "y"}
    assert me.post("/api/v1/privacy/corrections/", about_someone_else, format="json").status_code == 403
    me.post(
        "/api/v1/privacy/corrections/",
        {"subject": "personal", "wrong": "Old", "should_be": "New"},
        format="json",
    )
    assert client_for(other_student.user).get("/api/v1/privacy/corrections/").json()["count"] == 0
    assert me.get("/api/v1/privacy/corrections/").json()["count"] == 1

    # A course administrator files a request made on paper.
    filed = client_for(course_admin).post("/api/v1/privacy/corrections/", about_someone_else, format="json")
    assert filed.status_code == 201 and filed.json()["person_number"] == "26MRP0002"


@pytest.mark.django_db
def test_nobody_answers_a_request_about_themselves(make_person, client_for):
    admin = make_person("staff", "E0009", "Natasha", "Khan", "course_admin")
    client = client_for(admin.user)
    mine = client.post(
        "/api/v1/privacy/corrections/",
        {"subject": "account", "wrong": "Old", "should_be": "New"},
        format="json",
    ).json()
    refused = client.post(
        f"/api/v1/privacy/corrections/{mine['id']}/decide/", {"outcome": "corrected"}, format="json"
    )
    assert refused.status_code == 403 and "Someone else" in refused.json()["detail"]
    assert CorrectionRequest.objects.get().state == "open"
