"""Nightly insight jobs (Procrastinate): outcomes from the SRMS, early alerts, and results to the SRMS."""

import logging

from django.conf import settings
from procrastinate.contrib.django import app

from core.schedule import periodic

log = logging.getLogger(__name__)


@periodic("10 2 * * *")  # 02:10, after the sites at 02:00, so every course code is known (3.11)
@app.task(name="insights.sync_outcomes", queue="integration")
def sync_outcomes(timestamp: int | None = None) -> dict:
    from insights import srms

    if not srms.configured():
        log.info("insights.sync_outcomes skipped: SRMS not configured")
        return {"skipped": True}
    return srms.sync_outcomes()


@periodic("50 2 * * *")  # 02:50, after the coursework totals at 02:30 (item 6.10)
@app.task(name="insights.push_competency", queue="integration")
def push_competency(timestamp: int | None = None) -> dict:
    from insights import srms

    if not settings.SRMS_COMPETENCY_PUSH or not srms.configured():
        log.info("insights.push_competency skipped: off (SRMS_COMPETENCY_PUSH) or SRMS not configured")
        return {"skipped": True}
    return srms.push_all_competency()


@periodic("15 4 * * *")  # 04:15, once the night's marks and class lists are in (item 6.05)
@app.task(name="insights.early_alerts", queue="insights")
def early_alerts(timestamp: int | None = None) -> dict:
    from insights import alerts

    result = alerts.nightly()
    log.info("insights.early_alerts %s", result)
    return result
