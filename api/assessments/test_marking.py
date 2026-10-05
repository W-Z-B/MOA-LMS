"""The marking screen: moving through the class, drafts and release (2.23), feedback files (2.24), the
archive and spreadsheet marks (2.25), group marks (2.27), anonymous marking (3.16), moderation (3.17),
the SRMS lock (3.18) and the history kept for appeals (3.19)."""

import io
import zipfile
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from assessments.models import Assignment, Mark, MarkVersion, SrmsTransfer, Submission
from audit.models import AuditLog
from courses.models import Membership, SiteGroup
from notifications.models import Notification

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 32


def hand_in(client, assignment, text="My work", files=()):
    response = client.post(
        f"/api/v1/assignments/{assignment.id}/submit/", {"text": text, "files": list(files)}, format="multipart"
    )
    assert response.status_code == 201, response.json()
    return response.json()


def mark(client, submission_id, value, **extra):
    return client.post(f"/api/v1/submissions/{submission_id}/mark/", {"mark": value, **extra}, format="json")


@pytest.fixture
def second_marker(make_person, site):
    person = make_person("staff", "E0002", "Kumar", "Das", "lecturer")
    Membership.objects.create(site=site, person=person, role="lecturer")
    return person


@pytest.fixture
def both(site, assignment, student, other_student, client_for):
    """Both students have handed in; returns their submission ids in student-number order."""
    first = hand_in(client_for(student.user), assignment)
    second = hand_in(client_for(other_student.user), assignment, files=[SimpleUploadedFile("plot.pdf", b"%PDF-1.7")])
    return first["id"], second["id"]


@pytest.mark.django_db
def test_drafts_next_and_previous_and_release_all(site, assignment, student, lecturer, client_for, both):
    teacher, learner = client_for(lecturer.user), client_for(student.user)
    first, second = both
    order = teacher.get(f"/api/v1/submissions/{first}/neighbours/").json()
    assert order == {
        "position": 1,
        "total": 2,
        "previous": None,
        "next": second,
        "previous_unmarked": None,
        "next_unmarked": second,
    }
    assert mark(teacher, first, "30", feedback="Draft thoughts").json()["mark"]["is_released"] is False
    # The draft is invisible to the student.
    assert learner.get(f"/api/v1/assignments/{assignment.id}/").json()["my_submission"]["mark"] is None
    assert teacher.get(f"/api/v1/submissions/{second}/neighbours/").json()["previous_unmarked"] is None
    mark(teacher, second, "45")
    assert learner.get(f"/api/v1/submissions/{first}/neighbours/").status_code == 403

    released = teacher.post(f"/api/v1/assignments/{assignment.id}/release/")
    assert released.json() == {"released": 2}
    assert Mark.objects.filter(is_released=True).count() == 2
    assert Notification.objects.filter(recipient=student.user, kind="mark").exists()
    shown = learner.get(f"/api/v1/assignments/{assignment.id}/").json()["my_submission"]["mark"]
    assert shown["mark"] == "30.00" and shown["feedback"] == "Draft thoughts"
    assert AuditLog.objects.filter(action="marks_released").exists()
    assert teacher.post(f"/api/v1/assignments/{assignment.id}/release/").json() == {"released": 0}


@pytest.mark.django_db
def test_every_mark_change_is_kept(site, assignment, student, lecturer, client_for, both):
    teacher, learner = client_for(lecturer.user), client_for(student.user)
    first, _ = both
    mark(teacher, first, "20")
    mark(teacher, first, "25", is_released=True)
    mark(teacher, first, "26", feedback="Re-marked on appeal", is_released=True)
    assert MarkVersion.objects.filter(submission_id=first).count() == 3
    staff_view = teacher.get(f"/api/v1/submissions/{first}/history/").json()
    assert [m["mark"] for m in staff_view["marks"]] == ["20.00", "25.00", "26.00"]
    assert staff_view["marks"][0]["changed_by"] == "Asha Persaud" or staff_view["marks"][0]["changed_by"]
    # The student sees the released versions only, and not who changed them.
    own = learner.get(f"/api/v1/submissions/{first}/history/").json()
    assert [m["mark"] for m in own["marks"]] == ["25.00", "26.00"] and own["marks"][0]["changed_by"] is None
    assert mark(teacher, first, "-1").status_code == 400
    assert AuditLog.objects.filter(action="mark", entity="assessments.submission").count() == 3


