"""Monitoring (item 7.10): structured logs, the request log, error groups and the metrics endpoint.

Nothing is sent to an outside service. Logs are one JSON object per line on standard output, for the host's
log collector; errors carry a short "group" so that the same fault, however often it happens, can be counted
and found as one (docs/runbook.md, "Errors"). Metrics are served at /api/metrics in the Prometheus text format
(prometheus_client, Apache 2.0) to a scraper holding METRICS_TOKEN; Prometheus and Alertmanager (Apache 2.0)
turn them into alerts (deploy/monitoring/).

Under gunicorn, each worker process counts its own requests: set PROMETHEUS_MULTIPROC_DIR to an empty
directory (deploy/compose.prod.yml does) and the endpoint adds the processes' counts together.
"""

import hashlib
import hmac
import json
import logging
import os
import re
import time
import traceback
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db.models import Count, Min, Q
from django.http import HttpResponse
from django.utils import timezone
from prometheus_client import REGISTRY, CollectorRegistry, Counter, Histogram, generate_latest, multiprocess
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.exposition import CONTENT_TYPE_LATEST

request_id: ContextVar[str] = ContextVar("request_id", default="-")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# Attributes every log record has; anything else on a record was passed in `extra` and is logged as a field.
_STANDARD = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}
# Requests not written to the request log: the health check runs every few seconds.
QUIET = {"health", "metrics"}

