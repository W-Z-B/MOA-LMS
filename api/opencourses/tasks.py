"""Registrations whose link was never followed are deleted once it expires (item 5.07)."""

import logging

from procrastinate.contrib.django import app

log = logging.getLogger(__name__)


@app.periodic(cron="40 3 * * *")
@app.task(name="opencourses.purge_registrations", queue="notifications")
def purge_registrations(timestamp: int | None = None) -> int:
    from opencourses.services import purge_expired

    deleted = purge_expired()
    log.info("opencourses.purge_registrations deleted %s", deleted)
    return deleted
