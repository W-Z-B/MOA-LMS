"""The record of each integration run (item 1.23): started, finished, rows sent and refused, and why."""

import logging

from django.utils import timezone

from integration.models import IntegrationRun

log = logging.getLogger(__name__)
MAX_ERRORS = 200  # a run that fails on every row keeps the first ones; the counts stay exact


class Run:
    """Counts the rows of one run as they go, and writes them when it finishes."""

    def __init__(self, kind: str, trigger: str = "schedule"):
        self.row = IntegrationRun.objects.create(kind=kind, trigger=trigger)

    def ok_(self, count: int = 1) -> None:
        self.row.ok += count

    def _error(self, ref: str, code: str, detail: str) -> None:
        if len(self.row.errors) < MAX_ERRORS:
            self.row.errors.append({"ref": ref, "code": code, "detail": detail[:300]})

    def fail(self, ref: str, code: str, detail: str) -> None:
        """A row the other system refused; the run carries on."""
        self.row.failed += 1
        self._error(ref, code, detail)

    def note(self, ref: str, code: str, detail: str) -> None:
        """Something an administrator should know that is not a failure."""
        self._error(ref, code, detail)

    def stop(self, detail: str) -> None:
        self.row.stopped = detail[:300]

    def finish(self) -> dict:
        self.row.finished_at = timezone.now()
        self.row.save()
        summary = {
            "run": self.row.pk,
            "ok": self.row.ok,
            "failed": self.row.failed,
            "stopped": self.row.stopped,
        }
        log.info("integration %s %s", self.row.kind, summary)
        return summary
