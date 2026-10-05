"""Every night at 03:30 the whole audit chain is checked (item 1.17); a broken chain alerts the
administrators and the auditor at once, and every result goes to the application log as well."""

from procrastinate.contrib.django import app

from audit import chain


@app.periodic(cron="30 3 * * *")
@app.task(name="audit.verify_chain", queue="audit")
def verify_chain(timestamp: int | None = None) -> bool:
    return chain.verify().intact
