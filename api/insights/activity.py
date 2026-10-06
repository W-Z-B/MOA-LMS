"""When a student was last seen on a course, from records the LMS already keeps (item 1.20).

Nothing is recorded for this: "last seen" is the latest of the student's own recorded actions on the site:
an item first opened, downloaded or marked complete, work handed in, a quiz attempt started or submitted, a
forum post, a message sent, and a class attended. Reading a page again leaves no trace, by design, so this
is a lower bound and is described as "last recorded activity" wherever it is shown. The last sign-in comes
from the audit log, where every sign-in is already written.
"""

from django.db.models import Max

from assessments.models import SubmissionAttempt
from attendance.models import AttendanceRecord
from audit.models import AuditLog
from courses.models import ItemCompletion
from forums.models import Post
from messaging.models import Message
from people.models import PersonRef
from quizzes.models import Attempt


def _later(seen: dict, key, when) -> None:
    if when is not None and (seen.get(key) is None or when > seen[key]):
        seen[key] = when


def last_seen(site, people) -> dict[int, object]:
    """{person id: the latest recorded activity on the site}; people with none are left out."""
    people = list(people)
    ids = [p.id for p in people]
    seen: dict[int, object] = {}
    rows = (
        ItemCompletion.objects.filter(item__module__site=site, person_id__in=ids)
        .values("person_id")
        .annotate(at=Max("completed_at"))
    )
    for row in rows:
        _later(seen, row["person_id"], row["at"])
    rows = (
        SubmissionAttempt.objects.filter(submission__assignment__site=site, submitted_by_id__in=ids)
        .values("submitted_by_id")
        .annotate(at=Max("submitted_at"))
    )
    for row in rows:
        _later(seen, row["submitted_by_id"], row["at"])
    rows = (
        Attempt.objects.filter(quiz__site=site, student_id__in=ids)
        .values("student_id")
        .annotate(started=Max("started_at"), submitted=Max("submitted_at"))
    )
    for row in rows:
        _later(seen, row["student_id"], row["started"])
        _later(seen, row["student_id"], row["submitted"])
    rows = (
        AttendanceRecord.objects.filter(
            session__site=site,
            student_id__in=ids,
            status__in=[AttendanceRecord.Status.PRESENT, AttendanceRecord.Status.LATE],
        )
        .values("student_id")
        .annotate(at=Max("acted_at"))
    )
    for row in rows:
        _later(seen, row["student_id"], row["at"])
    by_user = {p.user_id: p.id for p in people if p.user_id}
    if by_user:
        rows = (
            Post.objects.filter(thread__forum__site=site, author_id__in=by_user)
            .values("author_id")
            .annotate(at=Max("created_at"))
        )
        for row in rows:
            _later(seen, by_user[row["author_id"]], row["at"])
        rows = (
            Message.objects.filter(conversation__site=site, sender_id__in=by_user)
            .values("sender_id")
            .annotate(at=Max("created_at"))
        )
        for row in rows:
            _later(seen, by_user[row["sender_id"]], row["at"])
    return seen


def last_signed_in(people) -> dict[int, object]:
    """{person id: their latest sign-in}, from the audit log's sign-in entries."""
    ids = [p.id if isinstance(p, PersonRef) else p for p in people]
    rows = (
        AuditLog.objects.filter(action="login", entity="auth.user", subject__in=ids)
        .values("subject")
        .annotate(at=Max("at"))
    )
    return {row["subject"]: row["at"] for row in rows}
