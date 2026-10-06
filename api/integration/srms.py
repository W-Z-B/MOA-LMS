"""Build course sites from SRMS offerings and return coursework totals to the SRMS.

The SRMS owns offerings, enrolments and results. The LMS mirrors the first two and feeds the third.
"""

from django.conf import settings
from django.db import transaction

from assessments.services import coursework_percent
from courses.models import CourseSite, Membership
from courses.site_templates import apply_template
from integration.client import call, pages
from people.models import PersonRef


def _srms(path: str, **kwargs):
    return call(settings.SRMS_API_URL, settings.SRMS_API_KEY, path, **kwargs)


def _srms_pages(path: str, params: dict | None = None):
    return pages(settings.SRMS_API_URL, settings.SRMS_API_KEY, path, params=params)


def _staff_directory() -> dict[str, dict]:
    """Names for lecturers, from the HRMS when it is configured. Empty otherwise."""
    if not settings.HRMS_API_URL or not settings.HRMS_API_KEY:
        return {}
    rows = pages(settings.HRMS_API_URL, settings.HRMS_API_KEY, "/api/v1/integration/staff/")
    return {row["employee_no"]: row for row in rows}


def _upsert_lecturer(employee_no: str, directory: dict[str, dict]) -> PersonRef:
    row = directory.get(employee_no, {})
    defaults = {"is_active": True}
    if row:
        defaults.update(
            first_name=row.get("first_name", ""),
            last_name=row.get("last_name", ""),
            email=row.get("email") or "",
            campus_code=row.get("campus_code") or "",
        )
    person, _ = PersonRef.objects.update_or_create(
        kind=PersonRef.Kind.STAFF, external_id=employee_no, defaults=defaults
    )
    return person


@transaction.atomic
def sync_sites(*, current_only: bool = True) -> dict:
    """Upsert sites, lecturers and class lists. Students who left an offering are deactivated, not deleted."""
    directory = _staff_directory()
    counts = {"sites": 0, "lecturers": 0, "students": 0, "deactivated": 0}
    params = {"current": "1"} if current_only else None
    for offering in _srms_pages("/api/v1/integration/offerings/", params):
        site, created = CourseSite.objects.update_or_create(
            code=offering["code"],
            defaults={
                "title": f"{offering['course_code']} {offering['title']}",
                "term_code": offering["term_code"],
                "campus_code": offering["campus_code"],
                "source": CourseSite.Source.SRMS,
                "coursework_weight": offering["coursework_weight"],
            },
        )
        counts["sites"] += 1
        if created:
            apply_template(site)  # the GSA standard layout for a new, empty site (item 2.17)
        if offering.get("lecturer_employee_no"):
            lecturer = _upsert_lecturer(offering["lecturer_employee_no"], directory)
            Membership.objects.update_or_create(
                site=site, person=lecturer, defaults={"role": Membership.SiteRole.LECTURER, "is_active": True}
            )
            counts["lecturers"] += 1
        enrolled: set[int] = set()
        for row in _srms_pages("/api/v1/integration/enrolments/", {"offering": offering["code"]}):
            student, _ = PersonRef.objects.update_or_create(
                kind=PersonRef.Kind.STUDENT,
                external_id=row["student_no"],
                defaults={
                    "first_name": row["first_name"],
                    "last_name": row["last_name"],
                    "email": row.get("email") or "",
                    "campus_code": row.get("campus_code") or "",
                    "is_active": True,
                },
            )
            Membership.objects.update_or_create(
                site=site, person=student, defaults={"role": Membership.SiteRole.STUDENT, "is_active": True}
            )
            enrolled.add(student.id)
            counts["students"] += 1
        counts["deactivated"] += (
            Membership.objects.filter(site=site, role=Membership.SiteRole.STUDENT, is_active=True)
            .exclude(person_id__in=enrolled)
            .update(is_active=False)
        )
    return counts


def push_marks(site: CourseSite) -> dict:
    """Send each student's coursework percentage to the SRMS. The SRMS reports which it accepted."""
    if site.source != CourseSite.Source.SRMS:
        return {"offering_code": site.code, "skipped": "not an SRMS offering"}
    marks = []
    members = Membership.objects.filter(
        site=site, role=Membership.SiteRole.STUDENT, is_active=True
    ).select_related("person")
    for membership in members:
        percent = coursework_percent(site, membership.person)
        if percent is not None:
            marks.append({"student_no": membership.person.external_id, "mark": str(percent)})
    if not marks:
        return {"offering_code": site.code, "accepted": [], "locked": [], "unknown": []}
    return _srms("/api/v1/integration/coursework-marks/", data={"offering_code": site.code, "marks": marks})


def push_attendance(site: CourseSite) -> dict:
    """Send each student's attendance totals to the SRMS (decision D6, ADR 0008, item 4.15), for a course
    whose programme makes attendance a condition (attendance.models.AttendancePolicy.send_to_srms).

    The SRMS endpoint, /api/v1/integration/attendance-totals/, is SRMS work agreed with the Registrar; it
    answers like coursework-marks: which students it accepted, which were locked and which it did not know.
    """
    from attendance.models import AttendancePolicy
    from attendance.services import totals

    if site.source != CourseSite.Source.SRMS:
        return {"offering_code": site.code, "skipped": "not an SRMS offering"}
    policy = AttendancePolicy.objects.filter(site=site).first()
    if policy is None or not policy.send_to_srms:
        return {"offering_code": site.code, "skipped": "attendance is not a condition on this course"}
    rows = [
        {
            "student_no": row["student_no"],
            "sessions": row["sessions"],
            "present": row["present"],
            "late": row["late"],
            "excused": row["excused"],
            "absent": row["absent"],
            "not_recorded": row["not_recorded"],
            "percent": row["percent"],
        }
        for row in totals(site)
    ]
    if not rows:
        return {"offering_code": site.code, "accepted": [], "locked": [], "unknown": []}
    return _srms("/api/v1/integration/attendance-totals/", data={"offering_code": site.code, "totals": rows})
