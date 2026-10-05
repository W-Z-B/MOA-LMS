from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from assessments.models import Assignment, Mark, Submission
from assessments.services import coursework_percent


@pytest.mark.django_db
def test_submit_mark_release_and_gradebook(site, assignment, student, other_student, lecturer, client_for):
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    url = f"/api/v1/assignments/{assignment.id}/"

    assert learner.post(f"{url}submit/", {}, format="json").status_code == 400
    submitted = learner.post(f"{url}submit/", {"text": "Samples taken at plots 3 and 7."}, format="json")
    assert submitted.status_code == 201 and submitted.json()["is_late"] is False
    # Teaching staff cannot submit; students cannot list submissions or mark.
    assert teacher.post(f"{url}submit/", {"text": "x"}, format="json").status_code == 403
    assert learner.get(f"{url}submissions/").status_code == 403
    submission_id = submitted.json()["id"]
    assert learner.post(f"/api/v1/submissions/{submission_id}/mark/", {"mark": "50"}).status_code == 403

    assert teacher.get(f"{url}submissions/").json()[0]["student_no"] == "26MRP0001"
    too_high = teacher.post(f"/api/v1/submissions/{submission_id}/mark/", {"mark": "60"}, format="json")
    assert too_high.status_code == 400
    marked = teacher.post(
        f"/api/v1/submissions/{submission_id}/mark/",
        {"mark": "40", "feedback": "Good method."},
        format="json",
    )
    assert marked.status_code == 200 and marked.json()["mark"]["is_released"] is False

    # Unreleased marks are invisible to the student; the lecturer's gradebook already counts them.
    own = learner.get(f"/api/v1/sites/{site.id}/gradebook/").json()
    assert len(own["rows"]) == 1 and own["rows"][0]["coursework_percent"] is None
    book = teacher.get(f"/api/v1/sites/{site.id}/gradebook/").json()
    by_student = {r["student_no"]: r for r in book["rows"]}
    assert by_student["26MRP0001"]["coursework_percent"] == "80.00"
    assert by_student["26MRP0002"]["coursework_percent"] is None  # not yet due, nothing submitted

    teacher.post(
        f"/api/v1/submissions/{submission_id}/mark/",
        {"mark": "40", "feedback": "Good method.", "is_released": True},
        format="json",
    )
    released = learner.get(f"/api/v1/sites/{site.id}/gradebook/").json()["rows"][0]
    assert released["coursework_percent"] == "80.00"
    assert released["marks"][str(assignment.id)]["feedback"] == "Good method."
    # A marked submission cannot be replaced.
    assert (
        learner.post(f"{url}submit/", {"text": "second try"}, format="json").json()["code"]
        == "already_marked"
    )


@pytest.mark.django_db
def test_work_handed_in_as_a_file_is_checked_and_kept_under_a_random_name(
    site, assignment, student, lecturer, client_for, settings
):
    """Item 1.12."""
    learner = client_for(student.user)
    url = f"/api/v1/assignments/{assignment.id}/submit/"
    disguised = SimpleUploadedFile("Ravi Singh report.docx", b"<html><script>steal()</script></html>")
    refused = learner.post(url, {"file": disguised}, format="multipart")
    assert refused.status_code == 400 and "do not match its name" in refused.json()["file"][0]
    settings.UPLOAD_LIMIT_SUBMISSION_MB = 1
    big = SimpleUploadedFile("Ravi Singh report.pdf", b"%PDF-1.7" + b"0" * (1024 * 1024))
    assert learner.post(url, {"file": big}, format="multipart").json()["file"] == [
        "The file is larger than 1 MB."
    ]

    report = SimpleUploadedFile("Ravi Singh report.pdf", b"%PDF-1.7 soil")
    handed_in = learner.post(url, {"file": report}, format="multipart")
    assert handed_in.status_code == 201 and handed_in.json()["filename"] == "Ravi Singh report.pdf"
    stored = Submission.objects.get()
    assert stored.file.name.startswith("submissions/") and "Ravi" not in stored.file.name
    download = client_for(lecturer.user).get(handed_in.json()["download_url"])
    assert download.status_code == 200 and "Ravi Singh report.pdf" in download["Content-Disposition"]


@pytest.mark.django_db
def test_late_and_closed_submissions(site, assignment, student, client_for):
    learner = client_for(student.user)
    Assignment.objects.filter(pk=assignment.pk).update(due_at=timezone.now() - timedelta(hours=1))
    late = learner.post(f"/api/v1/assignments/{assignment.id}/submit/", {"text": "Sorry"}, format="json")
    assert late.status_code == 201 and late.json()["is_late"] is True
    Submission.objects.all().delete()
    Assignment.objects.filter(pk=assignment.pk).update(allow_late=False)
    closed = learner.post(f"/api/v1/assignments/{assignment.id}/submit/", {"text": "Sorry"}, format="json")
    assert closed.status_code == 409 and closed.json()["code"] == "closed"


@pytest.mark.django_db
def test_coursework_is_weighted_and_overdue_missing_work_counts_as_zero(
    site, assignment, student, other_student
):
    now = timezone.now()
    quiz = Assignment.objects.create(
        site=site, title="Quiz 1", due_at=now - timedelta(days=1), max_mark=20, weight=1, is_published=True
    )
    Assignment.objects.create(
        site=site, title="Draft, not published", due_at=now - timedelta(days=1), max_mark=10, weight=5
    )
    report = Submission.objects.create(assignment=assignment, student=student, text="x", submitted_at=now)
    Mark.objects.create(submission=report, mark=40)  # 40/50 at weight 2
    done = Submission.objects.create(assignment=quiz, student=student, text="x", submitted_at=now)
    Mark.objects.create(submission=done, mark=10)  # 10/20 at weight 1
    # (2*0.8 + 1*0.5) / 3 = 70%
    assert coursework_percent(site, student) == Decimal("70.00")
    # The other student missed the overdue quiz (zero) and the report is not due yet (does not count).
    assert coursework_percent(site, other_student) == Decimal("0.00")
