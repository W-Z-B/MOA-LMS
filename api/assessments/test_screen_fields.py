"""What the marking and gradebook screens read beyond the rules themselves: anonymous marks kept out of the
staff total until release (3.16), the SRMS lock shown on marks and on the gradebook (3.18), practical and
forum columns in the gradebook (2.28), and a hand-in shown beside the mark (2.23)."""

import csv
import io
import zipfile
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from assessments.models import Assignment, Mark, SrmsTransfer, Submission
from audit.models import AuditLog

PDF = b"%PDF-1.7\n%fictional\n"


def docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("word/document.xml", "<w:document/>")
    return buffer.getvalue()


def handed(assignment, person, at, mark=None, released=False):
    submission = Submission.objects.create(assignment=assignment, student=person, text="x", submitted_at=at)
    if mark is not None:
        Mark.objects.create(submission=submission, mark=mark, is_released=released)
    return submission


@pytest.mark.django_db
def test_anonymous_marks_stay_out_of_the_staff_total_until_released(
    site, assignment, student, other_student, lecturer, client_for
):
    past = timezone.now() - timedelta(days=1)
    Assignment.objects.filter(pk=assignment.pk).update(anonymous=True, due_at=past)
    handed(assignment, student, past, mark=40)
    teacher = client_for(lecturer.user)

    working = teacher.get(f"/api/v1/sites/{site.id}/coursework/working/?person={student.id}").json()
    item = working["items"][0]
    assert (item["state"], item["anonymous"], item["final_mark"], item["percent"]) == (
        "pending",
        True,
        None,
        None,
    )
    assert working["coursework_percent"] is None  # nothing else counts: the mark cannot be worked back
    book = teacher.get(f"/api/v1/sites/{site.id}/gradebook/").json()
    ravi = next(r for r in book["rows"] if r["student_no"] == "26MRP0001")
    assert ravi["coursework_percent"] is None
    # Devi handed nothing in: that counts as zero, and says nothing about anyone's mark.
    devi = next(r for r in book["rows"] if r["student_no"] == "26MRP0002")
    assert devi["coursework_percent"] == "0.00"
    exported = teacher.get(f"/api/v1/sites/{site.id}/gradebook/export/")
    rows = list(csv.reader(io.StringIO(b"".join(exported.streaming_content).decode("utf-8-sig"))))
    line = next(r for r in rows if r[0] == "26MRP0001")
    assert line[2] == "pending (anonymous marking)" and "pending (anonymous marking)" in line[-1]

    assert teacher.post(f"/api/v1/assignments/{assignment.id}/release/").json() == {"released": 1}
    working = teacher.get(f"/api/v1/sites/{site.id}/coursework/working/?person={student.id}").json()
    assert working["items"][0]["state"] == "graded" and working["coursework_percent"] == "80.00"
    # The student's own working was never affected: it counts released marks only.
    own = client_for(student.user).get(f"/api/v1/sites/{site.id}/coursework/working/").json()
    assert own["items"][0]["anonymous"] is False and own["coursework_percent"] == "80.00"


@pytest.mark.django_db
def test_the_srms_lock_shows_on_the_mark_and_in_the_gradebook(
    site, assignment, student, other_student, lecturer, client_for
):
    past = timezone.now() - timedelta(days=1)
    submission = handed(assignment, student, past, mark=40, released=True)
    teacher = client_for(lecturer.user)
    rows = teacher.get(f"/api/v1/assignments/{assignment.id}/submissions/").json()
    assert rows[0]["srms_locked_at"] is None
    assert all(r["srms"] is None for r in teacher.get(f"/api/v1/sites/{site.id}/gradebook/").json()["rows"])

    sent = timezone.now()
    SrmsTransfer.objects.create(site=site, student=student, percent=80, outcome="accepted", sent_at=sent)
    SrmsTransfer.objects.create(site=site, student=other_student, percent=0, outcome="unknown", sent_at=sent)
    rows = teacher.get(f"/api/v1/assignments/{assignment.id}/submissions/").json()
    assert rows[0]["id"] == submission.id and rows[0]["srms_locked_at"] is not None
    book = {
        r["student_no"]: r["srms"] for r in teacher.get(f"/api/v1/sites/{site.id}/gradebook/").json()["rows"]
    }
    assert book["26MRP0001"]["outcome"] == "accepted" and book["26MRP0001"]["locked_since"] is not None
    assert book["26MRP0002"]["outcome"] == "unknown" and book["26MRP0002"]["locked_since"] is None
    own = client_for(student.user).get(f"/api/v1/assignments/{assignment.id}/").json()["my_submission"]
    assert own["srms_locked_at"] is not None


