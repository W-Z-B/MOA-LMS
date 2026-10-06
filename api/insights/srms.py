"""Learning outcomes from the SRMS; competency results and outcome standings back to it (items 3.11, 6.10).

Two integration endpoints of the SRMS, both with the LMS's service key:

- GET /api/v1/integration/course-outcomes/ (scope academics:read) lists each course's outcomes from its
  course outline: [{"course_code": "AGR101", "outcomes": [{"code": "LO1", "text": "..."}]}], as a plain
  list or a page of {"results": [...], "next": ...}. The nightly sync upserts them; an outcome the outline
  no longer lists is made inactive, never deleted, so links and evidence stay.
- POST /api/v1/integration/competency-results/ (scope marks:write) takes
  [{"offering_code", "student_no", "unit_code", "result", "assessed_on"}]. The LMS sends, for each SRMS
  offering, every unit of competence an assessor decided (result "competent" or "not_yet_competent", on the
  day decided) and each student's standing on each SRMS outcome that has released evidence (result
  "outcome_met" or "outcome_not_yet_met", unit_code the outcome's code, on the day sent). The SRMS may answer
  like coursework-marks ({"accepted": [...], "locked": [...], "unknown": [...]}); students it does not know
  are named in the run's notes.

The push is off until GSA decides competency records (decision D8, ADR 0017) and the Registrar agrees the
endpoint: SRMS_COMPETENCY_PUSH. The attendance totals have their own push (integration.srms.push_attendance).
"""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from courses.models import CourseSite
from insights.models import Outcome
from integration.client import IntegrationError, call, unreachable, with_retries
from integration.models import IntegrationRun
from integration.runs import Run

OUTCOMES_PATH = "/api/v1/integration/course-outcomes/"
COMPETENCY_PATH = "/api/v1/integration/competency-results/"


def configured() -> bool:
    return bool(settings.SRMS_API_URL and settings.SRMS_API_KEY)


def _srms(path: str, **kwargs):
    return call(settings.SRMS_API_URL, settings.SRMS_API_KEY, path, **kwargs)


def fetch_outlines() -> list[dict]:
    """Every course's outcomes from the SRMS, following pages when the answer is paged."""
    payload = _srms(OUTCOMES_PATH)
    if isinstance(payload, list):
        return payload
    rows = list(payload.get("results", []))
    while payload.get("next"):
        payload = _srms(payload["next"])
        rows.extend(payload.get("results", []))
    return rows


@transaction.atomic
def _apply_outline(course_code: str, outcomes: list[dict]) -> int:
    seen = set()
    for position, row in enumerate(outcomes, start=1):
        code = str(row["code"]).strip()[:20]
        text = str(row["text"]).strip()
        if not code or not text:
            raise ValueError("an outcome with no code or text")
        Outcome.objects.update_or_create(
            source=Outcome.Source.SRMS,
            course_code=course_code,
            code=code,
            defaults={"text": text, "position": position, "is_active": True},
        )
        seen.add(code)
    Outcome.objects.filter(source=Outcome.Source.SRMS, course_code=course_code, is_active=True).exclude(
        code__in=seen
    ).update(is_active=False, updated_at=timezone.now())
    return len(seen)


def sync_outcomes(*, trigger: str = "schedule") -> dict:
    """The nightly pull of course outlines. A course whose outline cannot be read is named and the others
    carry on; when the SRMS cannot be reached the run stops and the outcomes already held stay."""
    run = Run(IntegrationRun.Kind.OUTCOME_SYNC, trigger)
    try:
        outlines = with_retries(fetch_outlines)
    except IntegrationError as exc:
        run.stop(f"The SRMS could not be reached: {exc}" if unreachable(exc) else str(exc))
        return run.finish()
    for outline in outlines:
        course_code = str(outline.get("course_code") or "").strip()[:20]
        try:
            if not course_code:
                raise ValueError("a course outline with no course code")
            run.ok_(_apply_outline(course_code, list(outline.get("outcomes") or [])))
        except (KeyError, TypeError, ValueError) as exc:
            run.fail(course_code or "?", "bad_outline", f"The outline could not be read: {exc}")
    return run.finish()