@pytest.mark.django_db
def test_feedback_files_and_recordings(site, assignment, student, other_student, lecturer, client_for, both):
    teacher, learner = client_for(lecturer.user), client_for(student.user)
    first, _ = both
    url = f"/api/v1/submissions/{first}/feedback-files/"
    recording = SimpleUploadedFile("Comments on your report.mp3", MP3)
    added = teacher.post(url, {"file": recording}, format="multipart")
    assert added.status_code == 201, added.json()
    files = added.json()["feedback_files"]
    assert files[0]["is_audio"] is True and files[0]["kind"] == "mp3"
    disguised = SimpleUploadedFile("voice.mp3", b"<html></html>")
    assert teacher.post(url, {"file": disguised}, format="multipart").status_code == 400
    assert learner.post(url, {"file": SimpleUploadedFile("a.mp3", MP3)}, format="multipart").status_code == 403
    # The student hears it only once the mark is released.
    download = files[0]["download_url"]
    assert learner.get(download).status_code == 404
    assert learner.get(f"/api/v1/assignments/{assignment.id}/").json()["my_submission"]["feedback_files"] == []
    mark(teacher, first, "40", is_released=True)
    heard = learner.get(download)
    assert heard.status_code == 200 and "Comments on your report.mp3" in heard["Content-Disposition"]
    assert client_for(other_student.user).get(download).status_code == 404
    assert learner.delete(download).status_code == 403
    assert teacher.delete(download).status_code == 204
    assert teacher.get(download).status_code == 404
    assert AuditLog.objects.filter(action__in=["feedback_added", "feedback_removed"]).count() == 2


@pytest.mark.django_db
def test_download_everything_as_one_archive(site, assignment, student, other_student, lecturer, client_for):
    learner = client_for(student.user)
    hand_in(
        learner,
        assignment,
        text="Notes",
        files=[SimpleUploadedFile("report.pdf", b"%PDF-1.7 a"), SimpleUploadedFile("report.pdf", b"%PDF-1.7 b")],
    )
    hand_in(client_for(other_student.user), assignment, "", [SimpleUploadedFile("Plot 7.pdf", b"%PDF-1.7 c")])
    response = client_for(lecturer.user).get(f"/api/v1/assignments/{assignment.id}/download-all/")
    assert response.status_code == 200 and response["Content-Type"] == "application/zip"
    bundle = zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content)))
    assert sorted(bundle.namelist()) == [
        "26MRP0001/report (2).pdf",
        "26MRP0001/report.pdf",
        "26MRP0001/text.txt",
        "26MRP0002/Plot 7.pdf",
    ]
    assert bundle.read("26MRP0001/report (2).pdf") == b"%PDF-1.7 b"
    assert AuditLog.objects.get(action="downloaded_all").after == {"submissions": 2}
    assert learner.get(f"/api/v1/assignments/{assignment.id}/download-all/").status_code == 403


def csv_file(text: str):
    return SimpleUploadedFile("marks.csv", text.encode("utf-8"), content_type="text/csv")


