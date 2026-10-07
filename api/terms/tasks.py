"""Every night at 04:30, after the retention purge, terms close and old ones are archived (item 7.12)."""

from procrastinate.contrib.django import app

from terms import lifecycle


@app.periodic(cron="30 4 * * *")
@app.task(name="terms.lifecycle", queue="terms")
def term_lifecycle(timestamp: int | None = None) -> dict:
    return lifecycle.run()
