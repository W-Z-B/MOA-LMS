"""To do (items 2.07 to 2.09): everything waiting for one person, from every module, oldest first.

Each source asks only what that person may act on, by the same rules its own screen uses, and the list
links to where it is done: work to mark and logbooks to sign off on the sites they teach, takedown
requests and correction requests for course administrators, disposals for the keepers of records, and,
for a student, work due soon and logbook entries handed back. Something that has waited past its time
limit, or work past its due date, is marked overdue.
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


def to_do_for(user) -> list[dict]:
    """Everything waiting for the user, by due date where there is one and otherwise by how long it has
    waited, oldest first."""
    person = person_of(user)
    items = [
        *_marking(person),
        *_takedowns(user),
        *_corrections(user),
        *_disposals(user),
        *_student(person),
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
