"""gunicorn settings for production (deploy/compose.prod.yml). With PROMETHEUS_MULTIPROC_DIR set, each worker
process writes its request counts there and /api/metrics adds them up (item 7.10); the directory is emptied
when gunicorn starts and a stopped worker's figures are retired."""

import os
import shutil


def on_starting(server):
    directory = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if directory:
        shutil.rmtree(directory, ignore_errors=True)
        os.makedirs(directory, exist_ok=True)


def child_exit(server, worker):
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)


# Keep idle connections from Caddy open longer than Caddy does (60 s, deploy/Caddyfile.prod), so that Caddy,
# not gunicorn, closes them and never reuses one just closed (item 7.08).
keepalive = 75

# Production settings (deploy/compose.prod.yml runs `gunicorn -c config/gunicorn.py config.wsgi:application`).
bind = "0.0.0.0:8000"
# Processes use the cores; threads in each overlap the waits on the database (item 7.08, docs/performance.md).
# About two processes a core suits the host.
workers = int(os.environ.get("WEB_CONCURRENCY", "4"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"
# With threads, `timeout` is how long a worker process may stop answering gunicorn itself before it is
# restarted, not a limit on one request: a slow request, such as a lecture video of up to 1 GB coming in over
# a poor line, keeps its thread busy without the process being killed. How long a request may take is set
# at the edge, by path, in deploy/Caddyfile.prod: 60 seconds for the API's answer, 15 minutes after a video
# upload has arrived (docs/runbook.md, "Long uploads").
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30  # a stop or a release lets requests under way finish for this long
# Restart each process after a number of requests (with a little randomness so they do not all restart at
# once), which bounds any slow growth in memory.
max_requests = 2000
max_requests_jitter = 200
# The heartbeat file of each worker lives in memory, not on the container's (read-only) disk.
worker_tmp_dir = "/dev/shm"
# Requests are logged by the application itself, as JSON with their request id (config/observability.py).
accesslog = None
errorlog = "-"
