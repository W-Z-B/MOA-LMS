"""Coursework from practical tasks, the competency suggestion, logbook totals and the student's portfolio."""

from decimal import Decimal

from django.db.models import Prefetch, Sum
from django.utils import timezone

from courses.models import Membership
from practicals.models import (
    AssignmentCompetencyMap,
    CompetencyResult,
    CompetencyUnit,
    LogbookEntry,
    Observation,
    ObservationResult,
    PracticalCriterion,
    UnitType,
)


def coursework_items(
    site, student, *, released_only: bool = False, now=None
) -> list[tuple[Decimal, Decimal | None]]:
    """What each practical task that counts (published, weight above 0) adds to the student's coursework, as
    (weight, fraction): the fraction is earned / possible on the latest attempt; None while pending (not yet
    observed, or observed but not released when released_only); 0 when the task has closed and the student
    was never observed. Meant to be added to assessments.services.coursework_percent's items by the
    coordinator: sum(weight * fraction) / sum(weight) over the items whose fraction is not None.

    A failed critical criterion does not by itself make the fraction 0: the mark reports the checklist, and
    the competency record (CompetencyResult) reports whether the unit was met.
    """
    return [
        (task.weight, fraction)
        for task, fraction, _ in coursework_tasks(site, student, released_only=released_only, now=now)
    ]


def coursework_tasks(site, student, *, released_only: bool = False, now=None) -> list[tuple]:
    """coursework_items with the task and its state, for the working of the total (items 2.28, 2.30):
    (task, fraction, state), state being "graded", "zero" (closed, never observed), "pending" (observed,
    not released for the student's own view) or "not_due" (not yet observed and still open)."""
    from assessments import preload

    now = now or timezone.now()
    items: list[tuple] = []
    loaded = preload.current(site)
    tasks = loaded.practical_tasks if loaded else site.practical_tasks.filter(is_published=True, weight__gt=0)
    for task in tasks:
        if loaded is not None:  # the whole class read at once (assessments.preload)
            observed = loaded.observations.get((task.id, student.pk), [])
            counted = [o for o in observed if o.is_released] if released_only else observed
            latest, any_observed = (counted[0] if counted else None), bool(observed)
        else:
            observations = task.observations.filter(student=student)
            counted = observations.filter(is_released=True) if released_only else observations
            latest = counted.order_by("-attempt").prefetch_related("results__criterion").first()
            any_observed = latest is not None or observations.exists()
        if latest is not None:
            items.append((task, latest.fraction(), "graded"))
        elif not any_observed and task.closes_at is not None and task.closes_at < now:
            items.append((task, Decimal(0), "zero"))
        else:
            items.append((task, None, "pending" if any_observed else "not_due"))
    return items


def site_units(site):
    return CompetencyUnit.objects.filter(framework__sites__site=site).select_related("framework").distinct()


def unit_evidence(site, student, unit) -> dict:
    """The computed suggestion for one unit, and the evidence behind it. Only released observations count.

    The rule (decision D8): a unit may be confirmed competent only when every critical checklist criterion
    mapped to one of its performance criteria has been passed in a released observation (any attempt).
    The suggestion goes further so that it never says "competent" on no evidence: it needs every critical
    mapped criterion passed, or, where none of the mapped criteria is critical, every mapped criterion.
    It is only a suggestion: an assessor confirms every result.
    """
    criteria = list(
        PracticalCriterion.objects.filter(task__site=site, performance_criteria__element__unit=unit)
        .select_related("task")
        .distinct()
    )
    results = ObservationResult.objects.filter(
        observation__student=student, observation__is_released=True, criterion__in=criteria
    ).select_related("observation")
    passed = {r.criterion_id for r in results if r.passed}
    observed = {r.criterion_id for r in results}
    critical = [c for c in criteria if c.is_critical]
    required = critical or criteria
    missing = [c for c in critical if c.id not in passed]
    if not required:
        suggested = CompetencyResult.Status.NOT_ASSESSED
    elif all(c.id in passed for c in required):
        suggested = CompetencyResult.Status.COMPETENT
    elif any(c.id in observed for c in required):
        suggested = CompetencyResult.Status.NOT_YET_COMPETENT
    else:
        suggested = CompetencyResult.Status.NOT_ASSESSED
    assignment_ids = sorted(
        set(
            AssignmentCompetencyMap.objects.filter(
                site=site, performance_criterion__element__unit=unit
            ).values_list("assignment_id", flat=True)
        )
    )
    return {
        "unit_id": unit.id,
        "unit_code": unit.code,
        "unit_title": unit.title,
        "framework": f"{unit.framework.code} v{unit.framework.version}",
        "suggested": suggested,
        "critical_criteria": [{"id": c.id, "task": c.task.title, "text": c.text} for c in critical],
        "missing_critical": [{"id": c.id, "task": c.task.title, "text": c.text} for c in missing],
        "observations": sorted({r.observation_id for r in results}),
        "assignments": assignment_ids,
    }


