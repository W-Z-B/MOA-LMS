"""Peer review starts by itself: each hour, work past its due date is given out for review (item 4.13)."""

import logging

from procrastinate.contrib.django import app

from core.schedule import periodic

log = logging.getLogger(__name__)


@periodic("20 * * * *")
@app.task(name="peerreview.allocate_due", queue="notifications")
def allocate_due(timestamp: int | None = None) -> int:
    from peerreview.services import allocate_due as run

    made = run()
    log.info("peerreview.allocate_due made %s reviews", made)
    return made
