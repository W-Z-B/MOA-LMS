import pyotp
import pytest
from django.core.exceptions import ImproperlyConfigured

from core import crypto

JOURNEY_TOTP = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"  # fictional, as in compose.e2e.yml


def test_encrypt_decrypt_round_trip():
    token = crypto.encrypt("JBSWY3DPEHPK3PXP")
    assert token != b"JBSWY3DPEHPK3PXP"
    assert crypto.decrypt(token) == "JBSWY3DPEHPK3PXP"


def test_missing_key_is_a_configuration_error(settings):
    settings.FIELD_ENCRYPTION_KEY = ""
    crypto._fernet.cache_clear()
    with pytest.raises(ImproperlyConfigured):
        crypto.encrypt("x")
    crypto._fernet.cache_clear()


@pytest.mark.django_db
def test_seed_is_idempotent(seeded):
    from django.core.management import call_command

    from iam.models import Role
    from integration.models import CampusRef

    before = (Role.objects.count(), CampusRef.objects.count())
    call_command("seed", "--country", "GY", verbosity=0)
    assert (Role.objects.count(), CampusRef.objects.count()) == before == (6, 2)


@pytest.mark.django_db
def test_journey_data_needs_fictional_and_a_password(monkeypatch):
    from django.core.management import CommandError, call_command

    monkeypatch.setenv("DEMO_USER_PASSWORD", "e2e-Only-Fictional-Learner-2026")
    with pytest.raises(CommandError, match="--fictional"):
        call_command("seed_journeys")
    monkeypatch.setenv("DEMO_USER_PASSWORD", "short")
    with pytest.raises(CommandError, match="DEMO_USER_PASSWORD"):
        call_command("seed_journeys", "--fictional")
    monkeypatch.setenv("DEMO_USER_PASSWORD", "e2e-Only-Fictional-Learner-2026")
    monkeypatch.setenv("DEMO_TOTP_SECRET", "not-base32")
    with pytest.raises(CommandError, match="DEMO_TOTP_SECRET"):
        call_command("seed_journeys", "--fictional")


