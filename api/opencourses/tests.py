"""Open short courses (item 5.07): off by default; the public catalogue, registration by email with the
privacy notice, rate limits, learners kept to open sites, joining and the completion certificate."""

import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from certificates.models import Certificate
from courses.access import site_role, visible_sites
from courses.models import ContentItem, CourseSite, ItemCompletion, Membership, Module
from iam.models import Role, RoleScope
from opencourses import services, tasks
from opencourses.models import OpenRegistration
from people.models import PersonRef
from privacy.models import NoticeAcknowledgement, PrivacyNotice
from staffdev.models import CatalogueEntry

PASSWORD = "Cassava-Field-2026!"


@pytest.fixture
def enabled(settings):
    settings.OPEN_COURSES_ENABLED = True
    settings.OPEN_REGISTRATIONS_PER_ADDRESS = 3
    return settings


@pytest.fixture
def open_course(seeded):
    site = CourseSite.objects.create(
        code="OPEN-POULTRY-2026", title="Backyard poultry", kind=CourseSite.Kind.OPEN, is_published=True
    )
    CatalogueEntry.objects.create(
        site=site, summary="Housing, feed and health of a small flock.", audience="Farmers", capacity=2
    )
    module = Module.objects.create(site=site, title="Week 1")
    ContentItem.objects.create(module=module, title="Housing", body="<p>Dry and airy.</p>")
    return site


@pytest.fixture
def notice(seeded):
    return PrivacyNotice.objects.create(
        version=99, title="Privacy notice", body="What we keep.", published_at=timezone.now()
    )


def _register(client, **data):
    body = {
        "first_name": "Sita",
        "last_name": "Persaud",
        "email": "sita@example.org",
        "privacy_accepted": True,
    }
    return client.post("/api/v1/open-courses/register/", {**body, **data}, format="json")


def _token() -> str:
    return re.search(r"/open-courses/confirm/(\S+)", mail.outbox[-1].body).group(1)


@pytest.mark.django_db
def test_everything_is_off_until_gsa_decides(seeded, open_course):
    client = APIClient()
    for response in (
        client.get("/api/v1/open-courses/"),
        _register(client),
        client.get("/api/v1/open-courses/confirm/?token=x"),
        client.post("/api/v1/open-courses/confirm/", {"token": "x", "password": PASSWORD}, format="json"),
    ):
        assert response.status_code == 404 and response.json()["code"] == "open_courses_off"
    assert not OpenRegistration.objects.exists() and not mail.outbox


@pytest.mark.django_db
def test_register_confirm_join_and_complete(
    enabled, open_course, notice, site, django_capture_on_commit_callbacks
):
    public = APIClient()
    listed = public.get("/api/v1/open-courses/").json()
    assert listed["privacy_notice"]["version"] == 99
    assert listed["courses"] == [
        {
            "id": open_course.id,
            "code": "OPEN-POULTRY-2026",
            "title": "Backyard poultry",
            "summary": "Housing, feed and health of a small flock.",
            "audience": "Farmers",
            "length_hours": None,
            "places_left": 2,
            "joined": False,
            "certificate": True,
        }
    ]
    # The privacy notice must be accepted.
    refused = _register(public, privacy_accepted=False)
    assert refused.status_code == 400 and "privacy_accepted" in refused.json()
    # Registering sends a link; nothing is made until it is followed.
    asked = _register(public, site=open_course.id, email="Sita@Example.org ")
    assert asked.status_code == 202 and "link" in asked.json()["detail"]
    assert (
        mail.outbox[-1].to == ["sita@example.org"] and not PersonRef.objects.filter(kind="learner").exists()
    )
    token = _token()
    assert OpenRegistration.objects.get().token_hash != token  # only a fingerprint is kept
    looked = public.get(f"/api/v1/open-courses/confirm/?token={token}").json()
    assert looked == {"email": "sita@example.org", "first_name": "Sita", "course": "Backyard poultry"}
    weak = public.post("/api/v1/open-courses/confirm/", {"token": token, "password": "short"}, format="json")
    assert weak.status_code == 400 and weak.json()["code"] == "weak_password"
    made = public.post("/api/v1/open-courses/confirm/", {"token": token, "password": PASSWORD}, format="json")
    assert made.status_code == 201 and made.json()["username"] == "sita@example.org"
    again = public.post(
        "/api/v1/open-courses/confirm/", {"token": token, "password": PASSWORD}, format="json"
    )
    assert again.json()["code"] == "link_not_valid"

    person = PersonRef.objects.get(kind="learner")
    user = person.user
    assert (
        person.external_id.startswith("OL")
        and RoleScope.objects.filter(user=user, role__code="learner").exists()
    )
    assert NoticeAcknowledgement.objects.filter(user=user, notice=notice).exists()
    assert Membership.objects.filter(site=open_course, person=person, role="student").exists()
    assert AuditLog.objects.filter(action="learner_registered").exists()

    # The learner signs in with the email address and no authenticator code; they see open sites only,
    # even if someone puts them on an academic site by mistake.
    signed = APIClient()
    login = signed.post(
        "/api/v1/auth/login/", {"username": "sita@example.org", "password": PASSWORD}, format="json"
    )
    assert (
        login.status_code == 200 and login.json()["roles"] == ["learner"] and not login.json()["mfa_required"]
    )
    Membership.objects.create(site=site, person=person, role="student")
    assert list(visible_sites(user)) == [open_course]
    assert site_role(user, site) is None and site_role(user, open_course) == "student"
    assert signed.get(f"/api/v1/sites/{site.id}/").status_code == 404
    assert signed.get(f"/api/v1/assignments/?site={site.id}").json()["count"] == 0
    assert signed.get(f"/api/v1/sites/{open_course.id}/").status_code == 200
    assert signed.get("/api/v1/open-courses/").json()["courses"][0]["joined"] is True

    # Completing the course issues the certificate, as on staff-development courses.
    item = ContentItem.objects.get(module__site=open_course)
    with django_capture_on_commit_callbacks(execute=True):
        ItemCompletion.objects.create(person=person, item=item, completed_at=timezone.now(), how="viewed")
    certificate = Certificate.objects.get(person=person)
    assert certificate.values["number"] == person.external_id
    mine = signed.get("/api/v1/certificates/").json()
    assert mine["count"] == 1


