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
