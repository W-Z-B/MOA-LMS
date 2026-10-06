"""To do (items 2.07 to 2.09): everything waiting for one person, from every module, oldest first.

Each source asks only what that person may act on, by the same rules its own screen uses, and the list
links to where it is done: work to mark and logbooks to sign off on the sites they teach, takedown
requests and correction requests for course administrators, disposals for the keepers of records, forum
posts reported on the forums they moderate, the register of today's classes they teach, unread messages,
and, for a student, work due soon and logbook entries handed back. Something that has waited past its time
limit, or work past its due date, is marked overdue.
Staff development adds requests to join a course for those who decide them, required training falling
due, and, for administrators, people still to be invited to an account (items 1.22, 5.02, 5.05).
Help requests waiting for an answer go to course administrators and administrators (item 7.17).
"""

from datetime import datetime

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from core.home import student_work, to_mark
from core.serializers import ErrorSerializer
from courses.access import person_of
from iam.permissions import RolePermission
from iam.services import SITE_ADMIN_ROLES, has_role

MARKING_NAMES = {
    "submission": "Work to mark",
    "quiz_answer": "Quiz answers to mark",
    "observation": "Observations to release",
    "logbook": "Logbook entries to sign off",
}


def waited(since: datetime, today) -> int:
    """Calendar days from `since` to today; nothing for something not yet due."""
    return max((today - timezone.localtime(since).date()).days, 0)


def _item(
    kind: str,
    kind_name: str,
    title: str,
    since: datetime,
    link: str,
    *,
    limit: int | None = None,
    due_at: datetime | None = None,
    site_title: str = "",
) -> dict:
    days = waited(since, timezone.localdate())
    return {
        "kind": kind,
        "kind_name": kind_name,
        "title": title,
        "since": since,
        "due_at": due_at,
        "waited_days": days,
        "overdue": limit is not None and days >= limit,
        "link": link,
        "site_title": site_title,
    }


def _marking(person) -> list[dict]:
    if person is None:
        return []
    return [
        _item(
            row["kind"],
            MARKING_NAMES[row["kind"]],
            row["title"],
            row["oldest"],
            row["link"],
            limit=settings.MARKING_DAYS,
            site_title=row["site_title"],
        )
        for row in to_mark(person)
    ]