@pytest.mark.django_db
def test_known_addresses_rate_limits_places_and_expiry(enabled, open_course, make_person, client_for):
    staff = make_person("staff", "E0701", "Ext", "Officer", email="officer@agri.gov.gy")
    public = APIClient()
    # A known address is told to sign in; the answer is the same as for a new one.
    known = _register(public, email="officer@agri.gov.gy")
    assert known.status_code == 202 and "already have an account" in mail.outbox[-1].subject
    # Three an hour from one network address.
    for n in range(2):
        assert _register(public, email=f"farmer{n}@example.org").status_code == 202
    limited = _register(public, email="farmer9@example.org")
    assert limited.status_code == 429 and limited.json()["code"] == "too_many_requests"
    # Three a day for one email address, from anywhere.
    OpenRegistration.objects.update(source_ip="198.51.100.1")
    for n in range(2):
        assert (
            _register(APIClient(REMOTE_ADDR=f"203.0.113.{n}"), email="farmer0@example.org").status_code == 202
        )
    assert _register(APIClient(REMOTE_ADDR="203.0.113.9"), email="farmer0@example.org").status_code == 429

    # Staff may join an open course too; it holds two places.
    member = client_for(staff.user)
    assert member.post(f"/api/v1/open-courses/{open_course.id}/join/").json()["joined"] is True
    other = make_person("student", "26MRP0700", "Second", "Learner")
    assert client_for(other.user).post(f"/api/v1/open-courses/{open_course.id}/join/").status_code == 200
    third = make_person("student", "26MRP0701", "Third", "Learner")
    full = client_for(third.user).post(f"/api/v1/open-courses/{open_course.id}/join/")
    assert full.status_code == 409 and full.json()["code"] == "full"
    academic = CourseSite.objects.create(code="AGR999", title="Academic", is_published=True)
    assert member.post(f"/api/v1/open-courses/{academic.id}/join/").status_code == 404
    with pytest.raises(services.Refused):
        services.join(None, academic, staff.user.person)

    # Links last OPEN_CONFIRM_HOURS; unconfirmed requests are deleted after that.
    OpenRegistration.objects.update(asked_at=timezone.now() - timedelta(hours=49))
    token = _token()
    assert APIClient().get(f"/api/v1/open-courses/confirm/?token={token}").json()["code"] == "link_not_valid"
    waiting = OpenRegistration.objects.count()
    assert waiting and tasks.purge_registrations() == waiting
    assert not OpenRegistration.objects.exists()


@pytest.mark.django_db
def test_an_address_registered_twice_and_the_learner_role_alone(enabled, open_course, make_user):
    public = APIClient()
    _register(public)
    first = _token()
    _register(public)
    second = _token()
    assert (
        public.post(
            "/api/v1/open-courses/confirm/", {"token": first, "password": PASSWORD}, format="json"
        ).status_code
        == 201
    )
    taken = public.post(
        "/api/v1/open-courses/confirm/", {"token": second, "password": PASSWORD}, format="json"
    )
    assert taken.status_code == 409 and taken.json()["code"] == "already_registered"
    # A learner role on an account with no person record still keeps it to open sites.
    bare = make_user("learner.only", Role.LEARNER)
    academic = CourseSite.objects.create(code="AGR998", title="Academic", is_published=True)
    assert site_role(bare, academic) is None and not visible_sites(bare).exists()
    assert APIClient().get("/api/v1/open-courses/").status_code == 200
