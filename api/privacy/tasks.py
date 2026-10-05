"""Every night at 04:00, the logs that the retention schedule removes without review go (item 1.19)."""

from procrastinate.contrib.django import app

from privacy.retention import purge


@app.periodic(cron="0 4 * * *")
@app.task(name="privacy.retention_purge", queue="privacy")
def retention_purge(timestamp: int | None = None) -> dict[str, int]:
    return purge()
