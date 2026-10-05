"""Class sessions and attendance (items 4.14 and 4.15, decision D6): sessions with meeting links, the
register on a phone and offline, check-in with the rotating code, totals, and sending them to the SRMS."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from attendance import codes
from attendance.models import AttendancePolicy, AttendanceRecord, ClassSession
from audit.models import AuditLog


@pytest.fixture
def teacher(client_for, lecturer):
    return client_for(lecturer.user)


@pytest.fixture
def learner(client_for, student):
    return client_for(student.user)


@pytest.fixture
def make_session(site):
    def _make(minutes_from_now=0, length=60, **fields):
        starts = timezone.now() + timedelta(minutes=minutes_from_now)
        return ClassSession.objects.create(
            site=site,
            title=fields.pop("title", "Soil science lecture"),
            starts_at=starts,
            ends_at=starts + timedelta(minutes=length),
            **fields,
        )

    return _make


def iso(**delta) -> str:
    return (timezone.now() + timedelta(**delta)).isoformat()


@pytest.mark.django_db
def test_teaching_staff_put_classes_on_a_site_with_a_secure_meeting_link(site, teacher, learner):
    body = {
        "site": site.id,
        "title": "Irrigation (online)",
        "starts_at": iso(days=1),
        "ends_at": iso(days=1, hours=1),
        "meeting_url": "http://meet.example.org/agr101",
    }
    insecure = teacher.post("/api/v1/class-sessions/", body, format="json")
    assert insecure.status_code == 400 and "meeting_url" in insecure.json()
    backwards = teacher.post(
        "/api/v1/class-sessions/", {**body, "meeting_url": "", "ends_at": iso(hours=1)}, format="json"
    )
    assert backwards.status_code == 400 and "ends_at" in backwards.json()
    made = teacher.post(
        "/api/v1/class-sessions/", {**body, "meeting_url": "https://meet.example.org/agr101"}, format="json"
    )
    assert made.status_code == 201
    session = made.json()
    assert learner.post("/api/v1/class-sessions/", body, format="json").status_code == 403
    recorded = teacher.patch(
        f"/api/v1/class-sessions/{session['id']}/",
        {"recording_url": "https://video.example.org/rec/1"},
        format="json",
    )
    assert recorded.json()["recording_url"] == "https://video.example.org/rec/1"
    assert AuditLog.objects.filter(entity="attendance.classsession").count() == 2
    assert [s["id"] for s in learner.get(f"/api/v1/class-sessions/?site={site.id}").json()["results"]] == [
        session["id"]
    ]
    assert learner.get("/api/v1/class-sessions/", {"to": iso(hours=1)}).json()["results"] == []
    assert learner.get("/api/v1/class-sessions/", {"to": "soon"}).status_code == 400
    assert len(learner.get("/api/v1/class-sessions/", {"from": iso(hours=2)}).json()["results"]) == 1


@pytest.mark.django_db
def test_a_group_session_is_seen_only_by_the_group(
    site, make_session, learner, client_for, other_student, student
):
    from courses.models import Membership, SiteGroup

    group = SiteGroup.objects.create(site=site, name="Lab group A")
    group.members.add(Membership.objects.get(site=site, person=student))
    lab = make_session(title="Lab A practical", group=group)
    other = client_for(other_student.user)
    assert other.get("/api/v1/class-sessions/").json()["results"] == []
    assert other.get(f"/api/v1/class-sessions/{lab.id}/").status_code == 404
    assert learner.get(f"/api/v1/class-sessions/{lab.id}/").status_code == 200


@pytest.mark.django_db
def test_students_check_in_with_the_code_in_the_room_once(make_session, teacher, learner, student, settings):
    session = make_session(minutes_from_now=-5)
    shown = teacher.get(f"/api/v1/class-sessions/{session.id}/check-in-code/").json()
    assert shown["valid_seconds"] == 60
    assert learner.get(f"/api/v1/class-sessions/{session.id}/check-in-code/").status_code == 403
    url = f"/api/v1/class-sessions/{session.id}/check-in/"

    wrong = learner.post(url, {"code": shown["code"][:-1] + "0"}, format="json")
    assert wrong.status_code == 400 and wrong.json()["code"] == "code_invalid"
    assert learner.post(url, {"code": "nonsense"}, format="json").json()["code"] == "code_invalid"
    expired, _ = codes.make(session.id, now=timezone.now().timestamp() - 61)
    old = learner.post(url, {"code": expired}, format="json")
    assert old.status_code == 400 and old.json()["code"] == "code_expired"
    future, _ = codes.make(session.id, now=timezone.now().timestamp() + 30)
    assert learner.post(url, {"code": future}, format="json").json()["code"] == "code_invalid"
    another = make_session(title="Another class")
    elsewhere, _ = codes.make(another.id)
    assert learner.post(url, {"code": elsewhere}, format="json").json()["code"] == "code_invalid"

    done = learner.post(url, {"code": shown["code"]}, format="json")
    assert done.status_code == 201 and done.json()["status"] == "present"
    twice = learner.post(url, {"code": shown["code"]}, format="json")
    assert twice.status_code == 409 and twice.json()["code"] == "already_recorded"
    record = AttendanceRecord.objects.get(student=student)
    assert record.how == "check_in"
    assert AuditLog.objects.filter(entity="attendance.attendancerecord", subject=student.id).exists()
    assert teacher.post(url, {"code": shown["code"]}, format="json").status_code == 403
    assert learner.get(f"/api/v1/class-sessions/{session.id}/").json()["my_status"] == "present"


@pytest.mark.django_db
def test_a_late_check_in_is_late_and_check_in_opens_only_around_the_class(make_session, teacher, learner):
    late = make_session(minutes_from_now=-20)
    code, _ = codes.make(late.id)
    assert (
        learner.post(f"/api/v1/class-sessions/{late.id}/check-in/", {"code": code}, format="json").json()[
            "status"
        ]
        == "late"
    )
    tomorrow = make_session(minutes_from_now=60 * 24)
    refused = teacher.get(f"/api/v1/class-sessions/{tomorrow.id}/check-in-code/")
    assert refused.status_code == 409 and refused.json()["code"] == "check_in_closed"
    code, _ = codes.make(tomorrow.id)
    early = learner.post(f"/api/v1/class-sessions/{tomorrow.id}/check-in/", {"code": code}, format="json")
    assert early.json()["code"] == "check_in_closed"
    no_register = make_session(title="Revision", takes_attendance=False)
    assert (
        teacher.get(f"/api/v1/class-sessions/{no_register.id}/check-in-code/").json()["code"]
        == "no_attendance"
    )


@pytest.mark.django_db
def test_a_student_outside_the_sessions_group_cannot_check_in(
    site, make_session, learner, student, client_for
):
    from courses.models import SiteGroup

    group = SiteGroup.objects.create(site=site, name="Lab group B")
    session = make_session(group=group)
    code, _ = codes.make(session.id)
    assert learner.post(
        f"/api/v1/class-sessions/{session.id}/check-in/", {"code": code}, format="json"
    ).status_code == (404)
    from courses.models import Membership

    Membership.objects.filter(site=site, person=student).update(role="assistant")
    other = make_session(title="Whole class")
    code, _ = codes.make(other.id)
    client = client_for(student.user)
    assert client.post(
        f"/api/v1/class-sessions/{other.id}/check-in/", {"code": code}, format="json"
    ).status_code == (403)


@pytest.mark.django_db
def test_the_lecturer_takes_the_register_in_bulk_from_a_phone_offline(
    make_session, teacher, learner, student, other_student, lecturer
):
    session = make_session(minutes_from_now=-90)
    url = f"/api/v1/class-sessions/{session.id}/register/"
    assert learner.get(url).status_code == 403
    assert learner.post(
        url, {"records": [{"student": student.id, "status": "present"}]}, format="json"
    ).status_code == (403)
    register = teacher.get(url).json()
    assert {r["name"] for r in register} == {"Ravi Singh", "Devi Ramnarine"} and register[0]["status"] is None

    key = str(uuid.uuid4())
    body = {
        "records": [
            {"student": student.id, "status": "present"},
            {"student": other_student.id, "status": "excused", "note": "Clinic"},
        ],
        "client_recorded_at": iso(minutes=-80),
    }
    first = teacher.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    again = teacher.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == 200 and first.json()["saved"] == 2
    assert again.json() == first.json() and again["Idempotent-Replay"] == "true"
    assert AttendanceRecord.objects.count() == 2

    stranger = teacher.post(url, {"records": [{"student": lecturer.id, "status": "present"}]}, format="json")
    assert stranger.status_code == 400
    old = teacher.post(url, {**body, "client_recorded_at": iso(days=-8)}, format="json")
    assert old.json()["code"] == "client_time_too_old"

    # A correction made later wins; a register taken earlier but sent later does not overwrite it.
    corrected = teacher.post(
        url, {"records": [{"student": student.id, "status": "late"}]}, format="json"
    ).json()
    assert corrected["saved"] == 1
    stale = teacher.post(
        url,
        {"records": [{"student": student.id, "status": "absent"}], "client_recorded_at": iso(minutes=-85)},
        format="json",
    ).json()
    assert stale["saved"] == 0 and stale["kept"] == [student.id]
    assert AttendanceRecord.objects.get(student=student).status == "late"
    assert AuditLog.objects.filter(entity="attendance.attendancerecord", action="update").count() == 1


@pytest.mark.django_db
def test_closing_the_register_marks_the_rest_absent_and_totals_are_counted(
    site, make_session, teacher, learner, student, other_student, client_for, make_user
):
    first = make_session(minutes_from_now=-60 * 24 * 2)
    second = make_session(minutes_from_now=-60 * 24)
    make_session(minutes_from_now=60 * 24, title="Next week")  # not held yet: does not count
    future = make_session(minutes_from_now=60)
    assert teacher.post(f"/api/v1/class-sessions/{future.id}/close-register/").json()["code"] == "not_started"
    teacher.post(
        f"/api/v1/class-sessions/{first.id}/register/",
        {
            "records": [
                {"student": student.id, "status": "present"},
                {"student": other_student.id, "status": "late"},
            ]
        },
        format="json",
    )
    teacher.post(
        f"/api/v1/class-sessions/{second.id}/register/",
        {"records": [{"student": other_student.id, "status": "excused"}]},
        format="json",
    )
    url = f"/api/v1/attendance/sites/{site.id}/totals/"
    before = {r["name"]: r for r in teacher.get(url).json()}
    assert before["Ravi Singh"]["not_recorded"] == 1 and before["Ravi Singh"]["percent"] == "100.00"
    assert learner.post(f"/api/v1/class-sessions/{second.id}/close-register/").status_code == 403
    assert teacher.post(f"/api/v1/class-sessions/{second.id}/close-register/").json() == {"marked_absent": 1}
    rows = {r["name"]: r for r in teacher.get(url).json()}
    assert rows["Ravi Singh"] | {} == {
        **rows["Ravi Singh"],
        "sessions": 2,
        "present": 1,
        "absent": 1,
        "not_recorded": 0,
        "percent": "50.00",
    }
    assert rows["Devi Ramnarine"]["late"] == 1 and rows["Devi Ramnarine"]["percent"] == "100.00"
    mine = learner.get(url).json()
    assert len(mine) == 1 and mine[0]["name"] == "Ravi Singh"
    auditor = make_user("auditor.att", "auditor")
    assert len(client_for(auditor).get(url).json()) == 2
    assert client_for(auditor).get(f"/api/v1/class-sessions/{first.id}/register/").status_code == 200


@pytest.mark.django_db
def test_totals_go_to_the_srms_only_where_the_programme_requires_it(
    site, make_session, teacher, learner, student, client_for, course_admin, settings, monkeypatch
):
    from integration import client as integration_client
    from integration import srms

    settings.SRMS_API_URL, settings.SRMS_API_KEY = "http://srms-api:8000", "k"
    posted = []

    def fake_call(base, key, path, params=None, data=None):
        posted.append((path, data))
        return {
            "offering_code": data["offering_code"],
            "accepted": [t["student_no"] for t in data["totals"]],
            "locked": [],
            "unknown": [],
        }

    monkeypatch.setattr(srms, "call", fake_call)
    session = make_session(minutes_from_now=-120)
    teacher.post(
        f"/api/v1/class-sessions/{session.id}/register/",
        {"records": [{"student": student.id, "status": "present"}]},
        format="json",
    )
    send = f"/api/v1/attendance/sites/{site.id}/send-to-srms/"
    assert teacher.post(send).json()["skipped"] == "attendance is not a condition on this course"
    assert posted == []

    policy_url = f"/api/v1/attendance/sites/{site.id}/policy/"
    assert teacher.get(policy_url).json()["send_to_srms"] is False
    assert learner.get(policy_url).status_code == 403
    assert teacher.put(policy_url, {"send_to_srms": True}, format="json").status_code == 403
    admin = client_for(course_admin)
    assert (
        admin.put(policy_url, {"send_to_srms": True, "minimum_percent": "80"}, format="json").status_code
        == 200
    )
    assert (
        admin.put(policy_url, {"send_to_srms": True, "minimum_percent": "75"}, format="json").status_code
        == 200
    )
    assert AuditLog.objects.filter(entity="attendance.attendancepolicy").count() == 2

    assert learner.post(send).status_code == 403
    answer = teacher.post(send).json()
    assert sorted(answer["accepted"]) == ["26MRP0001", "26MRP0002"]
    path, data = posted[0]
    assert path == "/api/v1/integration/attendance-totals/" and data["offering_code"] == site.code
    ravi = next(t for t in data["totals"] if t["student_no"] == "26MRP0001")
    assert ravi["present"] == 1 and ravi["percent"] == "100.00"
    assert AttendancePolicy.objects.get(site=site).last_sent_at is not None
    assert AuditLog.objects.filter(action="attendance_sent").exists()

    def down(*args, **kwargs):
        raise integration_client.IntegrationError("SRMS answered HTTP 404", status=404)

    monkeypatch.setattr(srms, "call", down)
    failed = teacher.post(send)
    assert failed.status_code == 502 and failed.json()["code"] == "srms_unavailable"
    assert AuditLog.objects.filter(action="attendance_send_failed").exists()

    from courses.models import CourseSite

    local = CourseSite.objects.create(code="LOCAL1", title="Local", source="local")
    assert srms.push_attendance(local)["skipped"] == "not an SRMS offering"
    AttendanceRecord.objects.all().delete()
    from courses.models import Membership

    Membership.objects.filter(site=site, role="student").update(is_active=False)
    assert srms.push_attendance(site) == {
        "offering_code": site.code,
        "accepted": [],
        "locked": [],
        "unknown": [],
    }


@pytest.mark.django_db
def test_the_short_code_is_typed_from_the_screen_and_lasts_its_minute_and_the_next(
    make_session, teacher, learner, settings
):
    session = make_session(minutes_from_now=-5)
    shown = teacher.get(f"/api/v1/class-sessions/{session.id}/check-in-code/").json()
    short = shown["short_code"]
    assert len(short) == 6 and not set(short) & set("IO01")
    assert 1 <= shown["refresh_seconds"] <= 60
    now = timezone.now().timestamp()
    window_start = (now // 60) * 60
    assert codes.check(session.id, short, now=window_start + 119) is None  # still good the next minute
    assert codes.check(session.id, short, now=window_start + 125) == "expired"
    assert codes.check(session.id, short, now=window_start + 600) == "invalid"
    other = make_session(title="Another class")
    assert codes.check(other.id, short, now=now) == "invalid"
    assert codes.check(session.id, "ABC", now=now) == "invalid"
    url = f"/api/v1/class-sessions/{session.id}/check-in/"
    # Typed as people type it: lower case, with a space in the middle.
    typed = f"{short[:3].lower()} {short[3:].lower()}"
    assert learner.post(url, {"code": typed}, format="json").status_code == 201
