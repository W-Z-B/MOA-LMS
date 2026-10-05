"""Discussion forums (items 4.08 to 4.10): who sees which forum, question-and-answer rules, the edit window,
moderation and reports, the conduct statement, subscriptions and graded discussion."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from audit.models import AuditLog
from forums.models import ConductAcceptance, ConductStatement, Forum, Post, PostReport
from notifications.models import Notification


def accept(user):
    from forums.services import current_statement

    ConductAcceptance.objects.get_or_create(statement=current_statement(), user=user)


@pytest.fixture
def teacher(client_for, lecturer):
    accept(lecturer.user)
    return client_for(lecturer.user)


@pytest.fixture
def learner(client_for, student):
    accept(student.user)
    return client_for(student.user)


@pytest.fixture
def classmate(client_for, other_student):
    accept(other_student.user)
    return client_for(other_student.user)


@pytest.fixture
def make_forum(site):
    def _make(**fields):
        return Forum.objects.create(site=site, title=fields.pop("title", "Crop questions"), **fields)

    return _make


def start(client, forum, title="Spacing of tomato plants", body="<p>How far apart?</p>"):
    return client.post(f"/api/v1/forums/{forum.id}/threads/", {"title": title, "body": body}, format="json")


def reply(client, thread_id, body="<p>Forty-five centimetres.</p>", **extra):
    return client.post(f"/api/v1/threads/{thread_id}/replies/", {"body": body, **extra}, format="json")


@pytest.mark.django_db
def test_the_first_conduct_statement_is_published_and_names_the_cybercrime_act():
    statement = ConductStatement.objects.get()
    assert statement.version == 1 and statement.published_at is not None
    assert "may be an offence under the Cybercrime Act 2018" in statement.body


@pytest.mark.django_db
def test_teaching_staff_make_forums_and_students_see_only_those_open_to_them(
    site, teacher, learner, classmate, student, make_forum
):
    made = teacher.post(
        "/api/v1/forums/",
        {"site": site.id, "title": "General", "description": "<p>Ask <script>x</script>here</p>"},
        format="json",
    )
    assert made.status_code == 201 and made.json()["description"] == "<p>Ask here</p>"
    assert AuditLog.objects.filter(entity="forums.forum", action="create").exists()
    assert (
        learner.post("/api/v1/forums/", {"site": site.id, "title": "Mine"}, format="json").status_code == 403
    )

    from courses.models import Membership, Module, SiteGroup

    hidden = make_forum(title="Draft", is_published=False)
    group = SiteGroup.objects.create(site=site, name="Lab group A")
    group.members.add(Membership.objects.get(site=site, person=student))
    lab = make_forum(title="Lab A")
    lab.groups.add(group)
    later = Module.objects.create(
        site=site, title="Week 9", available_from=timezone.now() + timedelta(days=3)
    )
    module_forum = make_forum(title="Week 9 forum", module=later)

    mine = {f["title"] for f in learner.get(f"/api/v1/forums/?site={site.id}").json()}
    assert mine == {"General", "Lab A"}
    theirs = {f["title"] for f in classmate.get("/api/v1/forums/").json()}
    assert theirs == {"General"}
    for forum in (hidden, lab, module_forum):
        assert classmate.get(f"/api/v1/forums/{forum.id}/").status_code == 404
    assert len(teacher.get("/api/v1/forums/").json()) == 4


@pytest.mark.django_db
def test_forum_fields_are_checked(site, teacher, make_forum):
    from courses.models import CourseSite, Module

    other = CourseSite.objects.create(code="AGR999", title="Other", is_published=True)
    module = Module.objects.create(site=other, title="Elsewhere")
    wrong = teacher.post(
        "/api/v1/forums/", {"site": site.id, "title": "x", "module": module.id}, format="json"
    )
    assert wrong.status_code == 400
    weighted = teacher.post("/api/v1/forums/", {"site": site.id, "title": "x", "weight": "2"}, format="json")
    assert weighted.status_code == 400 and "weight" in weighted.json()
    graded = teacher.post(
        "/api/v1/forums/",
        {"site": site.id, "title": "Graded", "forum_type": "graded", "weight": "2", "rubric_id": 7},
        format="json",
    )
    assert graded.status_code == 201 and graded.json()["rubric_id"] == 7
    forum = make_forum()
    moved = teacher.patch(f"/api/v1/forums/{forum.id}/", {"site": other.id}, format="json")
    assert moved.status_code in (400, 403)


@pytest.mark.django_db
def test_nobody_posts_before_accepting_the_conduct_statement(make_forum, client_for, student, course_admin):
    forum = make_forum()
    learner = client_for(student.user)
    refused = start(learner, forum)
    assert refused.status_code == 403 and refused.json()["code"] == "conduct_not_accepted"
    current = learner.get("/api/v1/conduct-statements/current/").json()
    assert current["accepted"] is False and current["statement"]["version"] == 1
    assert learner.post("/api/v1/conduct-statements/current/accept/").json()["accepted"] is True
    assert AuditLog.objects.filter(action="conduct_accepted").count() == 1
    assert start(learner, forum).status_code == 201

    # A new version must be accepted again; only course administrators write and publish one.
    assert (
        learner.post("/api/v1/conduct-statements/", {"body": "New rules"}, format="json").status_code == 403
    )
    admin = client_for(course_admin)
    draft = admin.post("/api/v1/conduct-statements/", {"body": "Version two"}, format="json").json()
    assert draft["version"] == 2 and draft["published_at"] is None
    assert (
        admin.patch(f"/api/v1/conduct-statements/{draft['id']}/", {"body": "V2"}, format="json").status_code
        == 200
    )
    assert admin.post(f"/api/v1/conduct-statements/{draft['id']}/publish/").status_code == 200
    again = admin.post(f"/api/v1/conduct-statements/{draft['id']}/publish/")
    assert again.status_code == 409 and again.json()["code"] == "already_published"
    assert (
        admin.patch(f"/api/v1/conduct-statements/{draft['id']}/", {"body": "V3"}, format="json").status_code
        == 400
    )
    assert start(learner, forum).json()["code"] == "conduct_not_accepted"
    assert learner.get("/api/v1/conduct-statements/current/").json()["statement"]["version"] == 2


@pytest.mark.django_db
def test_without_a_statement_in_force_posting_is_not_blocked(make_forum, client_for, student):
    ConductStatement.objects.update(published_at=None)
    learner = client_for(student.user)
    assert learner.get("/api/v1/conduct-statements/current/").json() == {"statement": None, "accepted": False}
    assert learner.post("/api/v1/conduct-statements/current/accept/").json()["code"] == "no_statement"
    assert start(learner, make_forum()).status_code == 201


@pytest.mark.django_db
def test_a_general_forum_has_threads_and_threaded_replies(make_forum, teacher, learner, classmate):
    forum = make_forum()
    thread = start(learner, forum).json()
    assert thread["author_name"] == "Ravi Singh"
    first = reply(classmate, thread["id"]).json()
    nested = reply(teacher, thread["id"], parent=first["id"]).json()
    assert nested["parent"] == first["id"]
    detail = learner.get(f"/api/v1/threads/{thread['id']}/").json()
    assert [p["parent"] for p in detail["posts"]] == [None, detail["posts"][0]["id"], first["id"]]
    assert detail["replies_hidden"] is False and detail["subscribed"] is True
    listed = learner.get(f"/api/v1/forums/{forum.id}/threads/").json()
    assert listed[0]["replies"] == 2
    bad_parent = reply(learner, thread["id"], parent=999999)
    assert bad_parent.status_code == 400
    assert reply(learner, thread["id"], body="<p> </p>").status_code == 400


@pytest.mark.django_db
def test_question_and_answer_students_see_replies_only_after_replying(
    make_forum, teacher, learner, classmate
):
    forum = make_forum(forum_type=Forum.Type.QUESTION)
    refused = start(learner, forum)
    assert refused.status_code == 403
    thread = start(teacher, forum, title="Why lime acid soils?").json()
    reply(classmate, thread["id"], body="<p>To raise the pH.</p>")
    before = learner.get(f"/api/v1/threads/{thread['id']}/").json()
    assert before["replies_hidden"] is True and len(before["posts"]) == 1
    hidden_post = Post.objects.get(body="<p>To raise the pH.</p>")
    assert (
        learner.post(f"/api/v1/posts/{hidden_post.id}/report/", {"reason": "x"}, format="json").status_code
        == 404
    )
    assert reply(learner, thread["id"], parent=hidden_post.id).status_code == 400
    assert reply(learner, thread["id"], body="<p>Calcium.</p>").status_code == 201
    after = learner.get(f"/api/v1/threads/{thread['id']}/").json()
    assert after["replies_hidden"] is False and len(after["posts"]) == 3
    assert teacher.get(f"/api/v1/threads/{thread['id']}/").json()["replies_hidden"] is False


@pytest.mark.django_db
def test_authors_change_or_remove_their_own_post_for_thirty_minutes(make_forum, learner, classmate, teacher):
    forum = make_forum()
    thread = start(learner, forum).json()
    post = Post.objects.get(thread_id=thread["id"])
    changed = learner.patch(
        f"/api/v1/posts/{post.id}/", {"body": "<p>How far apart, in rows?</p>"}, format="json"
    )
    assert changed.status_code == 200 and changed.json()["edited_at"] and changed.json()["can_edit"]
    assert (
        classmate.patch(f"/api/v1/posts/{post.id}/", {"body": "<p>x</p>"}, format="json").status_code == 403
    )
    assert teacher.patch(f"/api/v1/posts/{post.id}/", {"body": "<p>x</p>"}, format="json").status_code == 403
    Post.objects.filter(pk=post.pk).update(created_at=timezone.now() - timedelta(minutes=31))
    late = learner.patch(f"/api/v1/posts/{post.id}/", {"body": "<p>x</p>"}, format="json")
    assert late.status_code == 409 and late.json()["code"] == "edit_window_closed"
    late_remove = learner.post(f"/api/v1/posts/{post.id}/remove/", {}, format="json")
    assert late_remove.json()["code"] == "edit_window_closed"

    mine = reply(learner, thread["id"]).json()
    removed = learner.post(f"/api/v1/posts/{mine['id']}/remove/", {}, format="json").json()
    assert removed["removed"] is True and removed["removed_reason"] == "Removed by the author."
    again = learner.post(f"/api/v1/posts/{mine['id']}/remove/", {}, format="json")
    assert again.status_code == 409 and again.json()["code"] == "removed"
    assert learner.patch(f"/api/v1/posts/{mine['id']}/", {"body": "<p>y</p>"}, format="json").json()[
        "code"
    ] == ("removed")


@pytest.mark.django_db
def test_moderators_remove_posts_with_a_reason_and_pin_and_lock_threads(
    make_forum, teacher, learner, classmate, client_for, course_admin
):
    forum = make_forum()
    thread = start(learner, forum).json()
    rude = reply(classmate, thread["id"], body="<p>Rude words</p>").json()
    assert (
        learner.post(f"/api/v1/posts/{rude['id']}/remove/", {"reason": "x"}, format="json").status_code == 403
    )
    no_reason = teacher.post(f"/api/v1/posts/{rude['id']}/remove/", {}, format="json")
    assert no_reason.status_code == 400
    done = teacher.post(f"/api/v1/posts/{rude['id']}/remove/", {"reason": "Breaks the rules"}, format="json")
    assert done.json()["removed"] is True
    entry = AuditLog.objects.get(entity="forums.post", entity_id=rude["id"], action="moderate")
    assert entry.reason == "Breaks the rules"
    seen = {p["id"]: p for p in learner.get(f"/api/v1/threads/{thread['id']}/").json()["posts"]}
    assert seen[rude["id"]]["body"] == "" and seen[rude["id"]]["removed_reason"] is None
    own = {p["id"]: p for p in classmate.get(f"/api/v1/threads/{thread['id']}/").json()["posts"]}
    assert own[rude["id"]]["removed_reason"] == "Breaks the rules"

    for verb in ("pin", "lock"):
        assert learner.post(
            f"/api/v1/threads/{thread['id']}/{verb}/", {"value": True}, format="json"
        ).status_code == (403)
    assert teacher.post(f"/api/v1/threads/{thread['id']}/pin/", {"value": True}, format="json").json()[
        "is_pinned"
    ]
    other = start(classmate, forum, title="Later thread").json()
    assert learner.get(f"/api/v1/forums/{forum.id}/threads/").json()[0]["id"] == thread["id"]
    admin = client_for(course_admin)
    accept(course_admin)
    assert admin.post(f"/api/v1/threads/{other['id']}/lock/", {"value": True}, format="json").json()[
        "is_locked"
    ]
    locked = reply(learner, other["id"])
    assert locked.status_code == 409 and locked.json()["code"] == "thread_locked"
    assert reply(teacher, other["id"]).status_code == 201
    assert AuditLog.objects.filter(entity="forums.thread", action="moderate").count() == 2


@pytest.mark.django_db
def test_a_report_by_teaching_staff_hides_a_post_at_once_but_a_students_waits(
    make_forum, teacher, learner, classmate, lecturer
):
    forum = make_forum()
    thread = start(learner, forum).json()
    post = reply(classmate, thread["id"], body="<p>Off-topic advert</p>").json()

    by_student = learner.post(f"/api/v1/posts/{post['id']}/report/", {"reason": "Advertising"}, format="json")
    assert by_student.status_code == 201 and by_student.json()["status"] == "open"
    assert Post.objects.get(pk=post["id"]).is_hidden is False
    assert Notification.objects.filter(
        recipient=lecturer.user, dedupe_key__startswith="post-report:"
    ).exists()
    assert (
        learner.post(
            f"/api/v1/post-reports/{by_student.json()['id']}/review/", {"decision": "remove"}, format="json"
        ).status_code
        == 403
    )
    assert [r["id"] for r in learner.get("/api/v1/post-reports/").json()["results"]] == [
        by_student.json()["id"]
    ]

    by_staff = teacher.post(f"/api/v1/posts/{post['id']}/report/", {"reason": "Advertising"}, format="json")
    assert by_staff.status_code == 201 and Post.objects.get(pk=post["id"]).is_hidden is True
    shown = {p["id"]: p for p in learner.get(f"/api/v1/threads/{thread['id']}/").json()["posts"]}
    assert shown[post["id"]]["body"] == "" and shown[post["id"]]["hidden"] is True
    assert {p["id"]: p for p in classmate.get(f"/api/v1/threads/{thread['id']}/").json()["posts"]}[
        post["id"]
    ]["body"] == "<p>Off-topic advert</p>"
    assert (
        learner.post(f"/api/v1/posts/{post['id']}/report/", {"reason": "x"}, format="json").status_code == 404
    )

    kept = teacher.post(
        f"/api/v1/post-reports/{by_staff.json()['id']}/review/", {"decision": "keep"}, format="json"
    )
    assert kept.json()["status"] == "restored"
    assert PostReport.objects.filter(post_id=post["id"], status="open").count() == 0
    assert Post.objects.get(pk=post["id"]).is_hidden is False
    decided = teacher.post(
        f"/api/v1/post-reports/{by_staff.json()['id']}/review/", {"decision": "remove"}, format="json"
    )
    assert decided.status_code == 409 and decided.json()["code"] == "already_decided"

    again = learner.post(
        f"/api/v1/posts/{post['id']}/report/", {"reason": "Still advertising"}, format="json"
    ).json()
    removed = teacher.post(
        f"/api/v1/post-reports/{again['id']}/review/", {"decision": "remove", "note": "Advert"}, format="json"
    )
    assert removed.json()["status"] == "removed" and Post.objects.get(pk=post["id"]).delete_reason == "Advert"
    gone = learner.post(f"/api/v1/posts/{post['id']}/report/", {"reason": "x"}, format="json")
    assert gone.status_code == 409
    assert AuditLog.objects.filter(entity="forums.postreport", action="review").count() == 3


@pytest.mark.django_db
def test_subscribers_are_told_of_new_posts_they_may_see(
    make_forum, teacher, learner, classmate, other_student, student, site
):
    forum = make_forum()
    assert classmate.post(f"/api/v1/forums/{forum.id}/subscribe/").json() == {"subscribed": True}
    assert classmate.get(f"/api/v1/forums/{forum.id}/").json()["subscribed"] is True
    thread = start(learner, forum).json()
    assert (
        Notification.objects.filter(recipient=other_student.user, title__contains="New discussion").count()
        == 1
    )
    assert not Notification.objects.filter(recipient=student.user).exists()
    reply(teacher, thread["id"])
    assert (
        Notification.objects.filter(recipient=student.user, title__contains="New reply").count() == 1
    )  # author
    assert classmate.post(f"/api/v1/forums/{forum.id}/unsubscribe/").json() == {"subscribed": False}
    assert learner.post(f"/api/v1/threads/{thread['id']}/unsubscribe/").json() == {"subscribed": False}
    reply(teacher, thread["id"])
    assert Notification.objects.filter(recipient=student.user).count() == 1
    assert learner.post(f"/api/v1/threads/{thread['id']}/subscribe/").json() == {"subscribed": True}

    # A subscriber who cannot see the forum (outside its groups) is not told; nor, in a question-and-answer
    # forum, a student of replies they cannot see yet.
    from courses.models import SiteGroup

    lab = make_forum(title="Lab only")
    lab.groups.add(SiteGroup.objects.create(site=site, name="Lab B"))
    from forums.models import Subscription

    Subscription.objects.create(user=other_student.user, forum=lab)
    start(teacher, lab)
    assert not Notification.objects.filter(recipient=other_student.user, title__contains="Lab only").exists()
    qa = make_forum(title="Q and A", forum_type=Forum.Type.QUESTION)
    Subscription.objects.create(user=other_student.user, forum=qa)
    question = start(teacher, qa).json()
    reply(learner, question["id"])
    assert (
        Notification.objects.filter(
            recipient=other_student.user, title__contains="New discussion in Q"
        ).count()
        == 1
    )
    assert not Notification.objects.filter(
        recipient=other_student.user, title__contains="New reply in Q"
    ).exists()


@pytest.mark.django_db
def test_auditors_read_but_do_not_post(make_forum, make_user, client_for, learner):
    forum = make_forum()
    thread = start(learner, forum).json()
    auditor = make_user("auditor.one", "auditor")
    accept(auditor)
    reader = client_for(auditor)
    assert reader.get(f"/api/v1/threads/{thread['id']}/").status_code == 200
    assert start(reader, forum).status_code == 403
    assert reply(reader, thread["id"]).status_code == 403


@pytest.mark.django_db
def test_a_graded_forum_counts_in_coursework_by_the_participation_mark(
    site, make_forum, teacher, learner, student, other_student
):
    from forums.services import coursework_items

    plain = make_forum()
    assert teacher.get(f"/api/v1/forums/{plain.id}/marks/").json()["code"] == "not_graded"
    forum = make_forum(
        title="Graded debate",
        forum_type=Forum.Type.GRADED,
        weight=Decimal(2),
        max_mark=Decimal(10),
        rubric_id=4,
    )
    make_forum(title="Practice", forum_type=Forum.Type.GRADED, weight=Decimal(0))
    start(learner, forum)
    assert coursework_items(site, student) == [(Decimal(2), None)]

    body = {"student": student.id, "mark": "8", "feedback": "Well argued"}
    assert learner.post(f"/api/v1/forums/{forum.id}/marks/", body, format="json").status_code == 403
    too_high = teacher.post(f"/api/v1/forums/{forum.id}/marks/", {**body, "mark": "11"}, format="json")
    assert too_high.status_code == 400
    from people.models import PersonRef

    outsider = PersonRef.objects.create(
        kind="student", external_id="26MRP0999", first_name="A", last_name="B"
    )
    assert (
        teacher.post(
            f"/api/v1/forums/{forum.id}/marks/", {**body, "student": outsider.id}, format="json"
        ).status_code
        == 400
    )
    given = teacher.post(f"/api/v1/forums/{forum.id}/marks/", body, format="json").json()
    assert given["mark"] == "8.00" and given["posts"] == 1 and given["rubric_id"] == 4
    assert AuditLog.objects.filter(entity="forums.participationmark", action="mark").count() == 1
    assert coursework_items(site, student) == [(Decimal(2), Decimal("0.8"))]
    assert coursework_items(site, student, released_only=True) == [(Decimal(2), None)]
    rows = teacher.get(f"/api/v1/forums/{forum.id}/marks/").json()
    assert {r["name"] for r in rows} == {"Ravi Singh", "Devi Ramnarine"}
    assert learner.get(f"/api/v1/forums/{forum.id}/marks/").json()[0]["mark"] is None

    assert learner.post(f"/api/v1/forums/{forum.id}/release-marks/").status_code == 403
    assert teacher.post(f"/api/v1/forums/{forum.id}/release-marks/").json() == {"released": 1}
    assert Notification.objects.filter(recipient=student.user, dedupe_key__startswith="forum-mark:").exists()
    mine = learner.get(f"/api/v1/forums/{forum.id}/marks/").json()
    assert len(mine) == 1 and mine[0]["mark"] == "8.00" and mine[0]["feedback"] == "Well argued"
    assert coursework_items(site, student, released_only=True) == [(Decimal(2), Decimal("0.8"))]
    teacher.post(f"/api/v1/forums/{forum.id}/marks/", {**body, "mark": "10"}, format="json")
    ParticipationMark = forum.marks.model
    ParticipationMark.objects.filter(forum=forum).update(mark=Decimal(12))
    assert coursework_items(site, student) == [(Decimal(2), Decimal(1))]  # capped at the maximum


@pytest.mark.django_db
def test_a_picture_in_a_post_must_be_a_file_of_the_course(make_forum, learner):
    forum = make_forum()
    body = '<p>See</p><img src="/api/v1/content/999999/download/" alt="A leaf">'
    refused = start(learner, forum, body=body)
    assert refused.status_code == 400
    no_alt = start(learner, forum, body='<img src="/api/v1/content/1/download/">')
    assert no_alt.status_code == 400
    text = learner.post(
        f"/api/v1/forums/{forum.id}/threads/",
        {"title": "Plain", "body": "Line one\n\nLine two", "body_format": "text"},
        format="json",
    )
    assert text.status_code == 201
    assert Post.objects.get(thread_id=text.json()["id"]).body == "<p>Line one</p><p>Line two</p>"


@pytest.mark.django_db
def test_forums_of_a_site_one_cannot_open_are_unknown(make_forum, client_for, make_person):
    outsider = make_person("student", "26MRP0500", "Out", "Sider", "student")
    accept(outsider.user)
    stranger = client_for(outsider.user)
    forum = make_forum()
    assert stranger.get(f"/api/v1/forums/{forum.id}/").status_code == 404
    assert start(stranger, forum).status_code == 404
    assert stranger.get("/api/v1/forums/").json() == []