def competency_rows(site: CourseSite, *, today=None) -> list[dict]:
    """What is sent for one offering: decided units of competence, and standings on the course's SRMS
    outcomes from released marks."""
    from insights.analytics import students_of
    from insights.outcomes import NO_EVIDENCE, srms_outcomes, standings
    from practicals.models import CompetencyResult

    today = today or timezone.localdate()
    rows = [
        {
            "offering_code": site.code,
            "student_no": result.student.external_id,
            "unit_code": result.unit.code,
            "result": result.status,
            "assessed_on": result.decided_on.isoformat(),
        }
        for result in CompetencyResult.objects.filter(site=site)
        .exclude(status=CompetencyResult.Status.NOT_ASSESSED)
        .select_related("student", "unit")
        .order_by("student__external_id", "unit__code")
    ]
    if srms_outcomes(site).exists():
        table = standings(site, students_of(site), released_only=True)
        codes = {str(o["id"]): o["code"] for o in table["outcomes"]}
        for student in table["students"]:
            for outcome_id, cell in student["outcomes"].items():
                if cell["standing"] == NO_EVIDENCE:
                    continue
                rows.append(
                    {
                        "offering_code": site.code,
                        "student_no": student["student_no"],
                        "unit_code": codes[outcome_id],
                        "result": "outcome_met" if cell["standing"] == "met" else "outcome_not_yet_met",
                        "assessed_on": today.isoformat(),
                    }
                )
    return rows


def push_competency(site: CourseSite) -> dict:
    if site.source != CourseSite.Source.SRMS:
        return {"offering_code": site.code, "skipped": "not an SRMS offering", "sent": []}
    rows = competency_rows(site)
    if not rows:
        return {"offering_code": site.code, "accepted": [], "locked": [], "unknown": [], "sent": []}
    answer = _srms(COMPETENCY_PATH, data=rows)
    answer = answer if isinstance(answer, dict) else {}
    return {**answer, "sent": rows}


def push_all_competency(*, trigger: str = "schedule") -> dict:
    """The nightly push for every published SRMS offering, recorded as an integration run (item 1.23)."""
    run = Run(IntegrationRun.Kind.COMPETENCY_PUSH, trigger)
    for site in CourseSite.objects.filter(source=CourseSite.Source.SRMS, is_published=True).order_by("code"):
        try:
            result = with_retries(lambda site=site: push_competency(site))
        except IntegrationError as exc:
            if unreachable(exc):
                run.stop(f"The SRMS could not be reached: {exc}")
                break
            run.fail(site.code, f"http_{exc.status}", str(exc))
            continue
        run.ok_(len(result.get("sent", [])))
        for student_no in result.get("unknown", []) or []:
            run.note(f"{site.code}:{student_no}", "unknown_student", "The SRMS does not know this student")
        if result.get("locked"):
            run.note(site.code, "locked", f"{len(result['locked'])} results are locked in the SRMS")
    return run.finish()


def record_offering(site: CourseSite, offering: dict) -> None:
    """Keep the offering's course and programmes beside the site (called by integration.srms.sync_sites).
    The SRMS sends programme_codes (or programme_code) once it lists them; until then reports group the
    site under "Programme not known"."""
    from insights.models import SiteProfile

    programmes = offering.get("programme_codes")
    if programmes is None:
        programmes = [offering["programme_code"]] if offering.get("programme_code") else []
    SiteProfile.objects.update_or_create(
        site=site,
        defaults={
            "course_code": str(offering.get("course_code") or "")[:20],
            "programme_codes": [str(code)[:20] for code in programmes if code],
        },
    )
