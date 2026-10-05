#!/usr/bin/env bash
# Runs the browser journeys end to end: builds the hosted image, starts it on a fresh database behind TLS,
# loads the fictional journey data, runs Playwright (desktop and phone), then removes the stack.
# Needs only Docker. The report is written to web/playwright-report/.
#
#   bash scripts/e2e.sh            run everything and clean up
#   KEEP=1 bash scripts/e2e.sh     leave the stack running afterwards, to look at a failure
set -euo pipefail
cd "$(dirname "$0")/.."

compose=(docker compose -f compose.e2e.yml)
cleanup() {
  if [ "${KEEP:-0}" != "1" ]; then "${compose[@]}" --profile test down -v --remove-orphans >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT

# Always start from nothing, so a stack kept from an earlier run cannot leave data behind.
"${compose[@]}" --profile test down -v --remove-orphans >/dev/null 2>&1 || true
"${compose[@]}" up -d --build --wait db app tls
# seed_journeys refuses to run without --fictional; the database here is created for this run and discarded.
"${compose[@]}" exec -T -u app app python manage.py seed_journeys --fictional
"${compose[@]}" --profile test run --rm playwright
