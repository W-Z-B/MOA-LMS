"""Handing in: history and receipts (2.21), several files and accepted kinds (2.22), the integrity statement
(3.22), group hand-ins (2.27)."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from assessments.models import Assignment, Submission, SubmissionAttempt
from audit.models import AuditLog
from courses.models import Membership, SiteGroup
from notifications.models import Notification

PDF = b"%PDF-1.7 soil"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"


def pdf(name="report.pdf", body=PDF):
    return SimpleUploadedFile(name, body)


def submit(client, assignment, **data):
    return client.post(f"/api/v1/assignments/{assignment.id}/submit/", data, format="multipart")


@pytest.mark.django_db
def test_every_attempt_is_kept_with_a_receipt_and_the_latest_is_marked(
    site, assignment, student, lecturer, client_for
):
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    first = submit(learner, assignment, text="Draft", files=[pdf("one.pdf"), pdf("two.pdf", b"%PDF-1.7 two")])
    assert first.status_code == 201, first.json()
    body = first.json()
    assert body["attempts"] == 1 and [f["filename"] for f in body["files"]] == ["one.pdf", "two.pdf"]
    assert body["receipt"].startswith("GSA-") and body["filename"] == "one.pdf"
    second = submit(learner, assignment, text="Final", files=[pdf("final.pdf")])
    assert second.status_code == 201 and second.json()["attempts"] == 2
    assert second.json()["receipt"] != body["receipt"]
    assert Submission.objects.count() == 1 and SubmissionAttempt.objects.count() == 2

    # The receipt, with the content fingerprint, can be looked up by the student and the lecturer only.
    receipt = learner.get(f"/api/v1/receipts/{body['receipt'].lower()}/").json()
    assert receipt["attempt"] == 1 and len(receipt["content_hash"]) == 64
    assert [f["filename"] for f in receipt["files"]] == ["one.pdf", "two.pdf"]
    assert teacher.get(f"/api/v1/receipts/{body['receipt']}/").status_code == 200
    assert learner.get("/api/v1/receipts/GSA-NOTAR-EAL00/").status_code == 404
    # A receipt arrives as a notification.
    assert Notification.objects.filter(recipient=student.user, kind="receipt").count() == 2

    # The history keeps both attempts; the latest is the one marked.
    history = learner.get(f"/api/v1/submissions/{body['id']}/history/").json()
    assert [a["number"] for a in history["attempts"]] == [1, 2]
    assert [a["is_marked_attempt"] for a in history["attempts"]] == [False, True]
    assert history["attempts"][0]["text"] == "Draft" and history["moderation"] is None

    # Each file downloads under its own name; the download is audited.
    file_url = history["attempts"][0]["files"][1]["download_url"]
    download = teacher.get(file_url)
    assert download.status_code == 200 and "two.pdf" in download["Content-Disposition"]
    assert AuditLog.objects.filter(action="download", entity="assessments.submission").exists()
    receipts = AuditLog.objects.filter(action="submit").values_list("after__receipt", flat=True)
    assert set(receipts) == {body["receipt"], second.json()["receipt"]}


@pytest.mark.django_db
def test_other_people_cannot_see_a_hand_in(site, assignment, student, other_student, client_for):
    mine = submit(client_for(student.user), assignment, text="x", files=[pdf()]).json()
    other = client_for(other_student.user)
    assert other.get(f"/api/v1/receipts/{mine['receipt']}/").status_code == 404
    assert other.get(mine["files"][0]["download_url"]).status_code == 404
    assert other.get(f"/api/v1/submissions/{mine['id']}/history/").status_code == 404


@pytest.mark.django_db
def test_resubmission_rules(site, assignment, student, lecturer, client_for):
    learner = client_for(student.user)
    Assignment.objects.filter(pk=assignment.pk).update(allow_resubmission=False)
    assert submit(learner, assignment, text="once").status_code == 201
    again = submit(learner, assignment, text="twice")
    assert again.status_code == 409 and again.json()["code"] == "already_submitted"

    # With resubmission allowed, work may be replaced only until the due date, even when late work is taken.
    Assignment.objects.filter(pk=assignment.pk).update(
        allow_resubmission=True, due_at=timezone.now() - timedelta(hours=1)
    )
    late = submit(learner, assignment, text="after the due date")
    assert late.status_code == 409 and late.json()["code"] == "closed"


@pytest.mark.django_db
def test_files_are_checked_against_the_assignment(site, assignment, student, lecturer, client_for):
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    url = f"/api/v1/assignments/{assignment.id}/"
    changed = teacher.patch(url, {"accepted_kinds": ["pdf"], "max_files": 2}, format="json")
    assert changed.status_code == 200, changed.json()
    assert changed.json()["accepts"] == "PDF" and changed.json()["upload_limit_mb"] == 20
    photo = submit(learner, assignment, files=[SimpleUploadedFile("plot.jpg", JPEG)])
    assert photo.status_code == 400 and "Send PDF" in photo.json()["files"][0]
    many = submit(learner, assignment, files=[pdf("a.pdf"), pdf("b.pdf"), pdf("c.pdf")])
    assert many.status_code == 400 and many.json()["files"] == ["Send at most 2 files."]
    assert submit(learner, assignment).status_code == 400  # neither text nor a file
    bad = teacher.patch(url, {"accepted_kinds": ["exe"]}, format="json")
    assert bad.status_code == 400
    teacher.patch(url, {"accepted_kinds": ["pdf", "jpeg"], "max_files": 0}, format="json")
    assert teacher.get(url).json()["accepts"] == "PDF or JPG"
    text_only = submit(learner, assignment, files=[pdf()])
    assert text_only.json()["files"] == ["Send text only."]


@pytest.mark.django_db
def test_the_integrity_statement_is_accepted_with_each_hand_in(
    site, assignment, student, lecturer, client_for
):
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    teacher.patch(f"/api/v1/assignments/{assignment.id}/", {"requires_integrity": True}, format="json")
    shown = learner.get(f"/api/v1/assignments/{assignment.id}/").json()
    assert "my own" in shown["integrity_statement"]
    refused = submit(learner, assignment, text="x")
    assert refused.status_code == 400 and refused.json()["code"] == "integrity_required"
    accepted = submit(learner, assignment, text="x", integrity_accepted="true")
    assert accepted.status_code == 201
    attempt = SubmissionAttempt.objects.get()
    assert "my own" in attempt.integrity_statement
    history = learner.get(f"/api/v1/submissions/{accepted.json()['id']}/history/").json()
    assert history["attempts"][0]["integrity_accepted"] is True


@pytest.mark.django_db
def test_one_member_hands_in_for_the_group(site, assignment, student, other_student, lecturer, client_for):
    group = SiteGroup.objects.create(site=site, name="Plot team A")
    group.members.set(Membership.objects.filter(site=site, role="student"))
    teacher = client_for(lecturer.user)
    response = teacher.patch(
        f"/api/v1/assignments/{assignment.id}/", {"is_group": True, "groups": [group.id]}, format="json"
    )
    assert response.status_code == 200, response.json()
    handed = submit(client_for(student.user), assignment, text="Our report", files=[pdf()])
    assert handed.status_code == 201 and handed.json()["group"] == "Plot team A"
    theirs = Submission.objects.get(student=other_student)
    assert theirs.group == group and theirs.text == "Our report"
    # The other member sees the group's hand-in, its files and its receipt.
    partner = client_for(other_student.user)
    history = partner.get(f"/api/v1/submissions/{theirs.id}/history/").json()
    assert history["attempts"][0]["submitted_by"] == student.external_id
    assert partner.get(history["attempts"][0]["files"][0]["download_url"]).status_code == 200
    assert partner.get(f"/api/v1/receipts/{handed.json()['receipt']}/").status_code == 200
    # Their next hand-in is the group's second attempt.
    second = submit(partner, assignment, text="Corrected")
    assert second.json()["attempts"] == 2
    # Group-ness cannot change once work is in.
    assert (
        teacher.patch(f"/api/v1/assignments/{assignment.id}/", {"is_group": False}, format="json").status_code
        == 400
    )


@pytest.mark.django_db
def test_a_student_in_no_group_cannot_hand_in_group_work(site, assignment, student, client_for):
    Assignment.objects.filter(pk=assignment.pk).update(is_group=True)
    refused = submit(client_for(student.user), assignment, text="x")
    assert refused.status_code == 409 and refused.json()["code"] == "no_group"


@pytest.mark.django_db
def test_assignment_settings_are_checked(site, assignment, lecturer, client_for):
    from courses.models import CourseSite

    other = CourseSite.objects.create(code="OTHER-1", title="Other", is_published=True)
    foreign = SiteGroup.objects.create(site=other, name="Elsewhere")
    from assessments.models import GradeCategory

    elsewhere = GradeCategory.objects.create(site=other, name="Tests", weight=1)
    teacher = client_for(lecturer.user)
    url = f"/api/v1/assignments/{assignment.id}/"
    for change, field in (
        ({"groups": [foreign.id]}, "groups"),
        ({"category": elsewhere.id}, "category"),
        ({"late_penalty": "per_day"}, "late_penalty_percent"),
    ):
        refused = teacher.patch(url, change, format="json")
        assert refused.status_code == 400 and field in refused.json()
