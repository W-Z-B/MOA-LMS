#!/usr/bin/env bash
# Daily encrypted backup of the GSA LMS (item 7.09): the database and the file store, encrypted with age
# before anything touches the disk, kept by a rotation, and copied off site with rclone. Run it from cron on
# the host that runs the Compose stack, as a user that may use Docker:
#
#   15 1 * * *  /opt/gsa-lms/scripts/backup.sh >> /var/log/gsa-lms-backup.log 2>&1
#
# Settings come from the environment or from BACKUP_ENV_FILE (default /etc/gsa-lms/backup.env):
#   BACKUP_DIR              where backups are kept on this host (default /var/backups/gsa-lms)
#   AGE_RECIPIENTS          file of age public keys ("age1..."), one a line: who can decrypt. Keep the private
#                           keys OFF this host (docs/runbook.md, "Keys"); the host only ever encrypts.
#   BACKUP_ENCRYPT          age (default) or gpg; with gpg, GPG_RECIPIENT names the public key
#   BACKUP_KEEP_DAILY       newest daily backups kept (default 14)
#   BACKUP_KEEP_WEEKLY      newest weekly backups kept, the last of each week (default 8)
#   BACKUP_KEEP_MONTHLY     newest monthly backups kept, the last of each month (default 12)
#   RCLONE_REMOTE           off-site destination, e.g. "gsa-offsite:lms-backups" (rclone.conf names it). Empty:
#                           no copy off site, which the script reports as a failure unless BACKUP_OFFSITE=0
#   BACKUP_METRICS_FILE     a node_exporter text file for the monitoring (deploy/monitoring/alerts.yml)
#   COMPOSE                 how to reach the stack (default: docker compose -f compose.yml -f deploy/compose.prod.yml)
#   AGE, GPG, RCLONE        the programs, if not on the PATH under those names
#
# Every piece is checked: a failed dump, archive, encryption or copy stops the script with a non-zero status
# and no partial backup is left in the rotation. RPO 24 hours, RTO 8 hours: docs/runbook.md.
set -Eeuo pipefail
umask 077

# shellcheck source=scripts/backup-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/backup-common.sh"

BACKUP_ENCRYPT="${BACKUP_ENCRYPT:-age}"
BACKUP_KEEP_DAILY="${BACKUP_KEEP_DAILY:-14}"
BACKUP_KEEP_WEEKLY="${BACKUP_KEEP_WEEKLY:-8}"
BACKUP_KEEP_MONTHLY="${BACKUP_KEEP_MONTHLY:-12}"
BACKUP_OFFSITE="${BACKUP_OFFSITE:-1}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
trap 'fail "line $LINENO: $BASH_COMMAND"' ERR
cd "$LMS_DIR"

encrypt() { # stdin -> stdout
  case "$BACKUP_ENCRYPT" in
    age)
      [ -n "${AGE_RECIPIENTS:-}" ] || fail "AGE_RECIPIENTS is not set: no key to encrypt to"
      $AGE --encrypt -R "$AGE_RECIPIENTS"
      ;;
    gpg)
      [ -n "${GPG_RECIPIENT:-}" ] || fail "GPG_RECIPIENT is not set"
      $GPG --batch --yes --trust-model always --encrypt --recipient "$GPG_RECIPIENT"
      ;;
    *) fail "BACKUP_ENCRYPT must be age or gpg" ;;
  esac
}
suffix() { [ "$BACKUP_ENCRYPT" = gpg ] && echo gpg || echo age; }

# The backups to keep from a list of names (YYYYmmddTHHMMSSZ), newest first: the newest of each of the last
# KEEP_DAILY days, KEEP_WEEKLY ISO weeks and KEEP_MONTHLY months. Prints the names to keep.
keep_set() {
  local names daily weekly monthly
  names="$(sort -r)"
  [ -n "$names" ] || return 0
  daily="$(printf '%s\n' "$names" | awk -v n="$BACKUP_KEEP_DAILY" '{d=substr($0,1,8)} !(d in s){s[d]=1; if (c++ < n) print}')"
  weekly="$(printf '%s\n' "$names" | while read -r b; do
    printf '%s %s\n' "$(date -u -d "${b:0:4}-${b:4:2}-${b:6:2}" +%G%V)" "$b"
  done | awk -v n="$BACKUP_KEEP_WEEKLY" '!($1 in s){s[$1]=1; if (c++ < n) print $2}')"
  monthly="$(printf '%s\n' "$names" | awk -v n="$BACKUP_KEEP_MONTHLY" '{m=substr($0,1,6)} !(m in s){s[m]=1; if (c++ < n) print}')"
  printf '%s\n%s\n%s\n' "$daily" "$weekly" "$monthly" | grep -E '^[0-9]{8}T[0-9]{6}Z$' | sort -u
}

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
started="$(date +%s)"
mkdir -p "$BACKUP_DIR"
work="$BACKUP_DIR/.incomplete-$stamp"
mkdir "$work"
trap 'rm -rf "$work"' EXIT
ext="$(suffix)"

