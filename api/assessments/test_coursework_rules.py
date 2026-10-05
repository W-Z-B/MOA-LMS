"""Due dates for each student: extensions (2.26) and accommodations (3.23); late penalties (2.35); gradebook
categories (2.28), the export (2.29), the working (2.30) and sending coursework to the SRMS (2.31)."""

import csv
import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from assessments.models import (
    Accommodation,
    Assignment,
    Extension,
    Mark,
    SrmsTransfer,
    Submission,
)
from assessments.rules import due_for, penalty_percent
from assessments.services import coursework_percent, coursework_working
from audit.models import AuditLog
from courses.models import Membership, SiteGroup


def handed(assignment, person, at, mark=None, released=False):
    submission = Submission.objects.create(assignment=assignment, student=person, text="x", submitted_at=at)
    if mark is not None:
        Mark.objects.create(submission=submission, mark=mark, is_released=released)
    return submission


@pytest.mark.django_db
def test_extensions_for_a_student_or_a_group(site, assignment, student, other_student, lecturer, client_for):
    teacher = client_for(lecturer.user)
    Assignment.objects.filter(pk=assignment.pk).update(
        due_at=timezone.now() - timedelta(hours=2), allow_late=False
    )
    assignment.refresh_from_db()
    learner = client_for(student.user)
    closed = learner.post(f"/api/v1/assignments/{assignment.id}/submit/", {"text": "x"}, format="json")
    assert closed.json()["code"] == "closed"
    later = (timezone.now() + timedelta(days=2)).isoformat()
    refused = teacher.post(
        "/api/v1/extensions/", {"assignment": assignment.id, "due_at": later, "reason": ""}, format="json"
    )
    assert refused.status_code == 400
    granted = teacher.post(
        "/api/v1/extensions/",
        {"assignment": assignment.id, "student": student.id, "due_at": later, "reason": "Flooding at home"},
        format="json",
    )
    assert granted.status_code == 201, granted.json()
    assert AuditLog.objects.get(entity="assessments.extension").reason == "Flooding at home"
    assert learner.get(f"/api/v1/assignments/{assignment.id}/").json()["my_due_at"].startswith(later[:16])
    handed_in = learner.post(f"/api/v1/assignments/{assignment.id}/submit/", {"text": "x"}, format="json")
    assert (
        handed_in.status_code == 201 and handed_in.json()["is_late"] is False and handed_in.json()["extended"]
    )
    # The other student, without an extension, is missing work that counts as zero; the first is not.
    assert coursework_percent(site, other_student) == Decimal("0.00")
    duplicate = teacher.post(
        "/api/v1/extensions/",
        {"assignment": assignment.id, "student": student.id, "due_at": later, "reason": "Again"},
        format="json",
    )
    assert duplicate.status_code == 400
    early = teacher.post(
        "/api/v1/extensions/",
        {
            "assignment": assignment.id,
            "student": other_student.id,
            "due_at": (timezone.now() - timedelta(hours=3)).isoformat(),
            "reason": "x",
        },
        format="json",
    )
    assert early.status_code == 400 and "due_at" in early.json()

    group = SiteGroup.objects.create(site=site, name="Team B")
    group.members.set(Membership.objects.filter(person=other_student))
    by_group = teacher.post(
        "/api/v1/extensions/",
        {"assignment": assignment.id, "group": group.id, "due_at": later, "reason": "Field trip"},
        format="json",
    )
    assert by_group.status_code == 201
    assert due_for(assignment, other_student).extended is True
    assert coursework_percent(site, other_student) is None  # no longer overdue
    both = teacher.post(
        "/api/v1/extensions/",
        {
            "assignment": assignment.id,
            "group": group.id,
            "student": student.id,
            "due_at": later,
            "reason": "x",
        },
        format="json",
    )
    assert both.status_code == 400
    listed = teacher.get(f"/api/v1/extensions/?assignment={assignment.id}").json()
    assert listed["count"] == 2
    assert client_for(student.user).get("/api/v1/extensions/").json()["results"] == []
    moved = teacher.patch(
        f"/api/v1/extensions/{granted.json()['id']}/", {"reason": "Flooding, confirmed"}, format="json"
    )
    assert moved.status_code == 200


