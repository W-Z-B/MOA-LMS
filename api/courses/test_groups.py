"""Group work (item 4.12): groupings, random allocation into N groups or groups of K, and self-sign-up."""

import random
from datetime import timedelta

import pytest
from django.utils import timezone

from audit.models import AuditLog
from courses import groups
from courses.groups import Grouping, GroupRefused, GroupSignUp
from courses.models import Membership, SiteGroup


@pytest.fixture
def class_of_seven(site, make_person):
    for n in range(5):
        person = make_person("student", f"26MRP01{n:02d}", f"Student{n}", "Extra")
        Membership.objects.create(site=site, person=person, role="student")
    return site


def test_split_shares_as_evenly_as_possible():
    assert groups.split(7, groups=3) == [3, 2, 2]
    assert groups.split(7, size=3) == [3, 2, 2]
    assert groups.split(6, size=3) == [3, 3]
    assert groups.split(2, groups=3) == [1, 1, 0]


@pytest.mark.django_db
def test_students_are_shared_at_random_into_groups(class_of_seven, client_for, lecturer, student):
    site = class_of_seven
    teacher = client_for(lecturer.user)
    url = f"/api/v1/sites/{site.id}/allocate-groups/"
    assert client_for(student.user).post(url, {"groups": 2}, format="json").status_code == 403
    assert teacher.post(url, {"groups": 2, "size": 3}, format="json").status_code == 400
    assert teacher.post(url, {}, format="json").status_code == 400
    made = teacher.post(url, {"size": 3, "prefix": "Field group", "grouping": "Field groups"}, format="json")
    assert made.status_code == 201
    body = made.json()
    assert [g["name"] for g in body["groups"]] == ["Field group 1", "Field group 2", "Field group 3"]
    assert sorted(len(g["members"]) for g in body["groups"]) == [2, 2, 3]
    everyone = [m for g in body["groups"] for m in g["members"]]
    students = Membership.objects.filter(site=site, role="student").values_list("id", flat=True)
    assert sorted(everyone) == sorted(students)  # each student once, staff never
    grouping = Grouping.objects.get(pk=body["grouping"])
    assert grouping.groups.count() == 3
    assert AuditLog.objects.filter(entity="courses.sitegroup", action="create").count() == 3

    taken = teacher.post(url, {"groups": 2, "prefix": "Field group"}, format="json")
    assert taken.status_code == 409 and taken.json()["code"] == "name_taken"
    same_grouping = teacher.post(
        url, {"groups": 2, "prefix": "Lab", "grouping": "Field groups"}, format="json"
    )
    assert same_grouping.json()["code"] == "name_taken"
    assert SiteGroup.objects.filter(name__startswith="Lab").count() == 0  # nothing half-made
    many = teacher.post(url, {"groups": 8, "prefix": "Tiny"}, format="json")
    assert many.status_code == 409 and many.json()["code"] == "too_many_groups"


@pytest.mark.django_db
def test_allocation_is_random(class_of_seven):
    a, _ = groups.allocate(class_of_seven, groups=2, prefix="A", rng=random.Random(1))  # noqa: S311 - a fixed seed for the test
    b, _ = groups.allocate(class_of_seven, groups=2, prefix="B", rng=random.Random(2))  # noqa: S311
    assert [sorted(g.members.values_list("id", flat=True)) for g in a] != [
        sorted(g.members.values_list("id", flat=True)) for g in b
    ]


@pytest.mark.django_db
def test_an_empty_class_cannot_be_allocated(site):
    Membership.objects.filter(site=site, role="student").update(is_active=False)
    with pytest.raises(GroupRefused) as refused:
        groups.allocate(site, groups=2)
    assert refused.value.code == "no_students"


@pytest.mark.django_db
def test_groupings_are_managed_by_teaching_staff(site, client_for, lecturer, student):
    teacher = client_for(lecturer.user)
    lab = SiteGroup.objects.create(site=site, name="Lab A")
    made = teacher.post(
        "/api/v1/groupings/", {"site": site.id, "name": "Lab groups", "groups": [lab.id]}, format="json"
    )
    assert made.status_code == 201 and made.json()["groups"] == [lab.id]
    again = teacher.post("/api/v1/groupings/", {"site": site.id, "name": "Lab groups"}, format="json")
    assert again.status_code == 400
    assert client_for(student.user).get("/api/v1/groupings/").json()["results"] == []
    assert (
        client_for(student.user)
        .post("/api/v1/groupings/", {"site": site.id, "name": "Mine"}, format="json")
        .status_code
        == 403
    )
    assert teacher.get(f"/api/v1/groupings/?site={site.id}").json()["count"] == 1
    from courses.models import CourseSite

    elsewhere = CourseSite.objects.create(code="X1", title="X", is_published=True)
    foreign = SiteGroup.objects.create(site=elsewhere, name="Other")
    wrong = teacher.patch(f"/api/v1/groupings/{made.json()['id']}/", {"groups": [foreign.id]}, format="json")
    assert wrong.status_code == 400


