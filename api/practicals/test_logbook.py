"""The practical logbook (item 3.14) and the student's portfolio export (item 5.15)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from audit.models import AuditLog
from courses.models import CourseSite, Membership
from notifications.models import Notification
from practicals.conftest import now_iso, photo, today_iso
from practicals.models import CompetencyResult, LogbookEntry


def entry_body(site, **extra):
    return {
        "site": site.id,
        "work_date": timezone.localdate().isoformat(),
        "unit_type": "livestock_unit",
        "unit_text": "Pen 3, broilers",
        "task": "Cleaned drinkers and weighed a sample of birds",
        "hours": "3.5",
        "notes": "Average weight 1.4 kg.",
        "latitude": "6.80",
        "longitude": "-58.15",
        "client_recorded_at": now_iso(minutes=-30),
        **extra,
    }


@pytest.mark.django_db
def test_a_student_keeps_a_logbook_and_a_signed_entry_is_locked(site, student, lecturer, client_for):
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    made = learner.post(
        "/api/v1/logbook/", {**entry_body(site), "photos": [photo("pen.jpg")]}, format="multipart"
    )
    assert made.status_code == 201, made.json()
    entry = made.json()
    assert entry["status"] == "pending" and entry["student_no"] == "26MRP0001"
    assert entry["photo_files"][0]["filename"] == "pen.jpg"
    url = f"/api/v1/logbook/{entry['id']}/"

    # Returning needs a comment; the student corrects it and it waits for sign-off again.
    assert teacher.post(f"{url}review/", {"decision": "return"}, format="json").json()["comment"] == [
        "Say what needs correcting."
    ]
    returned = teacher.post(
        f"{url}review/", {"decision": "return", "comment": "Give the sample size."}, format="json"
    )
    assert returned.json()["status"] == "returned"
    assert Notification.objects.filter(recipient=student.user, title__startswith="Logbook returned").exists()
    corrected = learner.patch(url, {"notes": "Average weight 1.4 kg over 20 birds."}, format="json")
    assert corrected.status_code == 200 and corrected.json()["status"] == "pending"
    # Teaching staff do not write in a student's logbook.
    assert teacher.patch(url, {"notes": "x"}, format="json").status_code == 403

    signed = teacher.post(f"{url}review/", {"decision": "sign", "comment": "Good."}, format="json")
    assert signed.status_code == 200 and signed.json()["supervisor_name"] == "Asha Persaud"
    for attempt in (
        learner.patch(url, {"notes": "changed"}, format="json"),
        learner.delete(url),
        learner.post(f"{url}photos/", {"photos": [photo()]}, format="multipart"),
        teacher.post(f"{url}review/", {"decision": "return", "comment": "x"}, format="json"),
    ):
        assert attempt.status_code == 409 and attempt.json()["code"] == "locked"
    assert LogbookEntry.objects.get().notes == "Average weight 1.4 kg over 20 birds."
    assert {"create", "return", "update", "sign"} <= set(
        AuditLog.objects.filter(entity="practicals.logbookentry").values_list("action", flat=True)
    )


@pytest.mark.django_db
def test_logbook_refusals(site, student, other_student, lecturer, client_for):
    learner = client_for(student.user)
    too_long = learner.post("/api/v1/logbook/", entry_body(site, hours="25"), format="json")
    assert "at most 24" in too_long.json()["hours"][0]
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    assert (
        "future"
        in learner.post("/api/v1/logbook/", entry_body(site, work_date=tomorrow), format="json").json()[
            "work_date"
        ][0]
    )
    # Teaching staff do not keep a logbook on their own course; a site one cannot open is unknown.
    assert (
        client_for(lecturer.user).post("/api/v1/logbook/", entry_body(site), format="json").status_code == 403
    )
    hidden = CourseSite.objects.create(code="FOR201", title="Forestry", is_published=True)
    unknown = learner.post("/api/v1/logbook/", entry_body(hidden), format="json")
    assert unknown.status_code == 400 and "does not exist" in unknown.json()["site"][0]

    made = learner.post("/api/v1/logbook/", entry_body(site), format="json").json()
    # Another student cannot see, change or sign it.
    other = client_for(other_student.user)
    assert other.get(f"/api/v1/logbook/{made['id']}/").status_code == 404
    assert (
        other.post(f"/api/v1/logbook/{made['id']}/review/", {"decision": "sign"}, format="json").status_code
        == 404
    )
    assert (
        learner.post(f"/api/v1/logbook/{made['id']}/review/", {"decision": "sign"}, format="json").status_code
        == 403
    )
    assert learner.delete(f"/api/v1/logbook/{made['id']}/").status_code == 204


@pytest.mark.django_db
def test_hours_are_totalled_by_kind_of_place(site, student, other_student, lecturer, client_for):
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    ids = [
        learner.post("/api/v1/logbook/", entry_body(site, unit_type=kind, hours=hours), format="json").json()[
            "id"
        ]
        for kind, hours in (("livestock_unit", "3.5"), ("livestock_unit", "2"), ("pond", "1.25"))
    ]
    teacher.post(f"/api/v1/logbook/{ids[0]}/review/", {"decision": "sign"}, format="json")
    own = learner.get(f"/api/v1/sites/{site.id}/logbook-totals/").json()["rows"]
    assert len(own) == 1
    assert own[0]["hours"] == [
        {
            "unit_type": "livestock_unit",
            "label": "Livestock unit",
            "signed_hours": "3.50",
            "waiting_hours": "2.00",
        },
        {"unit_type": "pond", "label": "Fish pond", "signed_hours": "0.00", "waiting_hours": "1.25"},
    ]
    everyone = teacher.get(f"/api/v1/sites/{site.id}/logbook-totals/").json()["rows"]
    assert {r["student_no"] for r in everyone} == {"26MRP0001", "26MRP0002"}


@pytest.mark.django_db
def test_the_portfolio_holds_only_what_is_signed_off_or_released(
    site, task, passing, mapped, student, other_student, lecturer, client_for, observe, make_person
):
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    signed = learner.post(
        "/api/v1/logbook/", entry_body(site, task="<script>alert(1)</script> weighed birds"), format="json"
    ).json()
    learner.post("/api/v1/logbook/", entry_body(site, task="Still waiting"), format="json")
    teacher.post(f"/api/v1/logbook/{signed['id']}/review/", {"decision": "sign"}, format="json")
    released = observe(task, student, passing).json()
    teacher.post(f"/api/v1/observations/{released['id']}/release/")
    observe(task, student, passing)  # a second attempt, not released
    CompetencyResult.objects.create(
        site=site,
        student=student,
        unit=mapped,
        status="competent",
        assessor=lecturer,
        decided_on=timezone.localdate(),
    )

    data = learner.get("/api/v1/portfolio/").json()
    assert data["student"]["student_no"] == "26MRP0001" and len(data["sites"]) == 1
    block = data["sites"][0]
    assert [e["task"] for e in block["logbook"]] == ["<script>alert(1)</script> weighed birds"]
    assert block["logbook"][0]["signed_by"] == "Asha Persaud"
    assert [o["attempt"] for o in block["observations"]] == [1]
    assert block["competencies"][0]["status"] == "Competent"
    assert block["competencies"][0]["source"] == "Council for TVET occupational standard"

    page = learner.get("/api/v1/portfolio/?as=html")
    assert page.status_code == 200 and page["Content-Type"].startswith("text/html")
    html = page.content.decode()
    assert "&lt;script&gt;" in html and "<script>" not in html and "Still waiting" not in html

    # Teaching staff export their students' portfolios; anyone else's request reads as unknown.
    staff = teacher.get(f"/api/v1/portfolio/?student={student.id}&site={site.id}")
    assert staff.status_code == 200 and staff.json()["sites"][0]["site"]["code"] == site.code
    assert learner.get(f"/api/v1/portfolio/?student={other_student.id}").status_code == 404
    elsewhere = make_person("staff", "E0002", "Bibi", "Khan", "lecturer")
    assert client_for(elsewhere.user).get(f"/api/v1/portfolio/?student={student.id}").status_code == 404
    assert AuditLog.objects.filter(action="export").count() == 3

    # The portfolio is kept after the course ends: a membership no longer active still exports.
    Membership.objects.filter(person=student).update(is_active=False)
    assert len(learner.get("/api/v1/portfolio/").json()["sites"]) == 1


@pytest.mark.django_db
def test_a_sign_off_from_the_phone_keeps_the_phones_time(site, student, lecturer, client_for):
    """The web app sends the phone's time with every decision; it is kept in the audit log as text."""
    from datetime import datetime

    made = (
        client_for(student.user)
        .post(
            "/api/v1/logbook/",
            {
                "site": site.id,
                "work_date": today_iso(),
                "unit_type": "pond",
                "task": "Fed fingerlings",
                "hours": "1.5",
                "client_recorded_at": now_iso(minutes=-30),
            },
            format="json",
        )
        .json()
    )
    at = now_iso(minutes=-1)
    signed = client_for(lecturer.user).post(
        f"/api/v1/logbook/{made['id']}/review/",
        {"decision": "sign", "client_recorded_at": at},
        format="json",
    )
    assert signed.status_code == 200 and signed.json()["status"] == "signed"
    kept = AuditLog.objects.get(entity="practicals.logbookentry", action="sign").after["client_recorded_at"]
    assert datetime.fromisoformat(kept) == datetime.fromisoformat(at)
