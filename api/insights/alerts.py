"""Early alerts (item 6.05, decision D5, ADR 0007): visible rules, never prediction; a person decides.

Each night every active rule (insights.models.AlertRule) is checked for each student of each published
academic site. A rule that matches raises an alert carrying its evidence: the pieces of work missed, the
marks that fell, or the date of the last recorded activity. The same evidence never raises a second alert,
so an alert dismissed stays dismissed until something new happens; while an alert is still open, newer
evidence replaces its own. Nothing is decided or sent to the student: the site's teaching staff are told
how many new alerts there are, and a person acknowledges each, acts on it (usually by writing to the
student through Messages) or dismisses it with a reason. Students never see alerts as a label on themselves.
"""

import hashlib
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from assessments.services import coursework_working
from audit.services import record, snapshot
from courses.models import CourseSite, Membership
from insights.activity import last_seen
from insights.analytics import students_of
from insights.models import Alert, AlertRule

RECENT_MARKS = 2  # falling marks: the latest two marks against the student's earlier ones
DEFAULTS = {
    AlertRule.Kind.MISSED_WORK: (2, 28),
    AlertRule.Kind.FALLING_MARKS: (15, 28),
    AlertRule.Kind.NO_VISITS: (14, 0),
}


def _key(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def _when(value) -> str | None:
    return value.isoformat() if value is not None else None


def _dates(site) -> dict[tuple[str, int], object]:
    """When each counted item closed: assignments by their due date, quizzes and practicals when they
    close. Used to keep missed work to the rule's window."""
    dates = {("quiz", q.id): q.closes_at for q in site.quizzes.all()}
    dates.update({("practical", t.id): t.closes_at for t in site.practical_tasks.all()})
    return dates


def _closed_at(item: dict, dates: dict):
    if item.get("due_at"):
        return datetime.fromisoformat(item["due_at"])
    return dates.get((item["kind"], item["id"]))


def missed_work(rule, working, dates, now) -> tuple[str, list[dict], str] | None:
    since = now - timedelta(days=rule.window_days)
    missed = []
    for item in working["items"]:
        if item["state"] != "zero":
            continue
        when = _closed_at(item, dates)
        if when is not None and when < since:
            continue
        missed.append({"what": f"{item['title']}: nothing handed in by the due date", "when": _when(when)})
    if len(missed) < rule.threshold:
        return None
    summary = f"{len(missed)} pieces of work missed in the last {rule.window_days} days"
    return summary, missed, _key(*sorted(m["what"] for m in missed))


def falling_marks(rule, working, dates, now) -> tuple[str, list[dict], str] | None:
    graded = []
    for item in working["items"]:
        if item["state"] != "graded" or item["percent"] is None:
            continue
        graded.append((_closed_at(item, dates), item))
    # In the order the work closed; work with no closing date counts as the oldest.
    graded.sort(key=lambda pair: (pair[0] is not None, pair[0] or now))
    if len(graded) < RECENT_MARKS + 2:
        return None  # too few marks to speak of a trend
    earlier, recent = graded[:-RECENT_MARKS], graded[-RECENT_MARKS:]
    latest = recent[-1][0]
    if latest is not None and latest < now - timedelta(days=rule.window_days):
        return None
    before = sum(Decimal(i["percent"]) for _, i in earlier) / len(earlier)
    after = sum(Decimal(i["percent"]) for _, i in recent) / len(recent)
    if before - after < rule.threshold:
        return None
    evidence = [
        {"what": f"Earlier marks averaged {before:.1f}% over {len(earlier)} pieces of work", "when": None},
        *({"what": f"{i['title']}: {i['percent']}%", "when": _when(when)} for when, i in recent),
    ]
    summary = f"Latest marks {before - after:.1f} percentage points below earlier ones"
    return summary, evidence, _key(*(f"{i['kind']}{i['id']}" for _, i in recent))


def no_visits(rule, last, joined, now) -> tuple[str, list[dict], str] | None:
    since = last or joined
    if since is None or now - since < timedelta(days=rule.threshold):
        return None
    days = (now - since).days
    if last is None:
        what = f"Nothing recorded on the course since joining it {days} days ago"
    else:
        what = f"Last recorded activity on the course {days} days ago"
    return f"No visits for {days} days", [{"what": what, "when": _when(since)}], _key(_when(since))


def _raise(site, student, kind, found, now, raised: list) -> None:
    summary, evidence, key = found
    if Alert.objects.filter(site=site, student=student, kind=kind, evidence_key=key).exists():
        return  # this evidence was alerted already: whatever a person decided about it stands
    current = Alert.objects.filter(
        site=site, student=student, kind=kind, state__in=[Alert.State.OPEN, Alert.State.ACKNOWLEDGED]
    ).first()
    with transaction.atomic():
        if current is not None:
            before = snapshot(current)
            current.summary, current.evidence, current.evidence_key = summary[:300], evidence, key
            current.save(update_fields=["summary", "evidence", "evidence_key", "updated_at"])
            record(None, "update", current, before=before, after=snapshot(current), reason="New evidence")
            return
        alert = Alert.objects.create(
            site=site,
            student=student,
            kind=kind,
            summary=summary[:300],
            evidence=evidence,
            evidence_key=key,
            raised_at=now,
        )
        record(None, "create", alert, after=snapshot(alert), reason="An early-alert rule matched")
    raised.append(alert)


def check_site(site: CourseSite, rules: list[AlertRule], *, now=None) -> list[Alert]:
    """Check every rule for every student of the site. Returns the alerts raised now."""
    now = now or timezone.now()
    raised: list[Alert] = []
    by_kind = {rule.kind: rule for rule in rules if rule.is_active}
    if not by_kind:
        return raised
    students = students_of(site)
    seen = last_seen(site, students) if AlertRule.Kind.NO_VISITS in by_kind else {}
    joined = dict(
        Membership.objects.filter(site=site, role=Membership.SiteRole.STUDENT, is_active=True).values_list(
            "person_id", "created_at"
        )
    )
    dates = _dates(site)
    for student in students:
        working = None
        if AlertRule.Kind.MISSED_WORK in by_kind or AlertRule.Kind.FALLING_MARKS in by_kind:
            working = coursework_working(site, student, now=now)
        checks = {
            AlertRule.Kind.MISSED_WORK: lambda r, w=working: missed_work(r, w, dates, now),
            AlertRule.Kind.FALLING_MARKS: lambda r, w=working: falling_marks(r, w, dates, now),
            AlertRule.Kind.NO_VISITS: lambda r, s=student: no_visits(
                r, seen.get(s.id), joined.get(s.id), now
            ),
        }
        for kind, rule in by_kind.items():
            found = checks[kind](rule)
            if found is not None:
                _raise(site, student, kind, found, now, raised)
    return raised


def _tell_teaching_staff(site: CourseSite, count: int, now) -> None:
    from approvals.delegation import users_of
    from notifications.services import notify

    staff = [
        m.person
        for m in site.memberships.filter(
            is_active=True, role__in=[Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT]
        ).select_related("person__user")
    ]
    notify(
        users_of(staff),
        title=f"{count} new early alert{'s' if count != 1 else ''} on {site.code}",
        body="Students the alert rules picked out, with the evidence. You decide what, if anything, to do.",
        link=f"/sites/{site.id}/insights",
        dedupe_key=f"alerts:{site.id}:{now:%Y%m%d}",
    )


def nightly(*, now=None) -> dict:
    """The nightly check: every published academic site."""
    now = now or timezone.now()
    for kind, (threshold, window) in DEFAULTS.items():
        AlertRule.objects.get_or_create(kind=kind, defaults={"threshold": threshold, "window_days": window})
    rules = list(AlertRule.objects.filter(is_active=True))
    counts = {"sites": 0, "raised": 0}
    sites = CourseSite.objects.filter(is_published=True, kind=CourseSite.Kind.ACADEMIC)
    for site in sites:
        raised = check_site(site, rules, now=now)
        counts["sites"] += 1
        counts["raised"] += len(raised)
        if raised:
            _tell_teaching_staff(site, len(raised), now)
    return counts
