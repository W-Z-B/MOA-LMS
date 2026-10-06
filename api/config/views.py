import logging
import os
import tempfile
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone

log = logging.getLogger(__name__)


def _database() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 - any failure means not ready
        log.exception("health: the database cannot be reached")
        return False


def _storage() -> bool:
    """The file store takes a write: a small file is made and removed in its .health directory (which the
    backup leaves out, so the check never changes what is being copied)."""
    try:
        directory = os.path.join(settings.MEDIA_ROOT, ".health")
        os.makedirs(directory, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, prefix="check-"):
            pass
        return True
    except OSError:
        log.exception("health: the file store cannot be written")
        return False


def _queue() -> bool:
    """A job worker has reported within QUEUE_HEARTBEAT_SECONDS."""
    from procrastinate.contrib.django.models import ProcrastinateWorker

    try:
        since = timezone.now() - timedelta(seconds=settings.QUEUE_HEARTBEAT_SECONDS)
        return ProcrastinateWorker.objects.filter(last_heartbeat__gte=since).exists()
    except Exception:  # noqa: BLE001 - reported as not working, never as a failure of the check
        return False


def health(request):
    """Liveness and readiness, used by Compose, Caddy and monitoring (item 7.10).

    503 when the database or the file store fails, because nothing can be served without them. A queue with
    no working job worker is "degraded" but still 200: pages are served, but email, reminders and the nightly
    jobs wait, and the metrics' alert says so. Only yes or no is given, never figures: anyone may ask.
    """
    database = _database()
    storage = _storage()
    queue = database and _queue()
    ready = database and storage
    status = "ok" if ready and queue else "degraded"
    body = {"status": status, "database": database, "storage": storage, "queue": queue}
    return JsonResponse(body, status=200 if ready else 503)
