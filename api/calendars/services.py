"""One calendar for a person (item 2.32): due dates of assignments, quizzes and practical tasks, class
sessions, and the dates material is released, on every site they can open, as they are allowed to see them.

A student sees published work only, their own quiz close date (an extension moves it), the class sessions
of the whole class and of their groups, and release dates of published material meant for them (its
groups, and not hidden for a takedown review). Teaching staff, course administrators and auditors see
everything on the sites they can open.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from django.db.models import Q
from django.utils import timezone

from courses.access import TEACHING, person_of, site_role, visible_sites
from courses.groups import member_group_ids


@dataclass
class Event:
    kind: str  # assignment_due, quiz_closes, practical_closes, class_session, release
    id: int
    site_id: int
    site_code: str
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    location: str = ""
    meeting_url: str = ""
    link: str = ""

    @property
    def uid(self) -> str:
        return f"{self.kind}-{self.id}@gsa-lms"

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "id": self.id,
            "site": self.site_id,
            "site_code": self.site_code,
            "title": self.title,
            "starts_at": self.starts_at,
            "ends_at": self.ends_at,
            "location": self.location,
            "meeting_url": self.meeting_url,
            "link": self.link,
        }


def _groups_allow(obj, groups: set[int]) -> bool:
    ids = {g.id for g in obj.groups.all()}
    return not ids or bool(ids & groups)


def events(user, start: datetime, end: datetime) -> list[Event]:
    from assessments.models import Assignment
    from attendance.models import ClassSession
    from courses.models import ContentItem, Module
    from practicals.models import PracticalTask
    from quizzes.models import Quiz, QuizOverride

    person = person_of(user)
    out: list[Event] = []
    for site in visible_sites(user):
        role = site_role(user, site)
        if role is None:
            continue
        staff = role in (*TEACHING, "auditor")
        groups = set() if staff else member_group_ids(person, site)

        def add(kind, obj, title, when, site=site, **extra):
            out.append(Event(kind, obj.id, site.id, site.code, title, when, **extra))

        assignments = Assignment.objects.filter(site=site, due_at__gte=start, due_at__lt=end)
        for a in assignments if staff else assignments.filter(is_published=True):
            add("assignment_due", a, f"Due: {a.title}", a.due_at, link=f"/sites/{site.id}/assignments/{a.id}")

        quizzes = (
            Quiz.objects.filter(site=site) if staff else Quiz.objects.filter(site=site, is_published=True)
        )
        own = (
            {o.quiz_id: o.closes_at for o in QuizOverride.objects.filter(quiz__site=site, student=person)}
            if person is not None and not staff
            else {}
        )
        for quiz in quizzes.filter(Q(closes_at__isnull=False) | Q(id__in=[k for k, v in own.items() if v])):
            closes = own.get(quiz.id) or quiz.closes_at
            if closes and start <= closes < end:
                add(
                    "quiz_closes",
                    quiz,
                    f"Quiz closes: {quiz.title}",
                    closes,
                    link=f"/sites/{site.id}/quizzes/{quiz.id}",
                )

        tasks = PracticalTask.objects.filter(site=site, closes_at__gte=start, closes_at__lt=end)
        for task in tasks if staff else tasks.filter(is_published=True):
            add(
                "practical_closes",
                task,
                f"Practical closes: {task.title}",
                task.closes_at,
                location=task.location,
                link=f"/sites/{site.id}/practicals/{task.id}",
            )

        sessions = ClassSession.objects.filter(site=site, starts_at__lt=end, ends_at__gt=start)
        if not staff:
            sessions = sessions.filter(Q(group__isnull=True) | Q(group__in=groups))
        for s in sessions:
            add(
                "class_session",
                s,
                s.title,
                s.starts_at,
                ends_at=s.ends_at,
                location=s.location,
                meeting_url=s.meeting_url,
                link=f"/sites/{site.id}/classes/{s.id}",
            )

        modules = Module.objects.filter(site=site, available_from__gte=start, available_from__lt=end)
        for module in modules.prefetch_related("groups"):
            if staff or _groups_allow(module, groups):
                add(
                    "release",
                    module,
                    f"Opens: {module.title}",
                    module.available_from,
                    link=f"/sites/{site.id}",
                )
        items = ContentItem.objects.filter(
            module__site=site, available_from__gte=start, available_from__lt=end
        ).prefetch_related("groups", "module__groups")
        if not staff:
            items = items.filter(is_published=True, under_review=False)
        for item in items:
            if staff or (_groups_allow(item, groups) and _groups_allow(item.module, groups)):
                add(
                    "release",
                    item,
                    f"Opens: {item.title}",
                    item.available_from,
                    link=f"/sites/{site.id}/content/{item.id}",
                )
    out.sort(key=lambda e: (e.starts_at, e.kind, e.id))
    return out


# ---------------------------------------------------------------------------------------------------------
# iCalendar (RFC 5545), written by hand: a few properties need no library


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Lines longer than 75 octets continue on the next line after a space."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    parts, chunk = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        if len(chunk) + len(encoded) > (75 if not parts else 74):
            parts.append(chunk.decode("utf-8"))
            chunk = b""
        chunk += encoded
    parts.append(chunk.decode("utf-8"))
    return "\r\n ".join(parts)


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def ical(items: list[Event], origin: str) -> str:
    stamp = _utc(timezone.now())
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Guyana School of Agriculture//GSA LMS//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:GSA LMS",
    ]
    for e in items:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e.uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{_utc(e.starts_at)}",
        ]
        if e.ends_at:
            lines.append(f"DTEND:{_utc(e.ends_at)}")
        lines.append(f"SUMMARY:{_escape(f'{e.site_code}: {e.title}')}")
        if e.location:
            lines.append(f"LOCATION:{_escape(e.location)}")
        if e.meeting_url:
            lines.append(f"URL:{e.meeting_url}")
        description = f"{origin}/#{e.link}" if e.link else ""
        if e.meeting_url:
            description = f"Join online: {e.meeting_url}\n{description}".strip()
        if description:
            lines.append(f"DESCRIPTION:{_escape(description)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
