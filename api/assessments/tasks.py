"""Reminders before a due date (item 2.34): every hour, a student who has not handed in is reminded 48 hours
and again 24 hours before their own due date (extensions and accommodations included). Each reminder is
sent once: the notification's dedupe key carries the assignment, the student's due date and the window, so
a run that repeats sends nothing twice and a new due date reminds again."""

import logging
from datetime import timedelta

from django.utils import timezone
from procrastinate.contrib.django import app

log = logging.getLogger(__name__)
WINDOWS = ((24, "24h"), (48, "48h"))  # the nearest window first: inside 24 hours only that one is sent


def send_due_reminders(now=None) -> int:
    from assessments.models import Assignment, Submission
    from assessments.rules import due_for
    from courses.models import Membership
    from notifications.models import Notification
    from notifications.services import notify

    now = now or timezone.now()
    sent = 0
    # Extensions and accommodations can move a due date up to some weeks; look that far back.
    candidates = Assignment.objects.filter(
        is_published=True, site__is_published=True, due_at__gt=now - timedelta(days=90)
    ).select_related("site")
    for assignment in candidates:
        handed_in = set(Submission.objects.filter(assignment=assignment).values_list("student_id", flat=True))
        students = Membership.objects.filter(
            site=assignment.site, role=Membership.SiteRole.STUDENT, is_active=True, person__user__isnull=False
        ).select_related("person__user")
        for membership in students:
            person = membership.person
            if person.id in handed_in:
                continue
            due = due_for(assignment, person).at
            left = due - now
            if left <= timedelta(0):
                continue
            window = next((label for hours, label in WINDOWS if left <= timedelta(hours=hours)), None)
            if window is None:
                continue
            when = timezone.localtime(due).strftime("%d/%m/%Y %H:%M")
            sent += len(
                notify(
                    [person.user],
                    title=f"Due soon: {assignment.title}",
                    body=f"{assignment.site.code}: due {when}. You have not handed it in yet.",
                    link=f"/sites/{assignment.site_id}",
                    kind=Notification.Kind.REMINDER,
                    dedupe_key=f"due:{assignment.id}:{int(due.timestamp())}:{window}",
                )
            )
    return sent


@app.periodic(cron="5 * * * *")
@app.task(name="assessments.due_reminders", queue="notifications")
def due_reminders(timestamp: int | None = None) -> int:
    sent = send_due_reminders()
    log.info("assessments.due_reminders sent %s", sent)
    return sent