@pytest.mark.django_db
def test_the_gradebook_has_columns_for_practical_tasks_and_graded_forums(site, student, lecturer, client_for):
    from forums.models import Forum, ParticipationMark
    from practicals.models import PracticalTask

    task = PracticalTask.objects.create(
        site=site,
        title="Prepare a bed",
        weight=1,
        is_published=True,
        closes_at=timezone.now() - timedelta(days=1),
    )
    PracticalTask.objects.create(site=site, title="Not counted", weight=0, is_published=True)
    forum = Forum.objects.create(site=site, title="Debate", forum_type="graded", weight=1, max_mark=10)
    ParticipationMark.objects.create(forum=forum, student=student, mark=8, is_released=True)
    book = client_for(lecturer.user).get(f"/api/v1/sites/{site.id}/gradebook/").json()
    assert [t["title"] for t in book["practicals"]] == ["Prepare a bed"]
    assert [f["title"] for f in book["forums"]] == ["Debate"]
    ravi = next(r for r in book["rows"] if r["student_no"] == "26MRP0001")
    assert ravi["practicals"][str(task.id)] == {"state": "zero", "percent": "0.00"}
    assert ravi["forums"][str(forum.id)] == {"state": "graded", "percent": "80.00"}
    own = client_for(student.user).get(f"/api/v1/sites/{site.id}/gradebook/").json()
    assert [r["student_no"] for r in own["rows"]] == ["26MRP0001"]


@pytest.mark.django_db
def test_a_pdf_or_photograph_is_shown_in_the_page_and_anything_else_downloads(
    site, assignment, student, other_student, lecturer, client_for
):
    learner = client_for(student.user)
    handed_in = learner.post(
        f"/api/v1/assignments/{assignment.id}/submit/",
        {
            "text": "",
            "files": [
                SimpleUploadedFile("profile.pdf", PDF),
                SimpleUploadedFile("notes.docx", docx()),
            ],
        },
        format="multipart",
    )
    assert handed_in.status_code == 201, handed_in.json()
    pdf_url, docx_url = (f["download_url"] for f in handed_in.json()["files"])
    teacher = client_for(lecturer.user)

    shown = teacher.get(f"{pdf_url}?inline=1")
    assert shown.status_code == 200 and shown["Content-Type"] == "application/pdf"
    assert shown["Content-Disposition"].startswith("inline")
    assert (
        shown["X-Frame-Options"] == "SAMEORIGIN"
        and shown["Content-Security-Policy"] == "frame-ancestors 'self'"
    )
    assert AuditLog.objects.filter(action="download", after__shown=True).count() == 1

    # Without asking, or for a kind the browser cannot show, the file downloads under its own name.
    assert teacher.get(pdf_url)["Content-Disposition"].startswith("attachment")
    kept = teacher.get(f"{docx_url}?inline=1")
    assert (
        kept["Content-Disposition"].startswith("attachment") and "notes.docx" in kept["Content-Disposition"]
    )
    assert kept["X-Frame-Options"] != "SAMEORIGIN"
    # Someone who may not see the work still cannot, inline or not.
    assert client_for(other_student.user).get(f"{pdf_url}?inline=1").status_code == 404
