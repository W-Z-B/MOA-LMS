"""Every change made in the Django admin reaches the chained audit log (ASVS 7.1.3, 4.3.3)."""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client

from audit.models import AuditLog
from conftest import PASSWORD
from iam.admin_audit import REASON, AuditedAdmin


def admin_client(user):
    client = Client()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


@pytest.fixture
def root(seeded):
    return get_user_model().objects.create_superuser("root.admin", "root@gsa.edu.gy", PASSWORD)


def test_every_model_in_the_admin_is_audited():
    """Whichever app registers it, Django's own User and Group included (LmsAdminSite.register)."""
    registered = admin.site._registry
    assert get_user_model() in registered and Group in registered
    unaudited = [
        m._meta.label for m, model_admin in registered.items() if not isinstance(model_admin, AuditedAdmin)
    ]
    assert unaudited == []


@pytest.mark.django_db
def test_adding_changing_and_removing_in_the_admin_is_audited(root):
    client = admin_client(root)
    permission = Permission.objects.get(codename="view_auditlog")
    added = client.post("/admin/auth/group/add/", {"name": "Examiners", "permissions": [permission.pk]})
    assert added.status_code == 302, added.content[:2000]
    group = Group.objects.get(name="Examiners")
    entries = AuditLog.objects.filter(entity="auth.group", entity_id=group.pk).order_by("id")
    made, chosen = entries
    assert made.action == "create" and made.actor == root and made.reason == REASON
    assert made.after["name"] == "Examiners"
    # The many-to-many choice is saved after the record itself, and recorded as its own entry.
    assert chosen.action == "update" and chosen.after == {"permissions": [permission.pk]}
    assert chosen.before == {"permissions": []}

    changed = client.post(f"/admin/auth/group/{group.pk}/change/", {"name": "External examiners"})
    assert changed.status_code == 302
    renamed, unchosen = AuditLog.objects.filter(entity="auth.group", action="update", id__gt=chosen.id).order_by("id")
    assert renamed.before["name"] == "Examiners" and renamed.after["name"] == "External examiners"
    assert unchosen.before == {"permissions": [permission.pk]} and unchosen.after == {"permissions": []}

    removed = client.post(f"/admin/auth/group/{group.pk}/delete/", {"post": "yes"})
    assert removed.status_code == 302 and not Group.objects.filter(pk=group.pk).exists()
    gone = AuditLog.objects.get(entity="auth.group", action="delete")
    assert gone.entity_id == group.pk and gone.before["name"] == "External examiners"


@pytest.mark.django_db
def test_an_accounts_flags_and_password_changed_in_the_admin_are_audited_without_the_hash(
    root, make_user, rf
):
    clerk = make_user("clerk")
    client = admin_client(root)
    answer = client.post(
        f"/admin/auth/user/{clerk.pk}/password/",
        {
            "password1": "An0ther-" + "Long-Passw0rd",
            "password2": "An0ther-" + "Long-Passw0rd",
            "usable_password": "true",
        },
    )
    assert answer.status_code == 302, answer.content[:2000]
    entry = AuditLog.objects.get(entity="auth.user", entity_id=clerk.pk, actor=root)
    assert entry.action == "update" and entry.reason == REASON
    assert entry.after["password"].startswith("***") and "pbkdf2" not in str(entry.after)

    # The Active, Staff and Superuser flags through the list's own bulk action path (save_model).

    model_admin = admin.site._registry[get_user_model()]
    request = rf.post("/admin/")
    request.user = root
    clerk.is_staff = True
    model_admin.save_model(request, clerk, form=None, change=True)
    flags = AuditLog.objects.filter(entity="auth.user", entity_id=clerk.pk).order_by("-id").first()
    assert flags.before["is_staff"] is False and flags.after["is_staff"] is True
    assert flags.before["password"].startswith("***")


@pytest.mark.django_db
def test_rows_edited_inline_are_audited(root, site, student, rf):
    """An inline formset (a site's memberships) records each row added, changed or removed."""
    from django.forms import inlineformset_factory

    from courses.models import CourseSite, Membership

    model_admin = admin.site._registry[CourseSite]
    request = rf.post("/admin/")
    request.user = root
    Memberships = inlineformset_factory(
        CourseSite, Membership, fields=("person", "role", "is_active"), extra=0
    )
    existing = list(site.memberships.order_by("pk"))
    data = {
        "memberships-TOTAL_FORMS": str(len(existing)),
        "memberships-INITIAL_FORMS": str(len(existing)),
    }
    for index, membership in enumerate(existing):
        data.update(
            {
                f"memberships-{index}-id": str(membership.pk),
                f"memberships-{index}-person": str(membership.person_id),
                f"memberships-{index}-role": membership.role,
                f"memberships-{index}-is_active": "on",
            }
        )
    target = next(i for i, m in enumerate(existing) if m.person_id == student.pk)
    data.pop(f"memberships-{target}-is_active")  # the student's membership is switched off
    other = next(i for i, m in enumerate(existing) if m.person_id != student.pk)
    data[f"memberships-{other}-DELETE"] = "on"
    formset = Memberships(data, instance=site, prefix="memberships")
    assert formset.is_valid(), formset.errors
    model_admin.save_formset(request, None, formset, change=True)
    changed = AuditLog.objects.get(entity="courses.membership", action="update")
    assert changed.entity_id == existing[target].pk
    assert changed.before["is_active"] is True and changed.after["is_active"] is False
    removed = AuditLog.objects.get(entity="courses.membership", action="delete")
    assert removed.entity_id == existing[other].pk and removed.before["person"] == existing[other].person_id


@pytest.mark.django_db
def test_marks_and_handed_in_work_are_read_only_in_the_admin(root, rf):
    from assessments.models import Mark, Submission

    client = admin_client(root)
    assert client.get("/admin/assessments/mark/add/").status_code == 403
    assert client.get("/admin/assessments/submission/add/").status_code == 403
    for model in (Mark, Submission):
        model_admin = admin.site._registry[model]
        request = rf.post("/admin/")
        request.user = root
        assert not model_admin.has_change_permission(request) and not model_admin.has_delete_permission(
            request
        )
