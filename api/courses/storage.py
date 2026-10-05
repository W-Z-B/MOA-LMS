"""Storage allowance for each course site (item 2.20).

Every site may keep files up to an allowance: SITE_STORAGE_ALLOWANCE_MB (2 GB by default), or a figure a
course administrator sets for that site. Usage is the sum of the sizes of the site's files. Teaching staff
are warned from 80% and a file that would take the site past its allowance is refused.
"""

from django.conf import settings
from django.db.models import Sum
from rest_framework import status
from rest_framework.exceptions import APIException

from courses.models import ContentItem, CourseSite

MB = 1024 * 1024
WARN_AT = 80  # per cent


class StorageFull(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "storage_full"
    default_detail = "This course's storage allowance is full."


def size_in_words(size: int) -> str:
    if size >= 1024 * MB:
        return f"{size / (1024 * MB):.1f} GB".replace(".0 GB", " GB")
    if size >= MB:
        return f"{size / MB:.0f} MB"
    return f"{max(size // 1024, 1)} KB" if size else "nothing"


def allowance(site: CourseSite) -> int:
    """The site's allowance in bytes."""
    megabytes = site.storage_allowance_mb
    return (megabytes if megabytes is not None else settings.SITE_STORAGE_ALLOWANCE_MB) * MB


def used(site: CourseSite) -> int:
    return ContentItem.objects.filter(module__site=site).aggregate(total=Sum("file_size"))["total"] or 0


def refusal(site: CourseSite, extra: int, freed: int = 0) -> str | None:
    """Why `extra` more bytes (after `freed` are released) do not fit, or None when they do."""
    room, now = allowance(site), used(site) - freed
    if now + extra <= room:
        return None
    return (
        f"This course has used {size_in_words(now)} of its {size_in_words(room)} storage allowance, and "
        f"this needs {size_in_words(extra)} more. Remove files the course no longer needs, or ask a course "
        "administrator for a larger allowance."
    )


def require_room(site: CourseSite, extra: int, freed: int = 0) -> None:
    reason = refusal(site, extra, freed)
    if reason:
        raise StorageFull(reason)


def summary(site: CourseSite) -> dict:
    """Usage, allowance and, from 80%, a warning in words."""
    room, now = allowance(site), used(site)
    percent = round(now * 100 / room, 1) if room else 100.0
    warning = None
    if percent >= WARN_AT:
        warning = (
            f"This course has used {percent:.0f}% of its {size_in_words(room)} storage allowance. Remove "
            "files the course no longer needs before it is full."
        )
    return {"used_bytes": now, "allowance_bytes": room, "percent": percent, "warning": warning}


def largest_files(site: CourseSite, limit: int = 20):
    """The site's biggest files first, for housekeeping."""
    return (
        ContentItem.objects.filter(module__site=site, file_size__gt=0)
        .select_related("module")
        .order_by("-file_size", "id")[:limit]
    )
