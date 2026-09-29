#!/usr/bin/env bash
# Prepares the database, then runs the API, the job worker and Caddy as the application user.
# If any of the three stops, the container exits so that the platform restarts it.
set -euo pipefail
cd /app

python manage.py migrate --noinput
python manage.py seed --country GY

# First administrator, from variables the owner sets on the platform. Remove the password
# variable after the first sign-in.
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  python manage.py createsuperuser --noinput --email "${DJANGO_SUPERUSER_EMAIL:-}" \
    || echo "Administrator not created (the user name may already exist)."
fi

pids=()
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers "${WEB_CONCURRENCY:-2}" --timeout 60 &
pids+=($!)
python manage.py procrastinate worker &
pids+=($!)
caddy run --config /etc/caddy/Caddyfile --adapter caddyfile &
pids+=($!)

stop() {
  kill -TERM "${pids[@]}" 2>/dev/null || true
  wait
  exit "$1"
}
trap 'stop 0' TERM INT

wait -n || true
echo "A process stopped; shutting down so that the platform restarts the container."
stop 1
