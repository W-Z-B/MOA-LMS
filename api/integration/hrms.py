"""HRMS links: campus reference data, the staff directory, required training (decision D13), and staff
training completions reported to the HRMS training record (items 1.23, 5.05, 5.06)."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from audit.services import record, snapshot
from courses.models import Completion, CourseSite
from integration.client import IntegrationError, call, pages, unreachable, with_retries
from integration.models import CampusRef, IntegrationRun
from integration.runs import Run
from people.models import PersonRef

# Staff the HRMS lists under these states can no longer use the LMS: their record goes inactive and the
# account closes (item 1.22).
GONE = frozenset({"separated"})


def staff_refs(employee_nos: list[str]) -> list[PersonRef]:
    """References for the named staff, from the HRMS directory. Staff the HRMS does not know are left out."""
    wanted = set(employee_nos)
    people = []
    for row in pages(settings.HRMS_API_URL, settings.HRMS_API_KEY, "/api/v1/integration/staff/"):
        if row["employee_no"] in wanted:
            person, _ = PersonRef.objects.update_or_create(
                kind=PersonRef.Kind.STAFF,
                external_id=row["employee_no"],
                defaults={
                    "first_name": row.get("first_name", ""),
                    "last_name": row.get("last_name", ""),
                    "email": row.get("email") or "",
                    "campus_code": row.get("campus_code") or "",
                    "is_active": True,
                },
            )
            people.append(person)
    return people


def sync_staff(*, trigger: str = "schedule") -> dict:
    """Every member of staff from the HRMS directory, with post, unit and campus, so that staff can use the
    staff-development catalogue and required training can be assigned by post (items 5.02, 5.05).

    Someone the HRMS lists as separated, or no longer lists at all, goes inactive here, which closes their
    account (item 1.22). Nobody is made inactive unless the whole directory was read.
    """
    run = Run(IntegrationRun.Kind.STAFF_SYNC, trigger)
    rows = []
    try:
        rows = list(pages(settings.HRMS_API_URL, settings.HRMS_API_KEY, "/api/v1/integration/staff/"))
    except IntegrationError as exc:
        run.stop(str(exc))
        return run.finish()
    seen, supervisors = set(), {}
    for row in rows:
        number = row["employee_no"]
        seen.add(number)
        values = {
            "first_name": row.get("first_name") or "",
            "last_name": row.get("last_name") or "",
            "email": row.get("email") or "",
            "campus_code": row.get("campus_code") or "",
            "post_title": row.get("position_title") or "",
            "unit_code": row.get("unit_code") or "",
            "is_active": (row.get("status") or "active") not in GONE,
        }
        person = PersonRef.objects.filter(kind=PersonRef.Kind.STAFF, external_id=number).first()
        if person is None:
            person = PersonRef.objects.create(kind=PersonRef.Kind.STAFF, external_id=number, **values)
        else:
            changed = [field for field, value in values.items() if getattr(person, field) != value]
            for field in changed:
                setattr(person, field, values[field])
            if changed:
                person.save(update_fields=[*changed, "updated_at"])  # saved one by one: closes accounts
        # The directory names each person's supervisor (supervisor_employee_no, null for none): requests to
        # join a staff-development course go to that person (staffdev.enrolment.approver_for, item 5.02).
        # A directory that does not send the field leaves the supervisor as it was.
        if "supervisor_employee_no" in row:
            supervisors[person.pk] = row["supervisor_employee_no"] or None
        run.ok_()
    for person_id, number in supervisors.items():
        boss = None
        if number:
            boss = PersonRef.objects.filter(kind=PersonRef.Kind.STAFF, external_id=number).first()
        PersonRef.objects.filter(pk=person_id).exclude(supervisor=boss).update(supervisor=boss)
    for person in PersonRef.objects.filter(kind=PersonRef.Kind.STAFF, is_active=True).exclude(
        external_id__in=seen
    ):
        person.is_active = False
        person.save(update_fields=["is_active", "updated_at"])
        run.note(person.external_id, "not_listed", "No longer in the HRMS directory: made inactive")
    return run.finish()


def sync_org() -> dict:
    payload = call(settings.HRMS_API_URL, settings.HRMS_API_KEY, "/api/v1/integration/org/")
    for campus in payload.get("campuses", []):
        CampusRef.objects.update_or_create(
            code=campus["code"], defaults={"name": campus["name"], "region": campus.get("region", "")}
        )
    return {"campuses": len(payload.get("campuses", []))}


def base_ref(completion: Completion) -> str:
    return f"lms:{completion.site.code}:{completion.person.external_id}"


def training_row(completion: Completion) -> dict:
    """What the HRMS training record is sent for one completion, with its expiry date (item 5.06)."""
    return {
        "external_ref": completion.external_ref or base_ref(completion),
        "employee_no": completion.person.external_id,
        "course": completion.site.title,
        "provider": "GSA LMS",
        "starts": completion.completed_on.isoformat(),
        "ends": completion.completed_on.isoformat(),
        "certification": completion.certificate,
        "expiry_date": completion.expires_on.isoformat() if completion.expires_on else None,
    }


def pending_training():
    return Completion.objects.filter(
        reported_at__isnull=True,
        site__kind=CourseSite.Kind.STAFF_DEVELOPMENT,
        person__kind=PersonRef.Kind.STAFF,
    ).select_related("site", "person")


def push_training(*, trigger: str = "schedule", only=None) -> dict:
    """Report unreported staff-development completions to the HRMS training record. Idempotent: the HRMS
    keeps each under its reference, so sending one twice changes nothing.

    Each completion is sent on its own. One the HRMS refuses (an employee number it does not know) is
    recorded against the run and the rest carry on (item 1.23); it is tried again on the next run. When the
    HRMS cannot be reached, even after the retries, the run stops and what is left waits for the next one.
    """
    run = Run(IntegrationRun.Kind.TRAINING_PUSH, trigger)
    pending = pending_training()
    if only is not None:
        pending = pending.filter(pk__in=only)
    for completion in pending:
        row = training_row(completion)
        try:
            with_retries(
                lambda row=row: call(
                    settings.HRMS_API_URL,
                    settings.HRMS_API_KEY,
                    "/api/v1/integration/training-completions/",
                    data=row,
                )
            )
        except IntegrationError as exc:
            if unreachable(exc):
                run.stop(f"The HRMS could not be reached: {exc}")
                break
            code = "unknown_employee" if exc.status == 404 else f"http_{exc.status}"
            run.fail(row["external_ref"], code, str(exc))
            continue
        with transaction.atomic():
            Completion.objects.filter(pk=completion.pk).update(
                reported_at=timezone.now(), external_ref=row["external_ref"]
            )
        run.ok_()
    return run.finish()


REQUIREMENT_FIELDS = (
    "site",
    "campus_code",
    "unit_code",
    "post_title",
    "due_days",
    "renewal_months",
    "is_active",
)


def _requirement_values(row: dict, site: CourseSite) -> dict:
    """The LMS's fields for one HRMS requirement. A condition the HRMS leaves null applies to everyone."""
    return {
        "site": site,
        "campus_code": (row.get("campus_code") or "")[:10],
        "unit_code": (row.get("unit_code") or "")[:20],
        "post_title": (row.get("post_title") or "")[:160],
        "due_days": max(1, int(row.get("due_days") or 30)),
        "renewal_months": row.get("renewal_months") or None,
        "is_active": True,
    }


