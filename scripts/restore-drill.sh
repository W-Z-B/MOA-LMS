#!/usr/bin/env bash
# The restore drill (item 7.09): restore a backup into a scratch stack beside production, check it, time it
# against the recovery time objective (8 hours), write a report, and remove the scratch stack.
#
#   scripts/restore-drill.sh                    the newest backup in BACKUP_DIR
#   scripts/restore-drill.sh remote:<stamp>     a backup from off site: the drill GSA should run each term
#
# The scratch stack is a separate Compose project (DRILL_PROJECT, default gsa-lms-drill) with its own volumes
# and no published ports, so production is never touched. It uses the same .env (the same encryption key, so
# encrypted fields read back). KEEP=1 leaves it running to look at; remove it later with
#   docker compose -p gsa-lms-drill down -v
# Reports go to BACKUP_DIR/drills/. Settings as for restore.sh; AGE_IDENTITY is needed.
set -Eeuo pipefail
umask 077

# shellcheck source=scripts/backup-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/backup-common.sh"
DRILL_PROJECT="${DRILL_PROJECT:-gsa-lms-drill}"
RTO_SECONDS="${RTO_SECONDS:-28800}"
trap 'fail "line $LINENO: $BASH_COMMAND"' ERR
cd "$LMS_DIR"

backup="${1:-}"
if [ -z "$backup" ]; then
  backup="$(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended -regex '.*/[0-9]{8}T[0-9]{6}Z' -printf '%f\n' \
    | sort | tail -n 1)"
  [ -n "$backup" ] || fail "no backup in $BACKUP_DIR"
fi

drill="$COMPOSE -p $DRILL_PROJECT"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
report_dir="$BACKUP_DIR/drills"
mkdir -p "$report_dir"
report="$report_dir/$stamp.txt"
log="$(mktemp)"

cleanup() {
  if [ "${KEEP:-0}" != 1 ]; then
    $drill down -v --remove-orphans >/dev/null 2>&1 || true
  fi
  rm -f "$log"
}
trap cleanup EXIT

say "drill $stamp: restoring $backup into the scratch stack $DRILL_PROJECT"
$drill down -v --remove-orphans >/dev/null 2>&1 || true
started="$(date +%s)"
status=passed
if ! COMPOSE="$drill" RESTORE_START_ALL=0 bash "$LMS_DIR/scripts/restore.sh" --yes "$backup" 2>&1 | tee "$log"; then
  status=FAILED
fi
seconds=$(($(date +%s) - started))
if [ "$status" = passed ] && [ "$seconds" -gt "$RTO_SECONDS" ]; then
  status="FAILED (slower than the recovery time objective)"
fi

{
  echo "GSA LMS restore drill $stamp"
  echo "Backup: $backup"
  echo "Scratch stack: $DRILL_PROJECT (removed afterwards: $([ "${KEEP:-0}" = 1 ] && echo no || echo yes))"
  printf 'Time to restore and check: %d min %d s (objective: %d h)\n' $((seconds / 60)) $((seconds % 60)) \
    $((RTO_SECONDS / 3600))
  echo "Result: $status"
  echo
  echo "Log:"
  cat "$log"
} > "$report"

say "drill $status in $((seconds / 60)) min $((seconds % 60)) s; report: $report"
[ "$status" = passed ]
