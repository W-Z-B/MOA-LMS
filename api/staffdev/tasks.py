"""Nightly and daily staff-development runs (Procrastinate)."""

import logging

from procrastinate.contrib.django import app

from core.schedule import periodic

log = logging.getLogger(__name__)


@periodic("15 2 * * *")  # 02:15, before completions go to the HRMS at 02:45 (items 5.03, 5.06)
@app.task(name="staffdev.completion_sweep", queue="staffdev")
def completion_sweep(timestamp: int | None = None) -> dict:
    from staffdev.completion import sweep

    counts = sweep()
    log.info("staffdev.completion_sweep %s", counts)
    return counts


@periodic("30 6 * * *")  # 06:30, after the staff directory is current (item 5.05)
@app.task(name="staffdev.required_training", queue="staffdev")
def required_training(timestamp: int | None = None) -> dict:
    from staffdev.required import daily

    counts = daily()
    log.info("staffdev.required_training %s", counts)
    return counts