say "starting $stamp in $BACKUP_DIR (encryption: $BACKUP_ENCRYPT)"

# 1. The database, in PostgreSQL's custom format (restored with pg_restore), straight into the encryption.
say "dumping the database"
compose exec -T db sh -c 'pg_dump --format=custom --no-owner --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  | encrypt > "$work/database.dump.$ext"

# 2. The file store (course files, submissions, evidence photographs, certificates, archives), as a tar file.
say "archiving the file store"
# tar ends 1 when a file changed while it was read (an upload during the backup): that file is copied as it
# was, which is a warning, not a failure; 2 is a failure. The health check's own directory is left out.
compose exec -T api sh -c 'tar --create --file=- --exclude=./.health --directory=/srv/files .; [ $? -le 1 ]' | encrypt > "$work/files.tar.$ext"

# 3. What was backed up, so that a restore can be checked against it: the code's version, the migrations
#    applied, and the number of rows in the tables that matter and of files in the store.
say "writing the manifest"
counts="$(count_rows)"
files="$(count_files)"
commit="$(git -C "$LMS_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
cat > "$work/manifest.json" <<JSON
{"stamp": "$stamp", "commit": "$commit", "encryption": "$BACKUP_ENCRYPT", "rows": $counts, "files": $files}
JSON
(cd "$work" && sha256sum "database.dump.$ext" "files.tar.$ext" manifest.json > SHA256SUMS)
for part in "database.dump.$ext" "files.tar.$ext"; do
  [ -s "$work/$part" ] || fail "$part is empty"
done

# 4. Into the rotation only once complete.
mv "$work" "$BACKUP_DIR/$stamp"
trap - EXIT
size="$(du -sb "$BACKUP_DIR/$stamp" | cut -f1)"
say "kept $BACKUP_DIR/$stamp ($size bytes)"

# 5. Rotation on this host.
keep="$(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended -regex '.*/[0-9]{8}T[0-9]{6}Z' -printf '%f\n' | keep_set)"
[ -n "$keep" ] || fail "the rotation would keep nothing; nothing was removed"
for dir in "$BACKUP_DIR"/*T*Z; do
  name="$(basename "$dir")"
  # The backup just made is always kept, whatever the rotation says.
  if [ "$name" != "$stamp" ] && ! grep -qx "$name" <<< "$keep"; then
    say "removing $name (outside the rotation)"
    rm -rf "$dir"
  fi
done

# 6. Off site: copy the new backup, then apply the same rotation there. Never a sync: an empty or lost local
#    directory must not empty the off-site copy.
if [ -n "$RCLONE_REMOTE" ]; then
  say "copying off site to $RCLONE_REMOTE"
  $RCLONE copy --checksum "$BACKUP_DIR/$stamp" "$RCLONE_REMOTE/$stamp"
  $RCLONE check --one-way "$BACKUP_DIR/$stamp" "$RCLONE_REMOTE/$stamp"
  remote="$($RCLONE lsf --dirs-only "$RCLONE_REMOTE" | tr -d '/' | grep -E '^[0-9]{8}T[0-9]{6}Z$' || true)"
  remote_keep="$(printf '%s\n' "$remote" | keep_set)"
  [ -n "$remote_keep" ] || fail "the off-site rotation would keep nothing; nothing was removed"
  for name in $remote; do
    if [ "$name" != "$stamp" ] && ! grep -qx "$name" <<< "$remote_keep"; then
      say "removing $name off site (outside the rotation)"
      $RCLONE purge "$RCLONE_REMOTE/$name"
    fi
  done
elif [ "$BACKUP_OFFSITE" != 0 ]; then
  fail "RCLONE_REMOTE is not set: the backup is on this host only (set BACKUP_OFFSITE=0 to allow that)"
fi

# 7. For the monitoring: when the last good backup finished (alert LmsBackupMissing).
if [ -n "${BACKUP_METRICS_FILE:-}" ]; then
  tmp="$BACKUP_METRICS_FILE.$$"
  {
    echo "# HELP lms_backup_last_success_timestamp_seconds When the last complete backup finished."
    echo "# TYPE lms_backup_last_success_timestamp_seconds gauge"
    echo "lms_backup_last_success_timestamp_seconds $(date +%s)"
    echo "# HELP lms_backup_size_bytes Size of the last complete backup."
    echo "# TYPE lms_backup_size_bytes gauge"
    echo "lms_backup_size_bytes $size"
    echo "# HELP lms_backup_duration_seconds How long the last backup took."
    echo "# TYPE lms_backup_duration_seconds gauge"
    echo "lms_backup_duration_seconds $(($(date +%s) - started))"
  } > "$tmp"
  chmod 644 "$tmp"
  mv "$tmp" "$BACKUP_METRICS_FILE"
fi

say "done in $(($(date +%s) - started)) s"
