"""Monitoring (item 7.10): the health check, structured logs, error groups and the metrics endpoint."""

import json
import logging
import sys
from datetime import timedelta

import pytest
from django.db import connection
from django.test import Client
from django.utils import timezone

from config import observability


def _record(message="hello", exc_info=None, **extra):
    record = logging.LogRecord("lms.test", logging.ERROR, __file__, 1, message, None, exc_info)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_logs_are_one_json_object_a_line_with_extra_fields_and_the_request_id():
    token = observability.request_id.set("abc123")
    try:
        line = observability.JsonFormatter().format(_record(route="assignment-detail", status=200))
    finally:
        observability.request_id.reset(token)
    entry = json.loads(line)
    assert entry["message"] == "hello" and entry["level"] == "ERROR" and entry["logger"] == "lms.test"
    assert (
        entry["request_id"] == "abc123" and entry["route"] == "assignment-detail" and entry["status"] == 200
    )
    assert "\n" not in line


def _fail(kind=ValueError):
    raise kind("boom")


def test_an_error_carries_its_type_its_trace_and_a_stable_group():
    groups = []
    for kind in (ValueError, ValueError, KeyError):
        try:
            _fail(kind)
        except Exception:  # noqa: BLE001
            entry = json.loads(observability.JsonFormatter().format(_record(exc_info=sys.exc_info())))
            groups.append(entry["error"]["group"])
    assert entry["error"]["type"] == "KeyError" and "boom" in entry["error"]["trace"]
    assert groups[0] == groups[1] != groups[2] and len(groups[0]) == 12


@pytest.mark.django_db
def test_every_answer_carries_a_request_id_and_is_counted(caplog):
    client = Client()
    given = client.get("/api/v1/sites/", HTTP_X_REQUEST_ID="from-caddy-1")
    assert given["X-Request-ID"] == "from-caddy-1"
    made = client.get("/api/v1/sites/", HTTP_X_REQUEST_ID="not valid!")
    assert len(made["X-Request-ID"]) == 32  # a forged or odd id is replaced
    before = observability.REQUESTS.labels("GET", "site-list", "4xx")._value.get()
    with caplog.at_level(logging.INFO, logger="lms.request"):
        client.get("/api/v1/sites/")
    assert observability.REQUESTS.labels("GET", "site-list", "4xx")._value.get() == before + 1
    entry = [r for r in caplog.records if r.name == "lms.request"][-1]
    assert entry.route == "site-list" and entry.status == 403 and entry.user_id is None
    with caplog.at_level(logging.INFO, logger="lms.request"):
        Client().get("/api/health/")
        Client().get("/no/such/page/")
    routes = [r.route for r in caplog.records if r.name == "lms.request"]
    assert "health" not in routes and routes[-1] == "unmatched"  # the health check is not logged


@pytest.mark.django_db
def test_an_unhandled_error_is_counted_by_group(settings):
    from django.urls import path

    def broken(request):
        raise RuntimeError("the database said no")

    import config.urls

    settings.ROOT_URLCONF = type(
        "U", (), {"urlpatterns": [path("boom/", broken, name="boom"), *config.urls.urlpatterns]}
    )
    client = Client(raise_request_exception=False)
    before = observability.SERVER_ERRORS.labels("boom")._value.get()
    assert client.get("/boom/").status_code == 500
    assert observability.SERVER_ERRORS.labels("boom")._value.get() == before + 1
    samples = observability.UNHANDLED.collect()[0].samples
    assert any(s.value >= 1 for s in samples)


@pytest.mark.django_db
def test_health_checks_the_database_the_file_store_and_the_queue(settings, tmp_path):
    from procrastinate.contrib.django.models import ProcrastinateWorker

    answer = Client().get("/api/health/")
    assert answer.status_code == 200
    assert answer.json() == {"status": "degraded", "database": True, "storage": True, "queue": False}
    with connection.cursor() as cursor:  # a worker reporting in, as procrastinate does
        cursor.execute("INSERT INTO procrastinate_workers DEFAULT VALUES")
    assert ProcrastinateWorker.objects.count() == 1
    assert Client().get("/api/health/").json()["status"] == "ok"

    blocked = tmp_path / "not-a-directory"
    blocked.write_text("a file where the store should be")
    settings.MEDIA_ROOT = blocked
    answer = Client().get("/api/health/")
    assert answer.status_code == 503 and answer.json()["storage"] is False


