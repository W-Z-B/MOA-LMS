#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh into a Compose stack (item 7.09), then check it.
#
#   scripts/restore.sh --yes 20261006T051500Z           a backup in BACKUP_DIR
#   scripts/restore.sh --yes /mnt/usb/20261006T051500Z  a backup directory anywhere
#   scripts/restore.sh --yes remote:20261006T051500Z    fetched first from RCLONE_REMOTE (off site)
#
# It REPLACES the stack's database and file store. Without --yes it only checks the backup's fingerprints
# and says what it would do. The private key comes from AGE_IDENTITY (a file; bring it from where the keys
# are kept, docs/runbook.md "Keys", and remove it from the host afterwards), or from gpg's keyring.
#
# Settings as for backup.sh (BACKUP_ENV_FILE, BACKUP_DIR, COMPOSE, RCLONE_REMOTE, AGE, GPG, RCLONE), and:
#   RESTORE_START_ALL   1 (default): start the whole stack afterwards; 0: leave only the database and the API
set -Eeuo pipefail
umask 077

# shellcheck source=scripts/backup-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/backup-common.sh"
RESTORE_START_ALL="${RESTORE_START_ALL:-1}"
trap 'fail "line $LINENO: $BASH_COMMAND"' ERR

confirmed=0
if [ "${1:-}" = "--yes" ]; then
  confirmed=1
  shift
fi
[ $# -eq 1 ] || fail "usage: restore.sh [--yes] <backup directory | stamp | remote:stamp>"
cd "$LMS_DIR"

source="$1"
fetched=""
if [[ "$source" == remote:* ]]; then
  [ -n "${RCLONE_REMOTE:-}" ] || fail "RCLONE_REMOTE is not set"
  fetched="$(mktemp -d)"
  trap 'rm -rf "$fetched"' EXIT
  say "fetching ${source#remote:} from $RCLONE_REMOTE"
  $RCLONE copy --checksum "$RCLONE_REMOTE/${source#remote:}" "$fetched"
  source="$fetched"
elif [ ! -d "$source" ]; then
  source="$BACKUP_DIR/$source"
fi
[ -f "$source/SHA256SUMS" ] || fail "$source is not a backup (no SHA256SUMS)"

say "checking the fingerprints of $source"
(cd "$source" && sha256sum --check --quiet SHA256SUMS) || fail "the backup does not match its fingerprints"
if [ -f "$source/database.dump.gpg" ]; then ext=gpg; else ext=age; fi
decrypt() { # file -> stdout
  if [ "$ext" = gpg ]; then
    $GPG --batch --decrypt "$1"
  else
    [ -n "${AGE_IDENTITY:-}" ] || fail "AGE_IDENTITY is not set: the private key file is needed to decrypt"
    $AGE --decrypt -i "$AGE_IDENTITY" < "$1"
  fi
}

if [ "$confirmed" != 1 ]; then
  say "the backup is whole. Run again with --yes to REPLACE the database and file store of: $COMPOSE"
  exit 0
fi

started="$(date +%s)"
say "stopping the job worker and the web server"
compose stop worker caddy web >/dev/null 2>&1 || true
say "starting the database and the API"
compose up -d db api
for _ in $(seq 1 60); do
  compose exec -T db sh -c 'pg_isready -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' && break
  sleep 2
done

say "restoring the database"
compose exec -T db sh -c 'dropdb --force --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
decrypt "$source/database.dump.$ext" \
  | compose exec -T db sh -c 'pg_restore --no-owner --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

say "restoring the file store"
decrypt "$source/files.tar.$ext" \
  | compose exec -T api sh -c 'find /srv/files -mindepth 1 -delete && tar --extract --file=- --directory=/srv/files'

say "applying any newer migrations"
compose restart api >/dev/null
compose exec -T api python manage.py migrate --noinput

# The check: the API answers healthy, Django's checks pass, the audit chain is whole, and the rows and files
# are those the manifest recorded when the backup was made.
say "checking the restored system"
for _ in $(seq 1 60); do
  if compose exec -T api python -c "import urllib.request as u; u.urlopen('http://localhost:8000/api/health/')" \
    >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
compose exec -T api python -c "
import json, urllib.request as u
body = json.load(u.urlopen('http://localhost:8000/api/health/'))
assert body['database'] and body['storage'], body
print('health', body)"
compose exec -T api python manage.py check
compose exec -T api python manage.py verify_audit_chain
rows="$(count_rows)"
files="$(count_files)"
compose exec -T -e EXPECTED="$(cat "$source/manifest.json")" -e ROWS="$rows" -e FILES="$files" api python -c "
import json, os
expected, rows, files = json.loads(os.environ['EXPECTED']), json.loads(os.environ['ROWS']), int(os.environ['FILES'])
problems = [f'{t}: {n} rows, the backup had {expected[\"rows\"][t]}' for t, n in rows.items()
            if t != 'django_migrations' and n != expected['rows'][t]]
if rows['django_migrations'] < expected['rows']['django_migrations']:
    problems.append('fewer migrations than the backup recorded')
if files != expected['files']:
    problems.append(f'{files} files, the backup had {expected[\"files\"]}')
assert not problems, problems
print('rows and files match the manifest:', rows, files)"

if [ "$RESTORE_START_ALL" = 1 ]; then
  say "starting the whole stack"
  compose up -d
fi
say "restored $(basename "$source") in $(($(date +%s) - started)) s"
