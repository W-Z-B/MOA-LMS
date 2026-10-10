"""Scheduled jobs at GSA's local time.

procrastinate (3.10, as pinned) reads a periodic task's cron line in UTC: it hands croniter a Unix timestamp
and has no time-zone option. Every schedule in the code is written in local time (TIME_ZONE,
America/Guyana), so each one goes through `periodic` below, which turns the local hours into UTC ones.

Guyana keeps UTC-4 all year (no daylight saving since 1991), so one fixed shift is exact. A zone that does
change its clock cannot be expressed as one cron line; local_cron refuses it rather than run jobs an hour
out for half the year (core/test_schedule.py checks the zone and every job's local time).
"""

import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def utc_offset_hours(zone: str | None = None, *, year: int | None = None) -> int:
    """How many hours the zone is behind UTC (Guyana: 4), the same in winter and summer, or an error."""
    tz = ZoneInfo(zone or settings.TIME_ZONE)
    year = year or datetime.date.today().year
    offsets = {datetime.datetime(year, month, 15, 12, tzinfo=tz).utcoffset() for month in (1, 4, 7, 10)}
    if len(offsets) != 1:
        raise ImproperlyConfigured(f"{tz.key} changes its clock: scheduled jobs cannot follow it.")
    seconds = -offsets.pop().total_seconds()
    if seconds % 3600:
        raise ImproperlyConfigured(f"{tz.key} is not a whole number of hours from UTC.")
    return int(seconds // 3600)


def _hours(field: str) -> list[int] | None:
    """The hours a cron hour field names, or None for every hour."""
    if field == "*":
        return None
    hours: list[int] = []
    for part in field.split(","):
        if "/" in part:
            raise ValueError(f"Write the hours of {field!r} out in full for a local schedule.")
        first, _, last = part.partition("-")
        hours.extend(range(int(first), int(last or first) + 1))
    if any(not 0 <= hour <= 23 for hour in hours):
        raise ValueError(f"{field!r} is not a list of hours.")
    return hours


def local_cron(cron: str, *, zone: str | None = None) -> str:
    """The UTC cron line that runs at the local times `cron` names (minute hour day month weekday)."""
    fields = cron.split()
    if len(fields) != 5:
        raise ValueError(f"{cron!r} is not a five-field cron line.")
    minute, hour, *days = fields
    hours = _hours(hour)
    if hours is None:
        return cron  # every hour is every hour in any zone
    shift = utc_offset_hours(zone)
    moved = [hour + shift for hour in hours]
    if any(not 0 <= hour <= 23 for hour in moved) and days != ["*", "*", "*"]:
        # The job would cross midnight in UTC, onto another day or weekday than the one written.
        raise ValueError(f"{cron!r} crosses midnight in UTC; give it days of '*' or an earlier hour.")
    return " ".join([minute, ",".join(str(h % 24) for h in sorted(moved, key=lambda h: h % 24)), *days])


def periodic(cron: str, **options):
    """`app.periodic`, with the cron line in local time."""
    from procrastinate.contrib.django import app

    return app.periodic(cron=local_cron(cron), **options)