@pytest.mark.django_db
def test_students_sign_up_to_open_groups_within_the_limits(
    site, client_for, lecturer, student, other_student, make_user
):
    teacher, learner, classmate = (client_for(p.user) for p in (lecturer, student, other_student))
    auditor = client_for(make_user("auditor.groups", "auditor"))
    lab_a = SiteGroup.objects.create(site=site, name="Lab A")
    lab_b = SiteGroup.objects.create(site=site, name="Lab B")
    hand = SiteGroup.objects.create(site=site, name="Chosen by the lecturer")

    assert learner.post(f"/api/v1/groups/{lab_a.id}/join/").json()["code"] == "not_self_sign_up"
    assert (
        learner.put(f"/api/v1/groups/{lab_a.id}/sign-up/", {"max_size": 1}, format="json").status_code == 403
    )
    for group in (lab_a, lab_b):
        set_up = teacher.put(f"/api/v1/groups/{group.id}/sign-up/", {"max_size": 1}, format="json")
        assert set_up.status_code == 200 and set_up.json()["is_open"] is True
    assert (
        teacher.put(f"/api/v1/groups/{lab_a.id}/sign-up/", {"max_size": 0}, format="json").status_code == 400
    )

    listed = {g["name"]: g for g in learner.get(f"/api/v1/sites/{site.id}/my-groups/").json()}
    assert set(listed) == {"Lab A", "Lab B"} and listed["Lab A"]["places_left"] == 1
    assert len(teacher.get(f"/api/v1/sites/{site.id}/my-groups/").json()) == 3

    assert learner.post(f"/api/v1/groups/{lab_a.id}/join/").json() == {"group": lab_a.id, "member": True}
    assert learner.post(f"/api/v1/groups/{lab_a.id}/join/").json()["code"] == "already_member"
    in_set = learner.post(f"/api/v1/groups/{lab_b.id}/join/")
    assert in_set.status_code == 409 and in_set.json()["code"] == "already_in_set"
    full = classmate.post(f"/api/v1/groups/{lab_a.id}/join/")
    assert full.status_code == 409 and full.json()["code"] == "group_full"
    assert AuditLog.objects.filter(action="group_joined").count() == 1
    assert learner.get(f"/api/v1/sites/{site.id}/my-groups/").json()[0]["member"] is True

    # Groups in different groupings are different sets: one may hold one of each.
    field = SiteGroup.objects.create(site=site, name="Field 1")
    GroupSignUp.objects.create(group=field)
    Grouping.objects.create(site=site, name="Field groups").groups.add(field)
    assert learner.post(f"/api/v1/groups/{field.id}/join/").status_code == 200

    assert learner.post(f"/api/v1/groups/{lab_a.id}/leave/").json() == {"group": lab_a.id, "member": False}
    assert learner.post(f"/api/v1/groups/{lab_a.id}/leave/").json()["code"] == "not_member"
    assert learner.post(f"/api/v1/groups/{lab_b.id}/join/").status_code == 200
    teacher.put(
        f"/api/v1/groups/{lab_b.id}/sign-up/",
        {"max_size": 1, "closes_at": (timezone.now() - timedelta(minutes=1)).isoformat()},
        format="json",
    )
    closed = learner.post(f"/api/v1/groups/{lab_b.id}/leave/")
    assert closed.status_code == 409 and closed.json()["code"] == "sign_up_closed"
    assert classmate.post(f"/api/v1/groups/{lab_b.id}/join/").json()["code"] == "sign_up_closed"

    hand.members.add(Membership.objects.get(site=site, person=student))
    assert learner.post(f"/api/v1/groups/{hand.id}/leave/").json()["code"] == "not_self_sign_up"
    assert teacher.post(f"/api/v1/groups/{lab_a.id}/join/").json()["code"] == "not_a_student"
    # Leaving is refused alike (item 1.16): it was a 409 "not in this group" to the staff and the auditor.
    for client in (teacher, auditor):
        refused = client.post(f"/api/v1/groups/{field.id}/leave/")
        assert refused.status_code == 403 and refused.json()["code"] == "not_a_student"
    assert teacher.delete(f"/api/v1/groups/{lab_b.id}/sign-up/").status_code == 204
    assert teacher.delete(f"/api/v1/groups/{lab_b.id}/sign-up/").status_code == 204
    assert not GroupSignUp.objects.filter(group=lab_b).exists()
    assert lab_b.members.count() == 1  # its members stay
    assert AuditLog.objects.filter(entity="courses.groupsignup").count() >= 4
