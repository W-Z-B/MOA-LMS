"""Who sees and moderates which forum, the conduct statement, notices of new posts, and what a graded forum
adds to coursework.

Visibility. Teaching staff, course administrators and auditors see every forum of the sites they can open.
A student sees a forum only when it is published, its module (if any) is released to them, and, when the
forum is restricted to groups, they belong to one of those groups.

Moderators are the site's teaching staff and course administrators (courses.access.can_teach). Auditors
read but never moderate.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from courses import release
from courses.access import TEACHING, can_teach, person_of, site_role
from forums.models import ConductAcceptance, ConductStatement, Forum, Post, Subscription, Thread


def edit_window() -> timedelta:
    return timedelta(minutes=settings.FORUM_EDIT_MINUTES)


def is_moderator(user, forum: Forum) -> bool:
    return can_teach(user, forum.site)


def forum_visible(user, forum: Forum, *, role: str | None = None) -> bool:
    """Whether the user sees the forum (the site's visibility is settled by the caller's queryset)."""
    role = role if role is not None else site_role(user, forum.site)
    if role is None:
        return False
    if role in (*TEACHING, "auditor"):
        return True
    if not forum.is_published:
        return False
    person = person_of(user)
    if person is None:
        return False
    state = getattr(user, "_release_state", None)
    if state is None:  # read once per request: the user object lives as long as the request
        state = user._release_state = release.student_state(person)
    if forum.module is not None and not release.released(forum.module, state):
        return False
    group_ids = {g.id for g in forum.groups.all()}
    return not group_ids or bool(group_ids & state.groups)


def visible_forums(user, forums):
    """The forums among `forums` the user sees, as a list."""
    roles: dict[int, str | None] = {}
    out = []
    for forum in forums:
        if forum.site_id not in roles:
            roles[forum.site_id] = site_role(user, forum.site)
        if forum_visible(user, forum, role=roles[forum.site_id]):
            out.append(forum)
    return out


def has_posted(user, thread: Thread) -> bool:
    """Whether the user has a post of their own in the thread that has not been removed."""
    return thread.posts.filter(author=user, deleted_at__isnull=True).exists()


def replies_hidden_until_posting(user, thread: Thread) -> bool:
    """In a question-and-answer forum a student sees others' replies only once they have replied."""
    return (
        thread.forum.forum_type == Forum.Type.QUESTION
        and not is_moderator(user, thread.forum)
        and site_role(user, thread.forum.site) != "auditor"
        and not has_posted(user, thread)
    )


# ---------------------------------------------------------------------------------------------------------
# The conduct statement


def current_statement() -> ConductStatement | None:
    return ConductStatement.objects.filter(published_at__isnull=False).order_by("-version").first()


def conduct_accepted(user) -> bool:
    """True when the person has accepted the statement in force, or none is in force."""
    statement = current_statement()
    return statement is None or ConductAcceptance.objects.filter(statement=statement, user=user).exists()


# ---------------------------------------------------------------------------------------------------------
# Notices of new posts


def subscribers(thread: Thread):
    users = get_user_model().objects.filter(
        Q(pk__in=Subscription.objects.filter(forum=thread.forum).values("user"))
        | Q(pk__in=Subscription.objects.filter(thread=thread).values("user")),
        is_active=True,
    )
    return users.distinct()


def notify_new_post(post: Post) -> int:
    """Tell the subscribers of the forum and of the thread, except the author and anyone who can no longer
    see it (left the course, outside the forum's groups, or not yet allowed to see replies)."""
    from notifications.services import notify

    thread = post.thread
    forum = thread.forum
    recipients = []
    for user in subscribers(thread).exclude(pk=post.author_id):
        if not forum_visible(user, forum):
            continue
        if post.parent_id is not None and replies_hidden_until_posting(user, thread):
            continue
        recipients.append(user)
    what = "New discussion" if post.parent_id is None else "New reply"
    notify(
        recipients,
        title=f"{forum.site.code}: {what} in {forum.title}"[:160],
        body=thread.title,
        link=f"/forums/{forum.id}/threads/{thread.id}",
        dedupe_key=f"forum-post:{post.id}",
    )
    return len(recipients)


def moderators(forum: Forum):
    """The teaching staff of the forum's site, who review reports."""
    from courses.models import Membership

    return (
        get_user_model()
        .objects.filter(
            is_active=True,
            person__memberships__site=forum.site,
            person__memberships__is_active=True,
            person__memberships__role__in=[Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT],
        )
        .distinct()
    )


# ---------------------------------------------------------------------------------------------------------
# Graded discussion and coursework (item 4.10)


def coursework_items(
    site, student, *, released_only: bool = False, now=None
) -> list[tuple[Decimal, Decimal | None]]:
    """What each graded forum that counts (published, graded, weight above 0) adds to the student's
    coursework, as (weight, fraction): the fraction is the participation mark over the forum's maximum,
    capped at 1; None while no mark has been given (or, when released_only, while it is not released). As
    practicals.services.coursework_items, meant to be added to assessments.services.coursework_percent's
    items: sum(weight * fraction) / sum(weight) over the items whose fraction is not None.
    """
    from forums.models import ParticipationMark

    forums = site.forums.filter(is_published=True, forum_type=Forum.Type.GRADED, weight__gt=0)
    marks = {m.forum_id: m for m in ParticipationMark.objects.filter(forum__in=forums, student=student)}
    items: list[tuple[Decimal, Decimal | None]] = []
    for forum in forums:
        mark = marks.get(forum.id)
        if mark is None or (released_only and not mark.is_released):
            items.append((forum.weight, None))
        else:
            items.append((forum.weight, min(mark.mark / forum.max_mark, Decimal(1))))
    return items


def touch_thread(thread: Thread, when=None) -> None:
    thread.last_post_at = when or timezone.now()
    thread.save(update_fields=["last_post_at", "updated_at"])