@pytest.mark.django_db
def test_accommodations_apply_everywhere_and_stay_private(
    site, assignment, student, lecturer, course_admin, client_for
):
    admin, teacher = client_for(course_admin), client_for(lecturer.user)
    assert teacher.post("/api/v1/accommodations/", {"person": student.id}, format="json").status_code == 403
    created = admin.post(
        "/api/v1/accommodations/",
        {
            "person": student.id,
            "extra_time_percent": 25,
            "extra_days": 3,
            "reason": "Dyslexia assessment 2025",
        },
        format="json",
    )
    assert created.status_code == 201, created.json()
    assert (
        admin.post(
            "/api/v1/accommodations/", {"person": student.id, "extra_time_percent": 400}, format="json"
        ).status_code
        == 400
    )
    assert admin.post("/api/v1/accommodations/", {"person": lecturer.id}, format="json").status_code == 400
    entry = AuditLog.objects.get(entity="assessments.accommodation")
    assert "Dyslexia" not in str(entry.after)
    assert due_for(assignment, student).at == assignment.due_at + timedelta(days=3)

    handed_in = client_for(student.user).post(
        f"/api/v1/assignments/{assignment.id}/submit/", {"text": "x"}, format="json"
    )
    row = teacher.get(f"/api/v1/assignments/{assignment.id}/submissions/").json()[0]
    assert row["accommodation_applies"] is True and "Dyslexia" not in str(row)
    assert handed_in.json()["accommodation_applies"] is None  # the student's own view does not need it

    # Every quiz time limit grows by the percentage.
    from quizzes.models import Quiz
    from quizzes.services import effective

    quiz = Quiz.objects.create(site=site, title="Test 1", time_limit_minutes=30, is_published=True)
    assert effective(quiz, student).time_limit_minutes == 38  # 37.5 rounded up
    pk = created.json()["id"]
    assert (
        admin.patch(f"/api/v1/accommodations/{pk}/", {"is_active": False}, format="json").status_code == 200
    )
    assert effective(quiz, student).time_limit_minutes == 30
    assert admin.delete(f"/api/v1/accommodations/{pk}/").status_code == 204
    assert not Accommodation.objects.exists()


@pytest.mark.django_db
def test_late_penalties_are_applied_and_shown(site, assignment, student, lecturer, client_for):
    due = assignment.due_at
    assert penalty_percent(assignment, due + timedelta(days=3), due) == 0  # no rule
    Assignment.objects.filter(pk=assignment.pk).update(
        late_penalty="per_day", late_penalty_percent=5, late_penalty_cap=12
    )
    assignment.refresh_from_db()
    assert penalty_percent(assignment, due - timedelta(hours=1), due) == 0
    assert penalty_percent(assignment, due + timedelta(hours=1), due) == 5  # a part of a day counts as a day
    assert penalty_percent(assignment, due + timedelta(days=1, minutes=1), due) == 10
    assert penalty_percent(assignment, due + timedelta(days=9), due) == 12  # the cap
    assignment.late_penalty, assignment.late_penalty_cap = "per_hour", None
    assert penalty_percent(assignment, due + timedelta(hours=30), due) == 100

    submission = handed(assignment, student, due + timedelta(hours=26), mark=40, released=True)
    Submission.objects.filter(pk=submission.pk).update(is_late=True)
    # 2 days late: 10% of 50 = 5 marks: 40 becomes 35, 70% of the assignment.
    assert coursework_percent(site, student) == Decimal("70.00")
    shown = (
        client_for(student.user).get(f"/api/v1/assignments/{assignment.id}/").json()["my_submission"]["mark"]
    )
    assert (shown["raw_mark"], shown["penalty"], shown["mark"], shown["penalty_percent"]) == (
        "40.00",
        "5.00",
        "35.00",
        "10.00",
    )
    rows = client_for(lecturer.user).get(f"/api/v1/sites/{site.id}/gradebook/").json()["rows"]
    cell = next(r for r in rows if r["student_no"] == student.external_id)["marks"]
    assert cell[str(assignment.id)]["penalty"] == "5.00"
    # The penalty never takes a mark below zero.
    Mark.objects.filter(submission=submission).update(mark=2)
    assert coursework_percent(site, student) == Decimal("0.00")


