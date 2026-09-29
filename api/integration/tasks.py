"""Scheduled ecosystem jobs (Procrastinate). Skipped quietly when a sibling system is not configured."""

import logging

from django.conf import settings
from procrastinate.contrib.django import app

from integration.client import IntegrationError

log = logging.getLogger(__name__)


@app.periodic(cron="0 2 * * *")  # 02:00 every night, after the SRMS has synced staff at 01:30
@app.task(name="integration.sync_srms", queue="integration")
def sync_srms(timestamp: int | None = None) -> dict:
    from integration import srms

    if not settings.SRMS_API_URL or not settings.SRMS_API_KEY:
        log.info("integration.sync_srms skipped: SRMS not configured")
        return {"skipped": True}
    try:
        result = srms.sync_sites()
    except IntegrationError:
        log.exception("integration.sync_srms failed")
        return {"failed": True}
    log.info("integration.sync_srms %s", result)
    return result