def missing_critical(site, student, unit) -> list[PracticalCriterion]:
    passed = ObservationResult.objects.filter(
        observation__student=student, observation__is_released=True, passed=True
    ).values("criterion_id")
    return list(
        PracticalCriterion.objects.filter(
            task__site=site, is_critical=True, performance_criteria__element__unit=unit
        )
        .exclude(pk__in=passed)
        .select_related("task")
        .distinct()
    )


def competency_sheet(site, students) -> list[dict]:
    """For each student and each unit the site follows: the suggestion and the result recorded."""
    units = list(site_units(site))
    recorded = {
        (r.student_id, r.unit_id): r
        for r in CompetencyResult.objects.filter(site=site, student__in=students).select_related("assessor")
    }
    rows = []
    for student in students:
        cells = []
        for unit in units:
            evidence = unit_evidence(site, student, unit)
            result = recorded.get((student.id, unit.id))
            evidence["result"] = (
                {
                    "id": result.id,
                    "status": result.status,
                    "assessor": result.assessor.full_name,
                    "decided_on": result.decided_on.isoformat(),
                }
                if result
                else None
            )
            cells.append(evidence)
        rows.append(
            {
                "person_id": student.id,
                "student_no": student.external_id,
                "name": student.full_name,
                "units": cells,
            }
        )
    return rows


def site_students(site):
    members = Membership.objects.filter(site=site, is_active=True, role=Membership.SiteRole.STUDENT)
    return [
        m.person for m in members.select_related("person").order_by("person__last_name", "person__first_name")
    ]


def hours_by_unit(entries) -> list[dict]:
    """Hours of logbook work by kind of place: signed off, and still waiting (pending or returned)."""
    labels = dict(UnitType.choices)
    totals: dict[str, dict] = {}
    for row in entries.values("unit_type", "status").annotate(hours=Sum("hours")):
        cell = totals.setdefault(
            row["unit_type"],
            {
                "unit_type": row["unit_type"],
                "label": labels.get(row["unit_type"], row["unit_type"]),
                "signed_hours": Decimal("0.00"),
                "waiting_hours": Decimal("0.00"),
            },
        )
        key = "signed_hours" if row["status"] == LogbookEntry.Status.SIGNED else "waiting_hours"
        cell[key] += row["hours"]
    ordered = [totals[code] for code, _ in UnitType.choices if code in totals]
    return [
        {**c, "signed_hours": str(c["signed_hours"]), "waiting_hours": str(c["waiting_hours"])}
        for c in ordered
    ]


def _place(record) -> dict | None:
    if record.latitude is None or record.longitude is None:
        return None
    return {"latitude": str(record.latitude), "longitude": str(record.longitude)}


def _photos(photos, prefix: str) -> list[dict]:
    return [
        {
            "filename": p.original_name or p.file.name.rsplit("/", 1)[-1],
            "download_url": f"/api/v1/{prefix}/{p.id}/download/",
        }
        for p in photos
    ]


def portfolio(student, sites) -> dict:
    """Signed logbook entries, released observations and competency results, site by site (item 5.15).
    Nothing waiting for sign-off or release is included."""
    out = []
    for site in sites:
        entries = LogbookEntry.objects.filter(site=site, student=student, status=LogbookEntry.Status.SIGNED)
        observations = (
            Observation.objects.filter(task__site=site, student=student, is_released=True)
            .select_related("task", "assessor")
            .prefetch_related(
                Prefetch("results", queryset=ObservationResult.objects.select_related("criterion")), "photos"
            )
        )
        results = CompetencyResult.objects.filter(site=site, student=student).select_related(
            "unit__framework", "assessor"
        )
        if not (entries.exists() or observations.exists() or results.exists()):
            continue
        out.append(
            {
                "site": {"id": site.id, "code": site.code, "title": site.title, "term": site.term_code},
                "logbook": [
                    {
                        "date": e.work_date.isoformat(),
                        "unit_type": e.get_unit_type_display(),
                        "unit": e.unit_text,
                        "task": e.task,
                        "hours": str(e.hours),
                        "notes": e.notes,
                        "place": _place(e),
                        "signed_by": e.supervisor.full_name if e.supervisor else None,
                        "signed_at": e.reviewed_at.isoformat() if e.reviewed_at else None,
                        "photos": _photos(e.photos.all(), "logbook-photos"),
                    }
                    for e in entries.select_related("supervisor").prefetch_related("photos")
                ],
                "logbook_hours": hours_by_unit(entries),
                "observations": [
                    {
                        "task": o.task.title,
                        "unit_type": o.task.get_unit_type_display(),
                        "attempt": o.attempt,
                        "assessor": o.assessor.full_name,
                        "observed_at": o.observed_at.isoformat(),
                        "recorded_at": o.recorded_at.isoformat(),
                        "location": o.location_text,
                        "place": _place(o),
                        "score": "{} of {}".format(*o.score()),
                        "critical_passed": o.critical_passed(),
                        "comments": o.comments,
                        "criteria": [
                            {
                                "text": r.criterion.text,
                                "critical": r.criterion.is_critical,
                                "passed": r.passed,
                                "score": r.score,
                                "comment": r.comment,
                            }
                            for r in o.results.all()
                        ],
                        "photos": _photos(o.photos.all(), "observation-photos"),
                    }
                    for o in observations
                ],
                "competencies": [
                    {
                        "framework": f"{r.unit.framework.code} v{r.unit.framework.version} "
                        f"{r.unit.framework.title}",
                        "source": r.unit.framework.source,
                        "unit_code": r.unit.code,
                        "unit_title": r.unit.title,
                        "status": r.get_status_display(),
                        "assessor": r.assessor.full_name,
                        "decided_on": r.decided_on.isoformat(),
                        "comments": r.comments,
                    }
                    for r in results
                ],
            }
        )
    return {
        "student": {"student_no": student.external_id, "name": student.full_name},
        "generated_at": timezone.now().isoformat(),
        "sites": out,
    }