@pytest.mark.django_db
def test_categories_weight_the_parts_and_drop_the_lowest(site, assignment, student, lecturer, client_for):
    now = timezone.now()
    past = now - timedelta(days=1)
    teacher = client_for(lecturer.user)
    tests = teacher.post(
        "/api/v1/grade-categories/",
        {"site": site.id, "name": "Tests", "weight": "60", "drop_lowest": 1},
        format="json",
    ).json()
    reports = teacher.post(
        "/api/v1/grade-categories/", {"site": site.id, "name": "Reports", "weight": "40"}, format="json"
    ).json()
    duplicate = teacher.post(
        "/api/v1/grade-categories/", {"site": site.id, "name": "Tests", "weight": "1"}, format="json"
    )
    assert duplicate.status_code == 400
    assert (
        client_for(student.user)
        .post("/api/v1/grade-categories/", {"site": site.id, "name": "Mine", "weight": "1"}, format="json")
        .status_code
        == 403
    )
    t1 = Assignment.objects.create(
        site=site, title="Test 1", due_at=past, max_mark=10, is_published=True, category_id=tests["id"]
    )
    t2 = Assignment.objects.create(
        site=site, title="Test 2", due_at=past, max_mark=10, is_published=True, category_id=tests["id"]
    )
    t3 = Assignment.objects.create(
        site=site, title="Test 3", due_at=past, max_mark=10, is_published=True, category_id=tests["id"]
    )
    Assignment.objects.filter(pk=assignment.pk).update(category_id=reports["id"])
    handed(t1, student, past, mark=8)
    handed(t2, student, past, mark=6)  # t3 missing: zero, and dropped as the lowest
    handed(assignment, student, past, mark=25)
    # Tests: (0.8 + 0.6) / 2 = 70%; Reports: 50%. 0.6 * 70 + 0.4 * 50 = 62.
    assert coursework_percent(site, student) == Decimal("62.00")
    working = coursework_working(site, student)
    states = {i["title"]: i["state"] for i in working["items"]}
    assert states == {
        "Test 1": "graded",
        "Test 2": "graded",
        "Test 3": "dropped",
        "Soil sampling report": "graded",
    }
    assert [c["percent"] for c in working["categories"]] == ["70.00", "50.00"]

    # An item in no category counts as one more category weighted by its own weight.
    Assignment.objects.create(
        site=site, title="Field notes", due_at=past, max_mark=10, weight=100, is_published=True
    )
    # (60 * 0.7 + 40 * 0.5 + 100 * 0) / 200 = 31%
    assert coursework_percent(site, student) == Decimal("31.00")
    assert coursework_working(site, student)["categories"][-1]["name"] == "Not in a category"
    t3.delete()
    assert (
        teacher.patch(
            f"/api/v1/grade-categories/{tests['id']}/", {"drop_lowest": 0}, format="json"
        ).status_code
        == 200
    )
    assert teacher.get(f"/api/v1/grade-categories/?site={site.id}").json()["results"][0]["name"] == "Tests"
    book = teacher.get(f"/api/v1/sites/{site.id}/gradebook/").json()
    assert [c["name"] for c in book["categories"]] == ["Tests", "Reports"]
    row = next(r for r in book["rows"] if r["student_no"] == student.external_id)
    assert row["categories"][str(tests["id"])] == "70.00"


@pytest.mark.django_db
def test_the_working_for_the_student_and_for_staff(
    site, assignment, student, other_student, lecturer, client_for
):
    past = timezone.now() - timedelta(days=1)
    missed = Assignment.objects.create(site=site, title="Quiz 0", due_at=past, max_mark=10, is_published=True)
    handed(assignment, student, past, mark=40, released=False)
    own = client_for(student.user).get(f"/api/v1/sites/{site.id}/coursework/working/").json()
    states = {i["title"]: i["state"] for i in own["items"]}
    assert states == {"Quiz 0": "zero", "Soil sampling report": "pending"}  # the mark is not released yet
    assert own["coursework_percent"] == "0.00" and own["student_no"] == "26MRP0001"
    teacher = client_for(lecturer.user)
    staff = teacher.get(f"/api/v1/sites/{site.id}/coursework/working/?person={student.id}").json()
    assert {i["title"]: i["state"] for i in staff["items"]}["Soil sampling report"] == "graded"
    assert teacher.get(f"/api/v1/sites/{site.id}/coursework/working/?person={lecturer.id}").status_code == 404
    assert teacher.get(f"/api/v1/sites/{site.id}/coursework/working/").status_code == 404
    assert missed


