"""HRMS links: campus reference data, and staff training completions reported to the HRMS."""

from django.conf import settings
from django.utils import timezone

from courses.models import Completion, CourseSite
from integration.client import call
from integration.models import CampusRef
from people.models import PersonRef


def sync_org() -> dict:
    payload = call(settings.HRMS_API_URL, settings.HRMS_API_KEY, "/api/v1/integration/org/")
    for campus in payload.get("campuses", []):
        CampusRef.objects.update_or_create(
            code=campus["code"], defaults={"name": campus["name"], "region": campus.get("region", "")}
        )
    return {"campuses": len(payload.get("campuses", []))}


def push_training() -> dict:
    """Report unreported staff-development completions to the HRMS training record. Idempotent."""
    pending = Completion.objects.filter(
        reported_at__isnull=True,
        site__kind=CourseSite.Kind.STAFF_DEVELOPMENT,
        person__kind=PersonRef.Kind.STAFF,
    ).select_related("site", "person")
    reported = 0
    for completion in pending:
        call(
            settings.HRMS_API_URL,
            settings.HRMS_API_KEY,
            "/api/v1/integration/training-completions/",
            data={
                "external_ref": f"lms:{completion.site.code}:{completion.person.external_id}",
                "employee_no": completion.person.external_id,
                "course": completion.site.title,
                "provider": "GSA LMS",
                "starts": completion.completed_on.isoformat(),
                "ends": completion.completed_on.isoformat(),
                "certification": completion.certificate,
            },
        )
        completion.reported_at = timezone.now()
        completion.save(update_fields=["reported_at", "updated_at"])
        reported += 1
    return {"reported": reported}