@pytest.mark.django_db
def test_marks_from_a_spreadsheet_are_checked_then_applied(
    site, assignment, student, other_student, lecturer, client_for, make_person, both
):
    teacher = client_for(lecturer.user)
    url = f"/api/v1/assignments/{assignment.id}/marks-upload/"
    first, _ = both
    mark(teacher, first, "10")
    late_joiner = make_person("student", "26MRP0003", "Sita", "Ram", "student")
    Membership.objects.create(site=site, person=late_joiner, role="student")
    text = (
        "Student number,Mark,Feedback\n"
        "26MRP0001,41,Clear method\n"
        "26MRP0002,60,Too high\n"
        "26MRP0003,30,\n"
        "26MRP0009,30,\n"
        "26MRP0001,20,again\n"
        ",,\n"
    )
    checked = teacher.post(url, {"file": csv_file(text)}, format="multipart").json()
    outcomes = [(r["line"], r["outcome"]) for r in checked["rows"]]
    assert outcomes == [(2, "changed"), (3, "above_max"), (4, "no_submission"), (5, "unknown_student"), (6, "repeated")]
    assert checked["applied"] is False and checked["refused"] == 4 and Mark.objects.get().mark == 10
    refused = teacher.post(url, {"file": csv_file(text), "apply": True, "token": checked["token"]}, format="multipart")
    assert refused.status_code == 409 and refused.json()["code"] == "rows_refused"

    good = "student_no,mark,feedback\n26MRP0001,41,Clear method\n26MRP0002,=1+1,\n26MRP0002,abc,\n"
    checked = teacher.post(url, {"file": csv_file(good)}, format="multipart").json()
    assert [r["outcome"] for r in checked["rows"]] == ["changed", "not_a_number", "repeated"]
    good = "student_no,mark,feedback\n26MRP0001,41,Clear method\n26MRP0002,35.5,\n"
    checked = teacher.post(url, {"file": csv_file(good)}, format="multipart").json()
    assert checked["to_save"] == 2 and checked["refused"] == 0
    unchecked = teacher.post(url, {"file": csv_file(good + "\n"), "apply": True, "token": "x"}, format="multipart")
    assert unchecked.json()["code"] == "not_checked"
    applied = teacher.post(url, {"file": csv_file(good), "apply": True, "token": checked["token"]}, format="multipart")
    assert applied.json()["applied"] is True
    marks = {m.submission.student.external_id: (m.mark, m.source, m.is_released) for m in Mark.objects.all()}
    assert marks == {"26MRP0001": (41, "upload", False), "26MRP0002": (35.5, "upload", False)}
    assert AuditLog.objects.filter(action="marks_uploaded").count() == 1
    again = teacher.post(url, {"file": csv_file(good)}, format="multipart").json()
    assert {r["outcome"] for r in again["rows"]} == {"unchanged"}
    no_header = teacher.post(url, {"file": csv_file("1,2,3\n")}, format="multipart")
    assert no_header.status_code == 400
    assert teacher.post(url, {"file": csv_file("")}, format="multipart").status_code == 400


@pytest.mark.django_db
def test_a_group_mark_is_copied_to_each_member_with_adjustments(
    site, assignment, student, other_student, lecturer, client_for
):
    group = SiteGroup.objects.create(site=site, name="Team A")
    group.members.set(Membership.objects.filter(site=site, role="student"))
    Assignment.objects.filter(pk=assignment.pk).update(is_group=True)
    teacher = client_for(lecturer.user)
    url = f"/api/v1/assignments/{assignment.id}/group-mark/"
    assert teacher.post(url, {"group": group.id, "mark": "40"}, format="json").json()["code"] == "no_submission"
    hand_in(client_for(student.user), assignment)
    response = teacher.post(
        url,
        {"group": group.id, "mark": "40", "feedback": "Good teamwork", "adjustments": [
            {"student_no": "26MRP0002", "adjustment": "-5"}
        ]},
        format="json",
    )
    assert response.status_code == 200, response.json()
    got = {m.submission.student.external_id: (m.mark, m.group_mark, m.adjustment) for m in Mark.objects.all()}
    assert got == {"26MRP0001": (40, 40, 0), "26MRP0002": (35, 40, -5)}
    too_high = teacher.post(
        url,
        {"group": group.id, "mark": "48", "adjustments": [{"student_no": "26MRP0001", "adjustment": "5"}]},
        format="json",
    )
    assert too_high.status_code == 400 and too_high.json()["code"] == "above_max"
    stranger = teacher.post(
        url, {"group": group.id, "mark": "40", "adjustments": [{"student_no": "X", "adjustment": "1"}]}, format="json"
    )
    assert stranger.status_code == 400
    Assignment.objects.filter(pk=assignment.pk).update(is_group=False)
    assert teacher.post(url, {"group": group.id, "mark": "40"}, format="json").json()["code"] == "not_group"


