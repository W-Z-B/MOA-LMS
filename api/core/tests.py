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

    site = CourseSite.objects.get()
    assert site.is_published and site.source == CourseSite.Source.LOCAL
    assert site.memberships.count() == 3
    assert Assignment.objects.filter(site=site).count() == 3  # with "Field notebook check", for the Homes
    assert Mark.objects.filter(submission__assignment__site=site, is_released=True).count() == 2
    # The practicals journeys' task (items 3.12 to 3.15): three criteria, the critical one mapped to the
    # framework the site follows, and no weight, so it changes no coursework figure.
    from practicals.models import PracticalTask, SiteFramework

    task = PracticalTask.objects.get(site=site)
    assert task.is_published and task.weight == 0 and task.criteria.count() == 3
    assert task.criteria.get(is_critical=True).performance_criteria.get().code == "PC1.1.1"
    assert SiteFramework.objects.get(site=site).framework.units.count() == 1

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
    assert [row["title"] for row in marking] == ["Crop calendar for a kitchen garden: 1 to mark"]