def _shorten(text: str, length: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


def _takedowns(user) -> list[dict]:
    """Open takedown requests, for those who decide them (courses.api.TakedownViewSet)."""
    from courses.models import TakedownRequest

    if not has_role(user, *SITE_ADMIN_ROLES):
        return []
    open_ = TakedownRequest.objects.filter(status=TakedownRequest.Status.OPEN).select_related(
        "item__module__site"
    )
    return [
        _item(
            "takedown",
            "Takedown request to review",
            f"{t.item.title}: {_shorten(t.reason)}",
            t.created_at,
            f"/sites/{t.item.module.site_id}",
            limit=settings.DECISION_DAYS,
            site_title=t.item.module.site.title,
        )
        for t in open_
    ]


def _corrections(user) -> list[dict]:
    from privacy.models import CorrectionRequest
    from privacy.views import CORRECTION_DECIDE

    if not has_role(user, *CORRECTION_DECIDE):
        return []
    open_ = CorrectionRequest.objects.filter(state=CorrectionRequest.State.OPEN).exclude(person__user=user)
    today = timezone.localdate()
    items = []
    for c in open_.select_related("person"):
        item = _item(
            "correction",
            "Correction to answer",
            f"{c.person.full_name}: {c.get_subject_display().lower()}",
            c.created_at,
            "/admin/corrections",
        )
        item["overdue"] = today > c.due_by
        items.append(item)
    return items


def _disposals(user) -> list[dict]:
    from privacy.models import DisposalRun
    from privacy.retention_views import KEEPERS

    if not has_role(user, *KEEPERS):
        return []
    runs = DisposalRun.objects.filter(state=DisposalRun.State.PROPOSED).exclude(created_by=user)
    return [
        _item(
            "disposal",
            "Disposal to approve",
            f"Records due under: {run.rule.name}",
            run.created_at,
            "/admin/retention",
            limit=settings.DECISION_DAYS,
        )
        for run in runs.select_related("rule")
    ]


def _messages(user) -> list[dict]:
    """Conversations with messages from others not yet read (messaging), oldest unread first."""
    from django.db.models import F, Min, Q

    from messaging.models import Conversation

    unread = (
        Conversation.objects.filter(participants__user=user)
        .annotate(
            oldest=Min(
                "messages__created_at",
                filter=~Q(messages__sender=user)
                & (
                    Q(participants__last_read_at__isnull=True)
                    | Q(messages__created_at__gt=F("participants__last_read_at"))
                ),
            )
        )
        .filter(oldest__isnull=False)
        .select_related("site")
    )
    return [
        _item("message", "Unread message", c.subject, c.oldest, f"/messages/{c.id}", site_title=c.site.title)
        for c in unread
    ]


def _reports(user) -> list[dict]:
    """Open reports of forum posts on the sites the person moderates (forums.api.PostReportViewSet)."""
    from courses.access import taught_sites
    from forums.models import PostReport

    open_ = PostReport.objects.filter(
        status=PostReport.Status.OPEN, post__thread__forum__site__in=taught_sites(user)
    ).select_related("post__thread__forum__site")
    return [
        _item(
            "post_report",
            "Reported post to review",
            f"{r.post.thread.title}: {_shorten(r.reason)}",
            r.created_at,
            f"/forums/{r.post.thread.forum_id}/threads/{r.post.thread_id}",
            limit=settings.DECISION_DAYS,
            site_title=r.post.thread.forum.site.title,
        )
        for r in open_
    ]


def _registers(person) -> list[dict]:
    """Today's classes, on the sites the person teaches, that have started and whose register is not
    complete (attendance)."""
    from attendance.models import ClassSession
    from attendance.services import expected
    from courses.models import Membership

    if person is None:
        return []
    now = timezone.now()
    start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    teaching = Membership.objects.filter(
        person=person, is_active=True, role__in=[Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT]
    ).values("site_id")
    sessions = ClassSession.objects.filter(
        site_id__in=teaching, takes_attendance=True, starts_at__gte=start, starts_at__lte=now
    ).select_related("site")
    items = []
    for session in sessions:
        if session.records.count() < expected(session).count():
            items.append(
                _item(
                    "register",
                    "Register to take",
                    session.title,
                    session.starts_at,
                    f"/sites/{session.site_id}/classes/{session.id}",
                    site_title=session.site.title,
                )
            )
    return items


def _student(person) -> list[dict]:
    """Work due within the week, overdue work that can still be handed in, and logbook entries returned."""
    from practicals.models import LogbookEntry

    if person is None:
        return []
    now = timezone.now()
    due, overdue = student_work(person, now)
    items = []
    for work in [*due, *(w for w in overdue if w["can_still_submit"])]:
        item = _item(
            work["kind"], "Work due", work["title"], work["due_at"], work["link"], due_at=work["due_at"]
        )
        item["site_title"] = work["site_title"]
        item["overdue"] = work["due_at"] < now
        items.append(item)
    returned = LogbookEntry.objects.filter(
        student=person, status=LogbookEntry.Status.RETURNED, site__is_published=True
    ).select_related("site")
    for entry in returned:
        items.append(
            _item(
                "logbook_returned",
                "Logbook entry returned",
                f"{entry.work_date:%d/%m/%Y}: {entry.task}",
                entry.reviewed_at or entry.updated_at,
                f"/sites/{entry.site_id}/logbook",
                site_title=entry.site.title,
            )
        )
    return items


def _enrolments(user) -> list[dict]:
    """Requests to join a staff-development course that the person decides: as the supervisor, standing in
    for one, or as a course administrator when there is no supervisor (approvals.inbox, item 5.02)."""
    from approvals.inbox import waiting_for

    return [
        _item(
            row["kind"],
            row["kind_name"],
            row["title"] + (f" ({row['for_whom']})" if row["for_whom"] else ""),
            row["since"],
            row["link"],
            limit=settings.DECISION_DAYS,
        )
        for row in waiting_for(user)
    ]


def _required_training(person) -> list[dict]:
    """Required training due within the reminder days, or overdue (item 5.05)."""
    from datetime import time, timedelta

    from staffdev.models import TrainingAssignment

    if person is None:
        return []
    soon = timezone.localdate() + timedelta(days=settings.REQUIRED_TRAINING_REMIND_DAYS)
    open_ = TrainingAssignment.objects.filter(
        person=person, completed_on__isnull=True, requirement__is_active=True, due_on__lte=soon
    ).select_related("requirement__site")
    items = []
    for row in open_:
        due = timezone.make_aware(datetime.combine(row.due_on, time.max))
        site = row.requirement.site
        item = _item(
            "required_training", "Required training", site.title, due, f"/sites/{site.id}", due_at=due
        )
        item["site_title"] = site.title
        item["overdue"] = row.due_on < timezone.localdate()
        items.append(item)
    return items


def _help_requests(user) -> list[dict]:
    """Help requests waiting for an answer, for those who answer them (helpdesk.api, item 7.17)."""
    from helpdesk.models import HelpRequest

    if not has_role(user, *SITE_ADMIN_ROLES):
        return []
    waiting = HelpRequest.objects.filter(status=HelpRequest.Status.OPEN).exclude(asked_by=user)
    return [
        _item(
            "help_request",
            "Help request to answer",
            _shorten(h.subject),
            h.created_at,
            f"/help/requests/{h.pk}",
            limit=2,
        )
        for h in waiting.order_by("created_at")[:50]
    ]


def _accounts(user) -> list[dict]:
    """People with no account who have not been invited to choose a password, for administrators (1.22)."""
    from iam.accounts import uninvited
    from iam.models import Role

    if not has_role(user, Role.ADMINISTRATOR):
        return []
    waiting = uninvited().filter(user__isnull=True)
    oldest = waiting.order_by("created_at").first()
    if oldest is None:
        return []
    count = waiting.count()
    title = f"{count} {'person has' if count == 1 else 'people have'} no account yet: invite them"
    return [_item("accounts", "Accounts to open", title, oldest.created_at, "/admin/accounts")]


def to_do_for(user) -> list[dict]:
    """Everything waiting for the user, by due date where there is one and otherwise by how long it has
    waited, oldest first."""
    person = person_of(user)
    items = [
        *_marking(person),
        *_takedowns(user),
        *_corrections(user),
        *_disposals(user),
        *_reports(user),
        *_registers(person),
        *_messages(user),
        *_student(person),
        *_enrolments(user),
        *_required_training(person),
        *_accounts(user),
        *_help_requests(user),
    ]
    return sorted(items, key=lambda item: item["due_at"] or item["since"])


class ToDoItemSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=[
            "submission",
            "quiz_answer",
            "observation",
            "logbook",
            "takedown",
            "correction",
            "disposal",
            "assignment",
            "quiz",
            "logbook_returned",
            "post_report",
            "register",
            "message",
            "enrolment",
            "required_training",
            "accounts",
            "help_request",
        ]
    )
    kind_name = serializers.CharField(help_text="What it is, in words: 'Work to mark', 'Work due'")
    title = serializers.CharField()
    since = serializers.DateTimeField(help_text="Waiting since; for work due, the due date")
    due_at = serializers.DateTimeField(allow_null=True, help_text="When work is due; null for the rest")
    waited_days = serializers.IntegerField(help_text="Calendar days it has waited; 0 for work not yet due")
    overdue = serializers.BooleanField(help_text="Waited past its time limit, or past its due date")
    link = serializers.CharField(help_text="Where it is done, in the web app")
    site_title = serializers.CharField(help_text="The course it belongs to; empty when none")


@extend_schema(
    responses={200: ToDoItemSerializer(many=True), 403: ErrorSerializer},
    summary="Everything waiting for me, oldest first",
)
@api_view(["GET"])
@permission_classes([RolePermission])
def to_do(request):
    return Response(ToDoItemSerializer(to_do_for(request.user), many=True).data)