def test_health_says_not_ready_without_the_database(monkeypatch):
    from config import views

    def down():
        raise OSError("connection refused")

    monkeypatch.setattr(views.connection, "cursor", down)
    answer = views.health(None)
    assert answer.status_code == 503
    assert json.loads(answer.content)["database"] is False and json.loads(answer.content)["queue"] is False


@pytest.mark.django_db
def test_metrics_need_the_token(settings):
    settings.METRICS_TOKEN = ""
    assert Client().get("/api/metrics").status_code == 404  # no monitoring: nothing there
    settings.METRICS_TOKEN = "scrape-token-for-tests"
    assert Client().get("/api/metrics").status_code == 401
    assert Client().get("/api/metrics", HTTP_AUTHORIZATION="Bearer wrong").status_code == 401
    assert Client().get("/api/metrics", HTTP_AUTHORIZATION="Bearer scrape-token-for-tests").status_code == 200


@pytest.mark.django_db
def test_metrics_report_the_queue_the_sibling_runs_and_the_audit_chain(settings):
    from audit import chain
    from integration.models import IntegrationRun

    settings.METRICS_TOKEN = "scrape-token-for-tests"
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO procrastinate_jobs (queue_name, task_name, args, status) "
            "VALUES ('notifications', 'notifications.daily_summary', '{}', 'todo') RETURNING id"
        )
        job = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO procrastinate_events (job_id, type, at) VALUES (%s, 'deferred', %s)",
            [job, timezone.now() - timedelta(minutes=10)],
        )
        cursor.execute("INSERT INTO procrastinate_workers DEFAULT VALUES")
    IntegrationRun.objects.create(kind="marks_push", failed=2, finished_at=timezone.now())
    IntegrationRun.objects.create(kind="staff_sync", ok=5, finished_at=timezone.now())
    chain.verify()
    Client().get("/api/v1/sites/")  # one request, so that the request metrics exist

    text = Client().get("/api/metrics", HTTP_AUTHORIZATION="Bearer scrape-token-for-tests").content.decode()
    assert 'lms_job_queue_jobs{queue="notifications",status="todo"} 1.0' in text
    oldest = next(
        line for line in text.splitlines() if line.startswith("lms_job_queue_oldest_waiting_seconds ")
    )
    assert 590 < float(oldest.split()[1]) < 700
    assert "lms_job_workers_alive 1.0" in text
    assert 'lms_integration_runs_failed_24h{kind="marks_push"} 1.0' in text
    assert 'lms_integration_last_run_ok{kind="marks_push"} 0.0' in text
    assert 'lms_integration_last_run_ok{kind="staff_sync"} 1.0' in text
    assert "lms_audit_chain_intact 1.0" in text
    assert 'lms_http_requests_total{method="GET",route="site-list",status="4xx"}' in text
    assert "lms_http_request_duration_seconds_bucket" in text


def test_metrics_add_up_gunicorn_processes(monkeypatch, tmp_path):
    from prometheus_client import CollectorRegistry

    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    assert isinstance(observability._counters(), CollectorRegistry)
    assert observability._counters() is not observability.REGISTRY


@pytest.mark.django_db
def test_api_answers_are_never_cached(student, client_for):
    """ASVS 8.2.1, 14.4.2."""
    answer = client_for(student.user).get("/api/v1/auth/me/")
    assert answer["Cache-Control"] == "no-store"
    assert Client().get("/api/health/")["Cache-Control"] == "no-store"


def test_an_unhandled_error_answers_with_a_reference_not_the_error():
    """ASVS 7.4.1: the {code, detail} shape with the request's id, which finds the error in the log."""
    token = observability.request_id.set("ref123")
    try:
        answer = observability.server_error(None)
    finally:
        observability.request_id.reset(token)
    body = json.loads(answer.content)
    assert answer.status_code == 500 and body["code"] == "server_error" and body["reference"] == "ref123"
    assert "ref123" in body["detail"]


def test_a_sibling_systems_next_page_elsewhere_is_not_followed(monkeypatch, settings):
    """ASVS 5.2.6, 12.6.1: the service key goes only to the system it belongs to."""
    from integration import client

    answers = {
        "https://srms.example/api/x/": {"results": [1], "next": "/api/x/?page=2"},
        "/api/x/?page=2": {"results": [2], "next": "https://evil.example/steal"},
    }
    monkeypatch.setattr(
        client,
        "call",
        lambda base, key, path, params=None: answers[
            path if path.startswith("/api/x/?") else base + path[1:]
        ],
    )
    rows = client.pages("https://srms.example/", "key", "/api/x/")
    assert next(rows) == 1 and next(rows) == 2
    with pytest.raises(client.IntegrationError, match="another system"):
        next(rows)
