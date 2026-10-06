"""The daily summary email (item 2.33): at 17:00, one email to each person who chose a summary for some
kinds of notification, listing what arrived since the last one."""

import logging

from procrastinate.contrib.django import app

from notifications.services import send_daily_summaries

log = logging.getLogger(__name__)


@app.periodic(cron="0 17 * * *")
@app.task(name="notifications.daily_summary", queue="notifications")
def daily_summary(timestamp: int | None = None) -> int:
    sent = send_daily_summaries()
    log.info("notifications.daily_summary sent %s", sent)
    return sent
