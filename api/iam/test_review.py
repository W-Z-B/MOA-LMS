"""The access review each term (item 1.21)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from audit.models import AuditLog
from iam.models import AccessReview
from iam.tasks import access_review_reminder, remind_access_review
from notifications.models import Notification


@pytest.fixture
def administrator(make_user):
    return make_user("sys.admin", "administrator")


@pytest.mark.django_db
def test_the_list_shows_role_holders_and_teaching_staff(administrator, course_admin, site, client_for):
    data = client_for(course_admin).get("/api/v1/auth/access-review/").json()
    roles = {(r["username"], r["role"]) for r in data["role_holders"]}
    assert {("sys.admin", "administrator"), ("course.admin", "course_admin"), ("E0001", "lecturer")} <= roles
    assert [(t["site_code"], t["employee_no"], t["site_role"]) for t in data["teaching_staff"]] == [
        (site.code, "E0001", "Lecturer")
    ]
    assert data["last_review"] is None


@pytest.mark.django_db
def test_only_administrators_sign_it_off_and_others_are_refused(
    administrator, student, lecturer, make_user, site, client_for
):
    assert client_for(student.user).get("/api/v1/auth/access-review/").status_code == 403
    assert client_for(lecturer.user).post("/api/v1/auth/access-review/sign-off/", {}).status_code == 403
    auditor = client_for(make_user("the.auditor", "auditor"))
    assert auditor.get("/api/v1/auth/access-review/").status_code == 200
    assert auditor.post("/api/v1/auth/access-review/sign-off/", {}).status_code == 403

    signed = client_for(administrator).post(
        "/api/v1/auth/access-review/sign-off/", {"notes": "Removed a lecturer who left"}, format="json"
    )
    assert signed.status_code == 201 and signed.json()["teaching_staff"] == 1
    entry = AuditLog.objects.get(action="access_review_signed")
    assert entry.actor == administrator and entry.reason == "Removed a lecturer who left"
    assert auditor.get("/api/v1/auth/access-review/").json()["last_review"]["reviewed_by"] == "sys.admin"


@pytest.mark.django_db
def test_the_reminder_lists_who_to_confirm_once_a_term(administrator, course_admin, site):
    today = timezone.localdate()
    assert remind_access_review(today) == 2
    note = Notification.objects.get(recipient=administrator, title="Access review due")
    assert "has not been signed off yet" in note.body
    assert f"{site.code}: Asha Persaud (E0001), lecturer" in note.body
    assert "course.admin" in note.body
    assert remind_access_review(today) == 0  # once a term

    AccessReview.objects.create(reviewed_by=administrator, role_holders=3, teaching_staff=1)
    assert access_review_reminder() == 0  # just signed off
    AccessReview.objects.update(reviewed_at=timezone.now() - timedelta(days=200))
    Notification.objects.all().delete()
    assert remind_access_review(today) == 2
    assert "was last signed off on" in Notification.objects.first().body
