"""Every night at 04:30, after the retention purge, terms close and old ones are archived (item 7.12)."""

from procrastinate.contrib.django import app

from core.schedule import periodic
from terms import lifecycle


@periodic("30 4 * * *")
@app.task(name="terms.lifecycle", queue="terms")
def term_lifecycle(timestamp: int | None = None) -> dict:
    return lifecycle.run()