@pytest.mark.django_db
def test_anonymous_marking_hides_names_until_release(
    site, assignment, student, other_student, lecturer, client_for, both
):
    Assignment.objects.filter(pk=assignment.pk).update(anonymous=True)
    teacher = client_for(lecturer.user)
    rows = teacher.get(f"/api/v1/assignments/{assignment.id}/submissions/").json()
    assert all(r["student_no"].startswith("Candidate ") and r["student_name"] == "" for r in rows)
    assert "26MRP" not in str(rows)
    book = teacher.get(f"/api/v1/sites/{site.id}/gradebook/").json()
    first, _ = both
    mark(teacher, first, "30")
    cell = next(r for r in teacher.get(f"/api/v1/sites/{site.id}/gradebook/").json()["rows"] if r["student_no"] == "26MRP0001")
    assert cell["marks"][str(assignment.id)]["mark"] is None and cell["marks"][str(assignment.id)]["anonymous"]
    assert book["rows"]
    # Spreadsheet marks are matched by pseudonym; the archive is filed by pseudonym.
    label = next(r["student_no"] for r in rows if r["id"] == first)
    text = f"candidate,mark\n{label},31\n26MRP0002,20\n"
    checked = teacher.post(
        f"/api/v1/assignments/{assignment.id}/marks-upload/", {"file": csv_file(text)}, format="multipart"
    ).json()
    assert [r["outcome"] for r in checked["rows"]] == ["changed", "unknown_student"]
    archive = teacher.get(f"/api/v1/assignments/{assignment.id}/download-all/")
    names = zipfile.ZipFile(io.BytesIO(b"".join(archive.streaming_content))).namelist()
    assert all(n.startswith("Candidate ") for n in names)
    # The student still sees their own work under their own number.
    own = client_for(student.user).get(f"/api/v1/assignments/{assignment.id}/").json()["my_submission"]
    assert own["student_no"] == "26MRP0001"
    teacher.post(f"/api/v1/assignments/{assignment.id}/release/")
    rows = teacher.get(f"/api/v1/assignments/{assignment.id}/submissions/").json()
    assert {r["student_no"] for r in rows} == {"26MRP0001", "26MRP0002"}


@pytest.mark.django_db
def test_double_marking_holds_release_until_agreed(
    site, assignment, student, lecturer, second_marker, client_for, both
):
    Assignment.objects.filter(pk=assignment.pk).update(moderation="double")
    first_marker, other = client_for(lecturer.user), client_for(second_marker.user)
    first, second = both
    assert other.post(f"/api/v1/submissions/{first}/second-mark/", {"mark": "30"}, format="json").json()["code"] == (
        "not_marked"
    )
    held = mark(first_marker, first, "30", is_released=True)
    assert held.status_code == 409 and held.json()["code"] == "moderation_outstanding"
    mark(first_marker, first, "30")
    same = first_marker.post(f"/api/v1/submissions/{first}/second-mark/", {"mark": "34"}, format="json")
    assert same.json()["code"] == "same_marker"
    assert other.post(f"/api/v1/submissions/{first}/agree/", {"mark": "32"}, format="json").json()["code"] == (
        "no_second_mark"
    )
    assert other.post(f"/api/v1/submissions/{first}/second-mark/", {"mark": "99"}, format="json").status_code == 400
    moderated = other.post(f"/api/v1/submissions/{first}/second-mark/", {"mark": "36", "note": "Generous"}, format="json")
    assert moderated.json()["first_mark"] == "30.00" and moderated.json()["second_mark"] == "36.00"
    assert first_marker.post(f"/api/v1/assignments/{assignment.id}/release/").json()["code"] == "moderation_outstanding"
    agreed = first_marker.post(f"/api/v1/submissions/{first}/agree/", {"mark": "33", "note": "Met"}, format="json")
    assert agreed.status_code == 200 and agreed.json()["mark"]["mark"] == "33.00"
    assert agreed.json()["mark"]["source"] == "agreed"
    assert other.post(f"/api/v1/submissions/{first}/second-mark/", {"mark": "30"}, format="json").json()["code"] == "agreed"
    history = first_marker.get(f"/api/v1/submissions/{first}/history/").json()
    assert history["moderation"]["first_mark"] == "30.00" and history["moderation"]["agreed_mark"] == "33.00"
    # The second submission is not marked yet, so release of the agreed one goes ahead.
    assert first_marker.post(f"/api/v1/assignments/{assignment.id}/release/").json() == {"released": 1}
    assert second


