"""Reports that leave a course (items 6.03, 6.04), with small groups hidden (item 6.06).

- Courses (6.03), for heads of department and the Registrar: each site's content, marking turnaround and the
  coursework sent to the SRMS, by campus and programme.
- Staff development (6.04), for HR and the Ministry: completions by unit, and required training overdue.

Who reads which rows comes from the person's role grants (iam.RoleScope). Administrators, course
administrators and the auditor read everything. The Registrar reads the campus of the grant, or every campus
when it names none. A head of department reads the units of their grants: for courses, the sites on which a
member of staff of the unit (from the HRMS record) teaches; for staff development, the unit's staff.

Every figure about people goes through insights.smallgroups.hide_small before it is shown or exported.
"""

import csv
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import Count, F, Q
from django.utils import timezone

from assessments.models import Mark, SrmsTransfer, Submission
from courses.models import Completion, ContentItem, CourseSite, Membership
from iam.models import Role, RoleScope
from insights.smallgroups import hide_small, hide_total
from people.models import PersonRef
from staffdev.models import TrainingAssignment

ONE_PLACE = Decimal("0.1")
EVERYTHING = (Role.ADMINISTRATOR, Role.COURSE_ADMIN, Role.AUDITOR)
COURSE_READERS = (*EVERYTHING, Role.REGISTRAR, Role.HEAD_OF_DEPARTMENT)
STAFF_READERS = (*EVERYTHING, Role.HEAD_OF_DEPARTMENT)
NOT_KNOWN = "Programme not known"
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


@dataclass
class Scope:
    everything: bool = False
    campuses: set[str] = field(default_factory=set)
    units: set[str] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not (self.everything or self.campuses or self.units)


def scope_of(user, readers: tuple[str, ...]) -> Scope:
    """What the user's grants let them read in a report for these roles."""
    scope = Scope()
    if getattr(user, "is_superuser", False):
        scope.everything = True
        return scope
    for grant in RoleScope.objects.filter(user=user, role__code__in=readers).select_related("role"):
        code = grant.role.code
        if code in EVERYTHING:
            scope.everything = True
        elif code == Role.REGISTRAR:
            if grant.campus_code:
                scope.campuses.add(grant.campus_code)
            else:
                scope.everything = True
        elif code == Role.HEAD_OF_DEPARTMENT and grant.unit_code:
            scope.units.add(grant.unit_code)
    return scope


def _round(value) -> str | None:
    return None if value is None else str(Decimal(value).quantize(ONE_PLACE, rounding=ROUND_HALF_UP))


