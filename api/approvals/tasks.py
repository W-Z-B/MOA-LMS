"""The daily chase of decisions that have waited too long (ported from the HRMS). Weekdays at 07:00."""

import logging

from procrastinate.contrib.django import app

from approvals.time_limits import chase

log = logging.getLogger(__name__)


@app.periodic(cron="0 7 * * 1-5")
@app.task(name="approvals.chase_decisions", queue="approvals")
def chase_decisions(timestamp: int | None = None) -> dict:
    counts = chase()
    log.info("approvals.chase_decisions %s", counts)
    return counts