@pytest.mark.django_db
def test_a_sample_is_second_marked(site, assignment, lecturer, second_marker, client_for, both):
    teacher, other = client_for(lecturer.user), client_for(second_marker.user)
    url = f"/api/v1/assignments/{assignment.id}/moderation-sample/"
    assert teacher.post(url, {"percent": 50}, format="json").json()["code"] == "not_sampled"
    Assignment.objects.filter(pk=assignment.pk).update(moderation="sample")
    first, second = both
    mark(teacher, first, "30")
    mark(teacher, second, "40")
    sampled = teacher.post(url, {"percent": 50}, format="json").json()["sampled"]
    assert len(sampled) == 1
    outside = first if sampled[0] == second else second
    assert other.post(f"/api/v1/submissions/{outside}/second-mark/", {"mark": "30"}, format="json").json()["code"] == (
        "not_sampled"
    )
    assert teacher.post(f"/api/v1/assignments/{assignment.id}/release/").status_code == 409
    other.post(f"/api/v1/submissions/{sampled[0]}/second-mark/", {"mark": "35"}, format="json")
    teacher.post(f"/api/v1/submissions/{sampled[0]}/agree/", {"mark": "35"}, format="json")
    assert teacher.post(f"/api/v1/assignments/{assignment.id}/release/").json() == {"released": 2}
    assert AuditLog.objects.filter(action__in=["moderation_sampled", "second_marked", "mark_agreed"]).count() == 3


@pytest.mark.django_db
def test_marks_sent_to_the_srms_are_locked(site, assignment, student, lecturer, client_for, both):
    teacher = client_for(lecturer.user)
    first, second = both
    mark(teacher, first, "30", is_released=True)
    SrmsTransfer.objects.create(
        site=site, student=student, percent="60.00", outcome="accepted", sent_at=timezone.now() - timedelta(days=1)
    )
    changed = mark(teacher, first, "35")
    assert changed.status_code == 409 and changed.json()["code"] == "locked_in_srms"
    assert "SRMS correction process" in changed.json()["detail"]
    assert Submission.objects.get(pk=first).mark.mark == 30
    feedback = teacher.post(
        f"/api/v1/submissions/{first}/feedback-files/", {"file": SimpleUploadedFile("a.mp3", MP3)}, format="multipart"
    )
    assert feedback.json()["code"] == "locked_in_srms"
    checked = teacher.post(
        f"/api/v1/assignments/{assignment.id}/marks-upload/",
        {"file": csv_file("student_no,mark\n26MRP0001,20\n26MRP0002,20\n")},
        format="multipart",
    ).json()
    assert [r["outcome"] for r in checked["rows"]] == ["locked_in_srms", "new"]
    # The other student's mark is not locked.
    assert mark(teacher, second, "20").status_code == 200
