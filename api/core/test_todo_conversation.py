"""To do and search for the conversation apps: unread messages, reported posts to review, registers of
today's classes to take, and forum threads found by title only where the forum can be seen."""

from datetime import timedelta

import pytest
from django.utils import timezone

from forums.tests import accept


def kinds(client) -> list[tuple[str, str]]:
    return [(i["kind"], i["title"]) for i in client.get("/api/v1/to-do/").json()]


@pytest.mark.django_db
def test_unread_messages_wait_in_to_do_until_read(client_for, site, student, lecturer):
    accept(student.user)
    learner, teacher = client_for(student.user), client_for(lecturer.user)
    made = learner.post(
        "/api/v1/conversations/", {"site": site.id, "subject": "Field trip", "body": "Boots?"}, format="json"
    ).json()
    assert ("message", "Field trip") in kinds(teacher)
    assert ("message", "Field trip") not in kinds(learner)  # one's own message is not waiting
    teacher.post(f"/api/v1/conversations/{made['id']}/read/")
    assert ("message", "Field trip") not in kinds(teacher)


@pytest.mark.django_db
def test_reported_posts_wait_for_the_sites_moderators(client_for, site, student, other_student, lecturer):
    from forums.models import Forum

    for person in (student, other_student):
        accept(person.user)
    forum = Forum.objects.create(site=site, title="General")
    learner = client_for(student.user)
    thread = learner.post(
        f"/api/v1/forums/{forum.id}/threads/", {"title": "Lime", "body": "<p>Advert</p>"}, format="json"
    ).json()
    post_id = learner.get(f"/api/v1/threads/{thread['id']}/").json()["posts"][0]["id"]
    client_for(other_student.user).post(
        f"/api/v1/posts/{post_id}/report/", {"reason": "Advertising"}, format="json"
    )
    teacher = client_for(lecturer.user)
    assert ("post_report", "Lime: Advertising") in kinds(teacher)
    assert not any(k == "post_report" for k, _ in kinds(learner))


@pytest.mark.django_db
def test_a_register_of_todays_class_waits_until_it_is_complete(
    client_for, site, lecturer, student, other_student
):
    from attendance.models import ClassSession

    now = timezone.now()
    session = ClassSession.objects.create(
        site=site, title="Soil lab", starts_at=now - timedelta(minutes=5), ends_at=now + timedelta(hours=1)
    )
    ClassSession.objects.create(
        site=site,
        title="Tomorrow",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=1),
    )
    teacher = client_for(lecturer.user)
    assert ("register", "Soil lab") in kinds(teacher) and ("register", "Tomorrow") not in kinds(teacher)
    assert not any(k == "register" for k, _ in kinds(client_for(student.user)))
    teacher.post(f"/api/v1/class-sessions/{session.id}/close-register/")
    assert ("register", "Soil lab") not in kinds(teacher)


@pytest.mark.django_db
def test_search_finds_threads_only_in_forums_one_can_see(client_for, site, lecturer, student, other_student):
    from courses.models import Membership, SiteGroup
    from forums.models import Forum, Thread

    general = Forum.objects.create(site=site, title="General")
    lab = Forum.objects.create(site=site, title="Lab A")
    group = SiteGroup.objects.create(site=site, name="Lab A")
    group.members.add(Membership.objects.get(site=site, person=student))
    lab.groups.add(group)
    Thread.objects.create(forum=general, title="Soil pH question")
    Thread.objects.create(forum=lab, title="Soil sample labels")
    found = client_for(student.user).get("/api/v1/search/", {"q": "soil"}).json()["threads"]
    assert [t["title"] for t in found] == ["Soil sample labels", "Soil pH question"]
    assert found[0]["link"].startswith(f"/forums/{lab.id}/threads/")
    other = client_for(other_student.user).get("/api/v1/search/", {"q": "soil"}).json()["threads"]
    assert [t["title"] for t in other] == ["Soil pH question"]
    assert len(client_for(lecturer.user).get("/api/v1/search/", {"q": "soil"}).json()["threads"]) == 2
