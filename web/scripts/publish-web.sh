#!/bin/sh
# Entry point of the production web image (web/Dockerfile): copies the built bundle into the volume Caddy
# serves. What the volume held is removed first, so files of an earlier release do not linger.
set -eu
mkdir -p /srv/web
find /srv/web -mindepth 1 -delete
cp -r /dist/. /srv/web/
echo "Web bundle published to /srv/web."