def portfolio_html(data: dict) -> str:
    """A plain page of the portfolio, to print or keep; every value escaped."""
    from django.utils.html import escape

    def cell(value) -> str:
        return escape("" if value is None else value)

    student = data["student"]
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>Practical portfolio: {cell(student['name'])}</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:16px;max-width:60rem}table{border-collapse:collapse;"
        "width:100%;margin-bottom:1rem}th,td{border:1px solid #999;padding:4px;text-align:left;"
        "vertical-align:top}"
        "</style></head><body>",
        f"<h1>Practical portfolio</h1><p>{cell(student['name'])} ({cell(student['student_no'])}). "
        f"Produced {cell(data['generated_at'][:16].replace('T', ' '))}. Signed logbook entries, released "
        "observations and competency results only.</p>",
    ]
    if not data["sites"]:
        parts.append("<p>Nothing has been signed off or released yet.</p>")
    for block in data["sites"]:
        site = block["site"]
        parts.append(f"<h2>{cell(site['code'])} {cell(site['title'])}</h2>")
        if block["competencies"]:
            parts.append(
                "<h3>Competency results</h3><table><tr><th>Unit</th><th>Result</th><th>Assessor</th>"
                "<th>Date</th><th>Framework</th></tr>"
            )
            for c in block["competencies"]:
                parts.append(
                    f"<tr><td>{cell(c['unit_code'])} {cell(c['unit_title'])}</td><td>{cell(c['status'])}</td>"
                    f"<td>{cell(c['assessor'])}</td><td>{cell(c['decided_on'])}</td><td>{cell(c['framework'])}</td></tr>"
                )
            parts.append("</table>")
        if block["observations"]:
            parts.append(
                "<h3>Practical observations</h3><table><tr><th>Task</th><th>Attempt</th><th>Score</th>"
                "<th>Critical criteria met</th><th>Assessor</th><th>Observed</th><th>Where</th></tr>"
            )
            for o in block["observations"]:
                parts.append(
                    f"<tr><td>{cell(o['task'])}</td><td>{cell(o['attempt'])}</td><td>{cell(o['score'])}</td>"
                    f"<td>{'Yes' if o['critical_passed'] else 'No'}</td><td>{cell(o['assessor'])}</td>"
                    f"<td>{cell(o['observed_at'][:16].replace('T', ' '))}</td>"
                    f"<td>{cell(o['location'])}</td></tr>"
                )
            parts.append("</table>")
        if block["logbook"]:
            parts.append(
                "<h3>Logbook (signed entries)</h3><table><tr><th>Date</th><th>Where</th><th>Task</th>"
                "<th>Hours</th><th>Signed by</th></tr>"
            )
            for e in block["logbook"]:
                parts.append(
                    f"<tr><td>{cell(e['date'])}</td><td>{cell(e['unit_type'])} {cell(e['unit'])}</td>"
                    f"<td>{cell(e['task'])}</td><td>{cell(e['hours'])}</td><td>{cell(e['signed_by'])}</td></tr>"
                )
            parts.append(
                "</table><p>Hours signed off: "
                + "; ".join(f"{cell(h['label'])} {cell(h['signed_hours'])}" for h in block["logbook_hours"])
                + "</p>"
            )
    parts.append("</body></html>")
    return "".join(parts)