@pytest.mark.django_db
def test_the_gradebook_export_is_spreadsheet_safe(
    site, assignment, student, other_student, lecturer, client_for
):
    past = timezone.now() - timedelta(days=1)
    Assignment.objects.create(site=site, title="=HYPERLINK(1)", due_at=past, max_mark=10, is_published=True)
    handed(assignment, student, past, mark=40)
    response = client_for(lecturer.user).get(f"/api/v1/sites/{site.id}/gradebook/export/")
    assert response.status_code == 200 and "gradebook" in response["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(b"".join(response.streaming_content).decode("utf-8-sig"))))
    assert rows[0][2].startswith("'=HYPERLINK") and rows[0][-2:] == ["Coursework (%)", "Working"]
    ravi = next(r for r in rows if r[0] == "26MRP0001")
    assert ravi[2] == "missing, counted as 0" and ravi[3] == "40.00" and ravi[-2] == "53.33"
    assert "Soil sampling report: counted 80.00%" in ravi[-1]
    assert AuditLog.objects.filter(action="gradebook_exported").exists()
    assert client_for(student.user).get(f"/api/v1/sites/{site.id}/gradebook/export/").status_code == 403


@pytest.fixture
def srms(settings, monkeypatch):
    from integration import srms

    settings.SRMS_API_URL, settings.SRMS_API_KEY = "http://srms-api:8000", "k"
    state = {"locked": [], "fail": False}

    def fake_call(base, key, path, params=None, data=None):
        from integration.client import IntegrationError

        if state["fail"]:
            raise IntegrationError("http://srms-api:8000 could not be reached")
        numbers = [m["student_no"] for m in data["marks"]]
        return {
            "offering_code": data["offering_code"],
            "accepted": [n for n in numbers if n not in state["locked"]],
            "locked": [n for n in numbers if n in state["locked"]],
            "unknown": [],
        }

    monkeypatch.setattr(srms, "call", fake_call)
    return state


@pytest.mark.django_db
def test_the_lecturer_sends_coursework_to_the_srms(
    site, assignment, student, other_student, lecturer, client_for, srms
):
    past = timezone.now() - timedelta(days=1)
    Assignment.objects.filter(pk=assignment.pk).update(due_at=past)
    first = handed(assignment, student, past, mark=40)
    srms["locked"] = ["26MRP0002"]
    teacher = client_for(lecturer.user)
    assert client_for(student.user).post(f"/api/v1/sites/{site.id}/coursework/send/").status_code == 403
    sent = teacher.post(f"/api/v1/sites/{site.id}/coursework/send/")
    assert sent.status_code == 200, sent.json()
    body = sent.json()
    assert body["accepted"] == ["26MRP0001"] and body["locked"] == ["26MRP0002"]
    assert {(s["student_no"], s["percent"], s["outcome"]) for s in body["students"]} == {
        ("26MRP0001", "80.00", "accepted"),
        ("26MRP0002", "0.00", "locked"),
    }
    assert SrmsTransfer.objects.count() == 2 and AuditLog.objects.filter(action="coursework_sent").exists()
    refused = teacher.post(f"/api/v1/submissions/{first.id}/mark/", {"mark": "45"}, format="json")
    assert refused.json()["code"] == "locked_in_srms"
    srms["fail"] = True
    assert teacher.post(f"/api/v1/sites/{site.id}/coursework/send/").json()["code"] == "srms_unavailable"
    from courses.models import CourseSite

    CourseSite.objects.filter(pk=site.pk).update(source="local")
    assert teacher.post(f"/api/v1/sites/{site.id}/coursework/send/").json()["code"] == "not_srms"


@pytest.mark.django_db
def test_extensions_reach_the_late_flag_of_each_group_member(
    site, assignment, student, other_student, client_for
):
    group = SiteGroup.objects.create(site=site, name="Team A")
    group.members.set(Membership.objects.filter(site=site, role="student"))
    Assignment.objects.filter(pk=assignment.pk).update(
        is_group=True, due_at=timezone.now() - timedelta(hours=1)
    )
    Extension.objects.create(
        assignment=assignment, student=other_student, due_at=timezone.now() + timedelta(days=1), reason="Ill"
    )
    client_for(student.user).post(
        f"/api/v1/assignments/{assignment.id}/submit/", {"text": "x"}, format="json"
    )
    late = dict(Submission.objects.values_list("student__external_id", "is_late"))
    assert late == {"26MRP0001": True, "26MRP0002": False}