@pytest.mark.django_db
def test_journey_data_signs_in_and_teaches_one_course(monkeypatch):
    from django.core.management import call_command
    from rest_framework.test import APIClient

    from assessments.models import Assignment, Mark
    from courses.models import CourseSite

    monkeypatch.setenv("DEMO_USER_PASSWORD", "e2e-Only-Fictional-Learner-2026")
    monkeypatch.setenv("DEMO_TOTP_SECRET", JOURNEY_TOTP)
    call_command("seed_journeys", "--fictional", verbosity=0)
    call_command("seed_journeys", "--fictional", verbosity=0)  # idempotent

    site = CourseSite.objects.get(code="AGR101-2026-27-S1-MRP")
    assert site.is_published and site.source == CourseSite.Source.LOCAL
    assert site.memberships.count() == 3
    # The lecturer also teaches last year's AGR102, dated, and this year's, empty, to copy one into the other.
    earlier = CourseSite.objects.get(code="AGR102-2025-26-S1-MRP")
    later = CourseSite.objects.get(code="AGR102-2026-27-S1-MRP")
    assert earlier.modules.get().available_from is not None and earlier.assignments.count() == 1
    assert not later.modules.exists() and not later.is_published
    assert {m.person.external_id for m in later.memberships.all()} == {"E0901"}
    assert Assignment.objects.filter(site=site).count() == 3  # with "Field notebook check", for the Homes
    assert Mark.objects.filter(submission__assignment__site=site, is_released=True).count() == 2
    # The practicals journeys' task (items 3.12 to 3.15): three criteria, the critical one mapped to the
    # framework the site follows, and no weight, so it changes no coursework figure.
    from practicals.models import PracticalTask, SiteFramework

    task = PracticalTask.objects.get(site=site)
    assert task.is_published and task.weight == 0 and task.criteria.count() == 3
    assert task.criteria.get(is_critical=True).performance_criteria.get().code == "PC1.1.1"
    assert SiteFramework.objects.get(site=site).framework.units.count() == 1
    # The quiz journeys write their questions in the course's bank (feature 10).
    from quizzes.models import QuestionBank

    bank = QuestionBank.objects.get(site=site)
    assert [c.name for c in bank.categories.all()] == ["Week 1: What a crop needs"]

    client = APIClient()
    response = client.post(
        "/api/v1/auth/login/",
        {"username": "kezia.persaud", "password": "e2e-Only-Fictional-Learner-2026"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["person_kind"] == "student"
    assert response.json()["mfa_required"] is False  # students need no authenticator code
    assert response.json()["privacy_notice_due"] == 1  # the notice is published, so it is read first
    sites = client.get("/api/v1/sites/").json()["results"]
    assert [(s["title"], s["my_role"]) for s in sites] == [("Introduction to Crop Production", "student")]
    due = [w["title"] for w in client.get("/api/v1/home/").json()["student"]["due"]]
    assert due == ["Field notebook check"]  # due this week, not handed in
    # Items 4.08 to 4.15: a question-and-answer forum where Kezia sees Tevin's answer only once she answers,
    # two classes open for the register and check-in now, and a group she may join herself.
    forums = {f["title"]: f for f in client.get("/api/v1/forums/").json()}
    assert set(forums) == {"Questions on germination", "Class discussion"}
    threads = client.get(f"/api/v1/forums/{forums['Questions on germination']['id']}/threads/").json()
    shown = client.get(f"/api/v1/threads/{threads[0]['id']}/").json()
    assert shown["replies_hidden"] is True and len(shown["posts"]) == 1
    classes = client.get("/api/v1/class-sessions/", {"site": site.id}).json()["results"]
    assert [c["title"] for c in classes] == [
        "Field practical: seed sowing",
        "Soil science lecture",
        "Irrigation (online)",
    ]
    groups = client.get(f"/api/v1/sites/{site.id}/my-groups/").json()
    assert [(g["name"], g["member"], g["open"]) for g in groups] == [
        ("Lab group A", True, False),
        ("Lab group B", False, True),
    ]

    # The lecturer must give a code, computed from the fictional secret the journeys hold.
    lecturer = APIClient()
    me = lecturer.post(
        "/api/v1/auth/login/",
        {"username": "marlon.bacchus", "password": "e2e-Only-Fictional-Learner-2026"},
        format="json",
    ).json()
    assert me["mfa_required"] is True and me["mfa_verified"] is False
    code = pyotp.TOTP(JOURNEY_TOTP).now()
    assert lecturer.post("/api/v1/auth/mfa/verify/", {"code": code}, format="json").json()["mfa_verified"]
    marking = lecturer.get("/api/v1/home/").json()["teaching"]["to_mark"]
    # AGR101's hand-in waits longest, so it comes first; then the marking journeys' course (AGR205).
    assert [row["title"] for row in marking] == [
        "Crop calendar for a kitchen garden: 1 to mark",
        "Soil profile report: 2 to mark",
        "Soil texture test: 2 to mark",
    ]

    # The marking journeys' course: a report handed in as a PDF a day late, with a rubric and a penalty.
    soils = CourseSite.objects.get(code="AGR205-2026-27-S1-MRP")
    report = Assignment.objects.get(site=soils, title="Soil profile report")
    assert report.rubric.criteria.count() == 2 and report.late_penalty == "per_day"
    rows = lecturer.get(f"/api/v1/assignments/{report.id}/submissions/").json()
    assert [(r["student_no"], r["is_late"], len(r["files"])) for r in rows] == [
        ("S2026911", True, 1),
        ("S2026912", True, 1),
    ]
    shown = lecturer.get(rows[0]["files"][0]["download_url"] + "?inline=1")
    assert shown.status_code == 200 and shown["Content-Type"] == "application/pdf"
    assert b"".join(shown.streaming_content).startswith(b"%PDF")


@pytest.mark.django_db
def test_journey_data_for_staff_development_invitations_and_the_console(monkeypatch, tmp_path):
    import json

    from django.core.management import call_command
    from rest_framework.test import APIClient

    links_file = tmp_path / "journeys" / "links.json"
    monkeypatch.setenv("DEMO_USER_PASSWORD", "e2e-Only-Fictional-Learner-2026")
    monkeypatch.setenv("DEMO_TOTP_SECRET", JOURNEY_TOTP)
    monkeypatch.setenv("JOURNEY_LINKS_FILE", str(links_file))
    call_command("seed_journeys", "--fictional", verbosity=0)
    written = json.loads(links_file.read_text())
    call_command("seed_journeys", "--fictional", verbosity=0)  # idempotent: the same certificate
    again = json.loads(links_file.read_text())
    assert again["certificate"] == written["certificate"]
    assert written["certificate"]["code"] == "JRNY-0000-2026"

    # The invitation opens a new student's account, once: after the password is chosen it is not offered.
    assert len(written["invitations"]) == 2 and written["invitations"][0].startswith("/#/set-password/")
    uid, token = written["invitations"][0].split("/")[-2:]
    anyone = APIClient()
    assert anyone.post(
        "/api/v1/auth/password/check/", {"uid": uid, "token": token}, format="json"
    ).json() == {
        "username": "S2026903",
        "kind": "invitation",
    }
    chosen = {"uid": uid, "token": token, "password": "Mango-Season-Starts-2026"}
    assert anyone.post("/api/v1/auth/password/set/", chosen, format="json").status_code == 200
    call_command("seed_journeys", "--fictional", verbosity=0)
    assert len(json.loads(links_file.read_text())["invitations"]) == 1

    # The certificate is genuine to the public check.
    checked = anyone.post("/api/v1/certificates/check/", written["certificate"], format="json").json()
    assert checked["status"] == "genuine" and checked["holder"] == "Marlon Bacchus"
    assert checked["expires_on"] is not None

    # The administrator gives a code too; the open course is in the catalogue for Marlon to join.
    admin = APIClient()
    admin.post(
        "/api/v1/auth/login/",
        {"username": "ayesha.ramdin", "password": "e2e-Only-Fictional-Learner-2026"},
        format="json",
    )
    me = admin.post(
        "/api/v1/auth/mfa/verify/", {"code": pyotp.TOTP(JOURNEY_TOTP).now()}, format="json"
    ).json()
    assert me["roles"] == ["administrator"] and me["mfa_verified"]
    assert admin.get("/api/v1/audit/").status_code == 200
    catalogue = admin.get("/api/v1/staff-development/catalogue/").json()["results"]
    assert [(c["code"], c["self_enrol"]) for c in catalogue] == [("SD-102", "approval"), ("SD-101", "open")]


@pytest.mark.django_db
def test_journey_data_for_insight_raises_one_alert_per_student_and_reads_the_reports(monkeypatch):
    """The insight journeys' course (items 3.11, 6.01 to 6.06): an alert for each student, stable when the
    data is loaded again, and a head of department scoped to Marlon's unit."""
    from django.core.management import call_command

    from courses.models import CourseSite
    from iam.models import RoleScope
    from insights.models import Alert, OutcomeLink

    monkeypatch.setenv("DEMO_USER_PASSWORD", "e2e-Only-Fictional-Learner-2026")
    monkeypatch.setenv("DEMO_TOTP_SECRET", JOURNEY_TOTP)
    call_command("seed_journeys", "--fictional", verbosity=0)
    call_command("seed_journeys", "--fictional", verbosity=0)  # idempotent

    site = CourseSite.objects.get(code="AGR150-2026-27-S1-MRP")
    raised = Alert.objects.filter(site=site)
    assert sorted(a.student.external_id for a in raised) == ["S2026921", "S2026922"]
    assert all(a.kind == "missed_work" and a.state == "open" and len(a.evidence) == 2 for a in raised)
    assert OutcomeLink.objects.get(site=site).assignment.title == "Farm diary"
    grant = RoleScope.objects.get(user__username="gail.henry")
    assert (grant.role.code, grant.unit_code) == ("head_of_department", "CROPS")
