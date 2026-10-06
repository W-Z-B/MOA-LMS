"""HRMS links: campus reference data, the staff directory, and staff training completions reported to the
HRMS training record (items 1.23, 5.06)."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

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
        # TODO(D13, HRMS): the directory does not yet say who supervises whom. When it sends
        # supervisor_employee_no, approvals of staff-development enrolments go to that person.
        if row.get("supervisor_employee_no"):
            supervisors[person.pk] = row["supervisor_employee_no"]
        run.ok_()
    for person_id, number in supervisors.items():
        boss = PersonRef.objects.filter(kind=PersonRef.Kind.STAFF, external_id=number).first()
        PersonRef.objects.filter(pk=person_id).update(supervisor=boss)
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