REQUESTS = Counter("lms_http_requests", "Requests answered", ["method", "route", "status"])
LATENCY = Histogram(
    "lms_http_request_duration_seconds",
    "Time to answer a request",
    ["method", "route"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
SERVER_ERRORS = Counter("lms_http_server_errors", "Answers with a 5xx status", ["route"])
UNHANDLED = Counter("lms_unhandled_errors", "Errors the code did not handle, by error group", ["group"])


def error_group(exc_info) -> str:
    """Twelve characters naming a fault: the error's type and the innermost function of the LMS's own code it
    passed through (not the line number, so that an unrelated change does not split one fault into two)."""
    kind, _, tb = exc_info
    frames = traceback.extract_tb(tb)
    own = [
        f for f in frames if "site-packages" not in f.filename and "/lib/python" not in f.filename
    ] or frames
    where = f"{os.path.basename(own[-1].filename)}:{own[-1].name}" if own else "-"
    return hashlib.sha256(f"{kind.__name__}|{where}".encode()).hexdigest()[:12]


class JsonFormatter(logging.Formatter):
    """One JSON object per line: time, level, logger, message, the request it belongs to, any extra fields,
    and for an error its type, group and trace."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id.get(),
        }
        entry.update({k: v for k, v in vars(record).items() if k not in _STANDARD and not k.startswith("_")})
        entry.pop("request", None)  # Django attaches the request to its own error records
        if record.exc_info and record.exc_info[0] is not None:
            entry["error"] = {
                "type": record.exc_info[0].__name__,
                "group": error_group(record.exc_info),
                "trace": self.formatException(record.exc_info),
            }
        return json.dumps(entry, default=str)


def route_of(request) -> str:
    """A name for what was asked for that never carries an id or a token: the URL pattern's name."""
    match = getattr(request, "resolver_match", None)
    if match is None:
        return "unmatched"
    return match.url_name or match.view_name or "unnamed"


class RequestObservabilityMiddleware:
    """Gives every request an id (kept from Caddy's X-Request-ID when it sends one), times it, counts it, and
    writes one line to the request log: the method, the route's name, the status, the time and the account.
    Never the address's ids, its query string or the body."""

    log = logging.getLogger("lms.request")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        given = request.META.get("HTTP_X_REQUEST_ID", "")
        token = request_id.set(given if REQUEST_ID.match(given) else uuid.uuid4().hex)
        started = time.perf_counter()
        try:
            response = self.get_response(request)
            elapsed = time.perf_counter() - started
            route = route_of(request)
            REQUESTS.labels(request.method, route, f"{response.status_code // 100}xx").inc()
            LATENCY.labels(request.method, route).observe(elapsed)
            if response.status_code >= 500:
                SERVER_ERRORS.labels(route).inc()
            response["X-Request-ID"] = request_id.get()
            if route not in QUIET:
                user = getattr(request, "user", None)
                self.log.info(
                    "request",
                    extra={
                        "method": request.method,
                        "route": route,
                        "status": response.status_code,
                        "duration_ms": round(elapsed * 1000, 1),
                        "user_id": user.pk if user is not None and user.is_authenticated else None,
                    },
                )
            return response
        finally:
            request_id.reset(token)

    def process_exception(self, request, exception):
        UNHANDLED.labels(error_group((type(exception), exception, exception.__traceback__))).inc()


class StateCollector:
    """What the database says at the moment of the scrape: the job queue, the workers, the sibling-system
    runs and the audit chain. Read fresh each time, so every gunicorn process reports the same."""

    def collect(self):
        from procrastinate.contrib.django.models import (
            ProcrastinateEvent,
            ProcrastinateJob,
            ProcrastinateWorker,
        )

        from audit.models import AuditCheck
        from integration.models import IntegrationRun

        now = timezone.now()
        jobs = GaugeMetricFamily(
            "lms_job_queue_jobs", "Jobs in the queue by state", labels=["queue", "status"]
        )
        for row in ProcrastinateJob.objects.values("queue_name", "status").annotate(n=Count("id")).order_by():
            jobs.add_metric([row["queue_name"], row["status"]], row["n"])
        yield jobs

        waiting = ProcrastinateJob.objects.filter(status="todo").filter(
            Q(scheduled_at__isnull=True) | Q(scheduled_at__lte=now)
        )
        oldest = ProcrastinateEvent.objects.filter(job__in=waiting, type="deferred").aggregate(at=Min("at"))[
            "at"
        ]
        yield GaugeMetricFamily(
            "lms_job_queue_oldest_waiting_seconds",
            "How long the oldest job due to run has waited (0 when none waits)",
            value=(now - oldest).total_seconds() if oldest else 0,
        )
        alive = ProcrastinateWorker.objects.filter(
            last_heartbeat__gte=now - timedelta(seconds=settings.QUEUE_HEARTBEAT_SECONDS)
        ).count()
        yield GaugeMetricFamily(
            "lms_job_workers_alive", "Job workers that have reported recently", value=alive
        )

        failed = GaugeMetricFamily(
            "lms_integration_runs_failed_24h",
            "Runs to or from the HRMS and SRMS in the last day that stopped or had rows refused",
            labels=["kind"],
        )
        last_ok = GaugeMetricFamily(
            "lms_integration_last_run_ok",
            "1 when the latest run of the kind finished cleanly",
            labels=["kind"],
        )
        last_at = GaugeMetricFamily(
            "lms_integration_last_run_timestamp_seconds",
            "When the latest run of the kind started",
            labels=["kind"],
        )
        bad = Q(failed__gt=0) | ~Q(stopped="") | Q(finished_at__isnull=True)
        for kind, _ in IntegrationRun.Kind.choices:
            runs = IntegrationRun.objects.filter(kind=kind)
            failed.add_metric([kind], runs.filter(bad, started_at__gte=now - timedelta(days=1)).count())
            latest = runs.order_by("-started_at", "-id").first()
            if latest is not None:
                clean = latest.finished_at is not None and not latest.failed and not latest.stopped
                last_ok.add_metric([kind], 1 if clean else 0)
                last_at.add_metric([kind], latest.started_at.timestamp())
        yield failed
        yield last_ok
        yield last_at

        check = AuditCheck.objects.order_by("-checked_at", "-id").first()
        intact = GaugeMetricFamily(
            "lms_audit_chain_intact",
            "1 when the latest check of the audit chain found it whole, 0 when broken",
        )
        checked = GaugeMetricFamily(
            "lms_audit_chain_checked_timestamp_seconds", "When the chain was last checked"
        )
        if check is not None:
            intact.add_metric([], 1 if check.intact else 0)
            checked.add_metric([], check.checked_at.timestamp())
        yield intact
        yield checked


def _counters() -> CollectorRegistry:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    return REGISTRY


def metrics(request):
    """The Prometheus text format, for a scraper sending "Authorization: Bearer <METRICS_TOKEN>". Not found
    when no token is set, so a deployment that does not monitor shows nothing."""
    token = settings.METRICS_TOKEN
    if not token:
        return HttpResponse(status=404)
    given = request.META.get("HTTP_AUTHORIZATION", "")
    if not hmac.compare_digest(given.encode(), f"Bearer {token}".encode()):
        return HttpResponse(status=401, headers={"WWW-Authenticate": 'Bearer realm="metrics"'})
    state = CollectorRegistry()
    state.register(StateCollector())
    return HttpResponse(
        generate_latest(_counters()) + generate_latest(state), content_type=CONTENT_TYPE_LATEST
    )
