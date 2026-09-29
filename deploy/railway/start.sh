#!/usr/bin/env bash
# Entry point of the single-container image. Platform volumes are mounted owned by root, so this
# runs as root only long enough to give the files volume to the application user.
set -euo pipefail

FILES_ROOT="${FILES_ROOT:-/srv/files}"

if [ "$(id -u)" = "0" ]; then
  mkdir -p "$FILES_ROOT"
  chown -R app:app "$FILES_ROOT"
  export HOME=/home/app
  exec setpriv --reuid app --regid app --init-groups /usr/local/bin/run.sh
fi
exec /usr/local/bin/run.sh