def cell(value) -> str:
    """A value as a spreadsheet cell that cannot start a formula, as in the audit export."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_START) else text


def write_csv(header: list[str], rows: list[list]):
    """The lines of a CSV file, starting with the mark that tells spreadsheet programs it is UTF-8."""

    class Echo:
        def write(self, value):
            return value

    writer = csv.writer(Echo())
    yield "﻿"
    yield writer.writerow(header)
    for row in rows:
        yield writer.writerow([cell(v) for v in row])


# ---------------------------------------------------------------------------------------------------------
# Courses (item 6.03)

SITE_FIGURES = (
    "handed_in",
    "marked",
    "turnaround_days",
    "marked_late",
    "waiting_too_long",
    "srms_sent",
    "srms_accepted",
    "srms_locked",
    "srms_unknown",
)


def scoped_sites(scope: Scope, *, campus: str = "", programme: str = "", term: str = ""):
    sites = CourseSite.objects.filter(kind=CourseSite.Kind.ACADEMIC)
    if not scope.everything:
        allowed = Q(pk__in=[])
        if scope.campuses:
            allowed |= Q(campus_code__in=scope.campuses)
        if scope.units:
            allowed |= Q(
                memberships__is_active=True,
                memberships__role__in=[Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT],
                memberships__person__unit_code__in=scope.units,
            )
        sites = sites.filter(allowed).distinct()
    if campus:
        sites = sites.filter(campus_code=campus)
    if term:
        sites = sites.filter(term_code=term)
    if programme == NOT_KNOWN:
        sites = sites.filter(Q(profile__isnull=True) | Q(profile__programme_codes=[]))
    elif programme:
        sites = sites.filter(profile__programme_codes__contains=[programme])
    return sites.select_related("profile").order_by("campus_code", "code")


def _site_row(site: CourseSite, now) -> dict:
    items = ContentItem.objects.filter(module__site=site, is_published=True).count()
    students = Membership.objects.filter(site=site, role=Membership.SiteRole.STUDENT, is_active=True).count()
    submissions = Submission.objects.filter(assignment__site=site, assignment__is_published=True)
    marks = Mark.objects.filter(submission__in=submissions).annotate(
        took=F("created_at") - F("submission__submitted_at")
    )
    days = [max(m.took.total_seconds(), 0) / 86400 for m in marks]
    limit = settings.MARKING_DAYS
    waiting = submissions.filter(mark__isnull=True, submitted_at__lt=now - timedelta(days=limit)).count()
    transfers = SrmsTransfer.objects.filter(site=site)
    latest = {}
    for transfer in transfers.order_by("student_id", "-sent_at"):
        latest.setdefault(transfer.student_id, transfer)
    outcomes = [t.outcome for t in latest.values()]
    profile = getattr(site, "profile", None)
    return {
        "id": site.id,
        "code": site.code,
        "title": site.title,
        "term_code": site.term_code,
        "campus_code": site.campus_code,
        "programmes": list(profile.programme_codes) if profile and profile.programme_codes else [],
        "is_published": site.is_published,
        "items": items,
        "no_content": items == 0,
        "assignments": site.assignments.filter(is_published=True).count(),
        "students": students,
        "handed_in": submissions.count(),
        "marked": len(days),
        "turnaround_days": _round(sum(days) / len(days)) if days else None,
        "marked_late": sum(1 for d in days if d > limit),
        "waiting_too_long": waiting,
        "srms_sent": len(latest),
        "srms_accepted": outcomes.count(SrmsTransfer.Outcome.ACCEPTED),
        "srms_locked": outcomes.count(SrmsTransfer.Outcome.LOCKED),
        "srms_unknown": outcomes.count(SrmsTransfer.Outcome.UNKNOWN),
        "srms_last_sent": max((t.sent_at for t in latest.values()), default=None),
    }


def _group_rows(sites: list[dict]) -> list[dict]:
    """The sites summed by campus and programme (a site in two programmes counts in both)."""
    groups: dict[tuple[str, str], dict] = {}
    for site in sites:
        for programme in site["programmes"] or [NOT_KNOWN]:
            row = groups.setdefault(
                (site["campus_code"], programme),
                {
                    "campus_code": site["campus_code"],
                    "programme": programme,
                    "sites": 0,
                    "sites_without_content": 0,
                    "students": 0,
                    "handed_in": 0,
                    "marked": 0,
                    "_days": Decimal(0),
                    "waiting_too_long": 0,
                    "srms_sent": 0,
                },
            )
            row["sites"] += 1
            row["sites_without_content"] += site["no_content"]
            for name in ("students", "handed_in", "marked", "waiting_too_long", "srms_sent"):
                row[name] += site[name]
            if site["turnaround_days"] is not None:
                row["_days"] += Decimal(site["turnaround_days"]) * site["marked"]
    rows = []
    for key in sorted(groups):
        row = groups[key]
        days = row.pop("_days")
        row["turnaround_days"] = _round(days / row["marked"]) if row["marked"] else None
        rows.append(row)
    return rows


GROUP_FIGURES = ("handed_in", "marked", "turnaround_days", "waiting_too_long", "srms_sent")


def course_report(scope: Scope, *, campus: str = "", programme: str = "", term: str = "", now=None) -> dict:
    now = now or timezone.now()
    sites = [
        _site_row(site, now) for site in scoped_sites(scope, campus=campus, programme=programme, term=term)
    ]
    groups = _group_rows(sites)
    total = {
        "sites": len(sites),
        "sites_without_content": sum(s["no_content"] for s in sites),
        "students": sum(s["students"] for s in sites),
        "handed_in": sum(s["handed_in"] for s in sites),
        "marked": sum(s["marked"] for s in sites),
        "waiting_too_long": sum(s["waiting_too_long"] for s in sites),
        "srms_sent": sum(s["srms_sent"] for s in sites),
    }
    weighted = [
        (Decimal(s["turnaround_days"]), s["marked"]) for s in sites if s["turnaround_days"] is not None
    ]
    marked = sum(n for _, n in weighted)
    total["turnaround_days"] = _round(sum(d * n for d, n in weighted) / marked) if marked else None
    # Small groups hidden only after every total is worked out from the real figures (item 6.06).
    hide_small(sites, size_key="students", fields=SITE_FIGURES, totalled=True)
    hide_small(groups, size_key="students", fields=GROUP_FIGURES, totalled=True)
    hide_total(total, size_key="students", fields=GROUP_FIGURES)
    return {
        "min_group": settings.REPORT_MIN_GROUP,
        "marking_days": settings.MARKING_DAYS,
        "total": total,
        "groups": groups,
        "sites": sites,
    }


COURSE_CSV = [
    ("Site", "code"),
    ("Title", "title"),
    ("Term", "term_code"),
    ("Campus", "campus_code"),
    ("Programmes", "programmes"),
    ("Published", "is_published"),
    ("Content items", "items"),
    ("Assignments", "assignments"),
    ("Students", "students"),
    ("Work handed in", "handed_in"),
    ("Work marked", "marked"),
    ("Average days to mark", "turnaround_days"),
    ("Marked after the limit", "marked_late"),
    ("Waiting longer than the limit", "waiting_too_long"),
    ("Students sent to the SRMS", "srms_sent"),
    ("Accepted by the SRMS", "srms_accepted"),
    ("Locked in the SRMS", "srms_locked"),
    ("Not known to the SRMS", "srms_unknown"),
]


def _shown(row: dict, key: str):
    value = row.get(key)
    if row.get("hidden") and key in (*SITE_FIGURES, "students"):
        return "hidden"
    if isinstance(value, list):
        return " ".join(value) or NOT_KNOWN
    if isinstance(value, bool):
        return "yes" if value else "no"
    return value


def course_csv(report: dict):
    rows = [[_shown(site, key) for _, key in COURSE_CSV] for site in report["sites"]]
    return write_csv([label for label, _ in COURSE_CSV], rows)


# ---------------------------------------------------------------------------------------------------------
# Staff development (item 6.04)

UNIT_FIGURES = ("completions", "required", "required_done", "overdue")
NO_UNIT = "Unit not known"


def staff_report(
    scope: Scope, *, campus: str = "", since: date | None = None, today: date | None = None
) -> dict:
    today = today or timezone.localdate()
    staff = PersonRef.objects.filter(kind=PersonRef.Kind.STAFF, is_active=True)
    if not scope.everything:
        staff = staff.filter(unit_code__in=scope.units)
    if campus:
        staff = staff.filter(campus_code=campus)
    completions = Completion.objects.filter(
        site__kind=CourseSite.Kind.STAFF_DEVELOPMENT, person__in=staff, person__kind=PersonRef.Kind.STAFF
    )
    if since:
        completions = completions.filter(completed_on__gte=since)
    assignments = TrainingAssignment.objects.filter(person__in=staff, requirement__is_active=True)
    units: dict[str, dict] = {}
    for row in staff.values("unit_code").annotate(n=Count("id")):
        units[row["unit_code"]] = {
            "unit_code": row["unit_code"] or NO_UNIT,
            "staff": row["n"],
            "completions": 0,
            "required": 0,
            "required_done": 0,
            "overdue": 0,
        }
    for row in completions.values("person__unit_code").annotate(n=Count("id")):
        units[row["person__unit_code"]]["completions"] = row["n"]
    for row in assignments.values("person__unit_code").annotate(
        n=Count("id"),
        done=Count("id", filter=Q(completed_on__isnull=False)),
        late=Count("id", filter=Q(completed_on__isnull=True, due_on__lt=today)),
    ):
        unit = units[row["person__unit_code"]]
        unit["required"], unit["required_done"], unit["overdue"] = row["n"], row["done"], row["late"]
    by_unit = [units[key] for key in sorted(units)]
    courses = [
        {
            "site": row["site_id"],
            "title": row["site__title"],
            "code": row["site__code"],
            "completions": row["n"],
        }
        for row in completions.values("site_id", "site__title", "site__code")
        .annotate(n=Count("id"))
        .order_by("site__title")
    ]
    total = {"staff": sum(u["staff"] for u in by_unit)}
    for name in UNIT_FIGURES:
        total[name] = sum(u[name] for u in by_unit)
    hide_small(by_unit, size_key="staff", fields=UNIT_FIGURES, totalled=True)
    hide_small(courses, size_key="completions", fields=(), totalled=True)
    hide_total(total, size_key="staff", fields=UNIT_FIGURES)
    return {
        "min_group": settings.REPORT_MIN_GROUP,
        "since": since,
        "total": total,
        "units": by_unit,
        "courses": courses,
    }


STAFF_CSV = [
    ("Unit", "unit_code"),
    ("Staff", "staff"),
    ("Completions", "completions"),
    ("Required training assigned", "required"),
    ("Required training done", "required_done"),
    ("Required training overdue", "overdue"),
]


def staff_csv(report: dict):
    def shown(row, key):
        if row.get("hidden") and key != "unit_code":
            return "hidden"
        return row.get(key)

    rows = [[shown(unit, key) for _, key in STAFF_CSV] for unit in report["units"]]
    return write_csv([label for label, _ in STAFF_CSV], rows)