@transaction.atomic
def _keep_requirement(row: dict, site: CourseSite) -> None:
    """Create or bring up to date the LMS's copy of one HRMS requirement, audited."""
    from staffdev.models import RequiredTraining

    values = _requirement_values(row, site)
    requirement = RequiredTraining.objects.filter(hrms_id=row["id"]).first()
    if requirement is None:
        requirement = RequiredTraining.objects.create(
            hrms_id=row["id"], source=RequiredTraining.Source.HRMS, **values
        )
        record(None, "create", requirement, after=snapshot(requirement), reason="From the HRMS")
        return
    changed = [field for field in REQUIREMENT_FIELDS if getattr(requirement, field) != values[field]]
    if not changed:
        return
    before = snapshot(requirement)
    for field in changed:
        setattr(requirement, field, values[field])
    requirement.save(update_fields=[*changed, "updated_at"])
    record(None, "update", requirement, before=before, after=snapshot(requirement), reason="From the HRMS")


@transaction.atomic
def _retire_requirement(requirement, reason: str) -> None:
    before = snapshot(requirement)
    requirement.is_active = False
    requirement.save(update_fields=["is_active", "updated_at"])
    record(None, "update", requirement, before=before, after=snapshot(requirement), reason=reason)


def sync_training_requirements(*, trigger: str = "schedule") -> dict:
    """Required training from the HRMS (decision D13, ADR 0019; item 5.05), scope training:read.

    The HRMS sends every requirement in force each time. Each is kept here under the HRMS's number
    (RequiredTraining.hrms_id, source hrms) on the staff-development course whose code it names, and the daily
    required-training run assigns it. A course code the LMS does not have is noted against the run with the
    HRMS's title, so that a course administrator can make the course; the rest of the run carries on. A
    requirement the HRMS no longer lists has been retired there and stops being in force here. Requirements
    course administrators keep in the LMS are never touched, and nothing is retired unless the whole list was
    read. A refused key (the training:read scope not given) is recorded as a failed run.
    """
    from staffdev.models import RequiredTraining

    run = Run(IntegrationRun.Kind.REQUIREMENT_SYNC, trigger)
    try:
        rows = with_retries(
            lambda: list(
                pages(
                    settings.HRMS_API_URL,
                    settings.HRMS_API_KEY,
                    "/api/v1/integration/training-requirements/",
                    params={"page_size": 500},
                )
            )
        )
    except IntegrationError as exc:
        if not unreachable(exc):
            run.fail("training-requirements", f"http_{exc.status}", f"The HRMS refused the request: {exc}")
        run.stop(str(exc))
        return run.finish()
    codes = {row.get("course_code") for row in rows if row.get("course_code")}
    sites = {
        site.code: site
        for site in CourseSite.objects.filter(code__in=codes, kind=CourseSite.Kind.STAFF_DEVELOPMENT)
    }
    kept, unmatched = set(), set()
    for row in rows:
        code, title = row.get("course_code") or "", row.get("title") or ""
        site = sites.get(code)
        if site is None:
            unmatched.add(row["id"])
            run.note(
                f"hrms:{row['id']}",
                "unmatched_course",
                f"{title}: no staff-development course has the code {code}. Make it and it is read next time."
                if code
                else f"{title}: the HRMS gives no LMS course code for it.",
            )
            continue
        _keep_requirement(row, site)
        kept.add(row["id"])
        run.ok_()
    gone = RequiredTraining.objects.filter(source=RequiredTraining.Source.HRMS, is_active=True).exclude(
        hrms_id__in=kept
    )
    for requirement in gone:
        if requirement.hrms_id in unmatched:
            _retire_requirement(requirement, "Its course in the HRMS is not one the LMS has")
            continue  # already noted as unmatched
        _retire_requirement(requirement, "Retired in the HRMS")
        run.note(
            f"hrms:{requirement.hrms_id}", "retired", "No longer listed by the HRMS: no longer in force."
        )
    return run.finish()
