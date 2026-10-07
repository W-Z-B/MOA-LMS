# Shared by backup.sh, restore.sh and restore-drill.sh (item 7.09). Sourced, never run.
# shellcheck shell=bash

LMS_DIR="${LMS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKUP_ENV_FILE="${BACKUP_ENV_FILE:-/etc/gsa-lms/backup.env}"
# shellcheck disable=SC1090
if [ -r "$BACKUP_ENV_FILE" ]; then . "$BACKUP_ENV_FILE"; fi

BACKUP_DIR="${BACKUP_DIR:-/var/backups/gsa-lms}"
COMPOSE="${COMPOSE:-docker compose -f compose.yml -f deploy/compose.prod.yml}"
AGE="${AGE:-age}"
GPG="${GPG:-gpg}"
RCLONE="${RCLONE:-rclone}"
SCRIPT_NAME="$(basename "$0" .sh)"

say() { printf '%s %s: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$SCRIPT_NAME" "$*"; }
fail() {
  say "FAILED: $*"
  exit 1
}
compose() { $COMPOSE "$@"; }

# The rows a restore is checked against, as one JSON object: people, courses, work, attempts, the audit log.
count_rows() {
  compose exec -T db sh -c 'psql -At --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' <<'SQL'
SELECT json_build_object(
  'auth_user', (SELECT count(*) FROM auth_user),
  'people_personref', (SELECT count(*) FROM people_personref),
  'courses_coursesite', (SELECT count(*) FROM courses_coursesite),
  'assessments_submission', (SELECT count(*) FROM assessments_submission),
  'quizzes_attempt', (SELECT count(*) FROM quizzes_attempt),
  'audit_auditlog', (SELECT count(*) FROM audit_auditlog),
  'django_migrations', (SELECT count(*) FROM django_migrations));
SQL
}

# The number of files in the file store.
count_files() {
  compose exec -T api sh -c 'find /srv/files -type f ! -path "/srv/files/.health/*" | wc -l' | tr -d '[:space:]'
}
