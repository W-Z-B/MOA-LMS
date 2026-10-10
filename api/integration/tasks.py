"""Scheduled ecosystem jobs (Procrastinate). Skipped quietly when a sibling system is not configured."""

import logging

from django.conf import settings
from procrastinate.contrib.django import app

from core.schedule import periodic
from integration.client import IntegrationError

log = logging.getLogger(__name__)


@periodic("0 2 * * *")  # 02:00 every night, after the SRMS has synced staff at 01:30
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


def _hrms_configured() -> bool:
    return bool(settings.HRMS_API_URL and settings.HRMS_API_KEY)


@periodic("45 1 * * *")  # 01:45, before the sites at 02:00, so lecturers and staff are current
@app.task(name="integration.sync_staff", queue="integration")
def sync_staff(timestamp: int | None = None) -> dict:
    from integration import hrms

    if not _hrms_configured():
        log.info("integration.sync_staff skipped: HRMS not configured")
        return {"skipped": True}
    return hrms.sync_staff()


@periodic("0 6 * * *")  # 06:00, before the daily required-training run at 06:30 (decision D13)
@app.task(name="integration.sync_training_requirements", queue="integration")
def sync_training_requirements(timestamp: int | None = None) -> dict:
    from integration import hrms

    if not settings.HRMS_TRAINING_REQUIREMENTS_SYNC:
        return {"skipped": True}
    if not _hrms_configured():
        log.info("integration.sync_training_requirements skipped: HRMS not configured")
        return {"skipped": True}
    return hrms.sync_training_requirements()


@periodic("30 2 * * *")  # 02:30, after the sites and class lists are current (item 1.23)
@app.task(name="integration.push_marks", queue="integration")
def push_marks(timestamp: int | None = None) -> dict:
    from integration import srms

    if not settings.SRMS_API_URL or not settings.SRMS_API_KEY:
        log.info("integration.push_marks skipped: SRMS not configured")
        return {"skipped": True}
    return srms.push_all_marks()


@periodic("45 2 * * *")  # 02:45, after the nightly completion sweep (items 1.23, 5.06)
@app.task(name="integration.push_training", queue="integration")
def push_training(timestamp: int | None = None) -> dict:
    from integration import hrms

    if not _hrms_configured():
        log.info("integration.push_training skipped: HRMS not configured")
        return {"skipped": True}
    return hrms.push_training()


@app.task(name="integration.report_completion", queue="integration", retry=3)
def report_completion(completion_id: int) -> dict:
    """Send one completion to the HRMS as soon as it is recorded (item 5.06). The nightly push sends it
    instead if this cannot."""
    from integration import hrms

    if not _hrms_configured():
        return {"skipped": True}
    return hrms.push_training(trigger="completion", only=[completion_id])
