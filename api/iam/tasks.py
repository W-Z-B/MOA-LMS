"""The access review falls due each term (item 1.21): a reminder to the administrators and course
administrators, each Monday at 06:00 until it is signed off, once a term at most. The reminder lists who
holds a system role and who teaches which site, so that it can be read where it arrives."""

import logging
from datetime import date

from django.utils import timezone
from procrastinate.contrib.django import app

from core.schedule import periodic
from iam.models import AccessReview, Role
from iam.review import role_holders, teaching_staff
from notifications.models import Notification
from notifications.services import notify, users_with_role

log = logging.getLogger(__name__)
# A term is about four months; the year is split into three for the reminder's once-a-term key.
REVIEW_EVERY_DAYS = 120
LISTED = 40  # lines in the reminder; the full list is on the access review page


def _lines() -> list[str]:
    roles = [f"{r['name']} ({r['username']}): {r['role_name']}" for r in role_holders()]
    teaching = [
        f"{t['site_code']}: {t['name']} ({t['employee_no']}), {t['site_role'].lower()}"
        for t in teaching_staff()
    ]
    lines = [
        "Who holds a role:",
        *(roles or ["nobody"]),
        "",
        "Who teaches which site:",
        *(teaching or ["nobody"]),
    ]
    if len(lines) > LISTED:
        lines = [*lines[:LISTED], f"... and {len(lines) - LISTED} more lines on the access review page."]
    return lines


def remind_access_review(today: date) -> int:
    last = AccessReview.objects.select_related("reviewed_by").first()
    if last is not None and (today - timezone.localdate(last.reviewed_at)).days < REVIEW_EVERY_DAYS:
        return 0
    when = (
        f"was last signed off on {timezone.localdate(last.reviewed_at):%d/%m/%Y}"
        if last
        else "has not been signed off yet"
    )
    recipients = set(users_with_role(Role.ADMINISTRATOR)) | set(users_with_role(Role.COURSE_ADMIN))
    term = (today.month - 1) // 4 + 1
    body = (
        f"The list of who holds a role and who teaches which site {when}. Confirm each line, take away "
        "access that is no longer needed, and sign the review off.\n\n" + "\n".join(_lines())
    )
    return len(
        notify(
            recipients,
            title="Access review due",
            body=body,
            link="/admin/access-review",
            kind=Notification.Kind.ALERT,
            dedupe_key=f"access-review:{today.year}-T{term}",
        )
    )


@periodic("0 6 * * 1")
@app.task(name="iam.access_review_reminder", queue="iam")
def access_review_reminder(timestamp: int | None = None) -> int:
    sent = remind_access_review(timezone.localdate())
    log.info("iam.access_review_reminder sent %s notifications", sent)
    return sent
