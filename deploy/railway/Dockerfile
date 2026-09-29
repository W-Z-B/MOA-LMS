# Single-container image for platforms that run one container per service (Railway).
# Caddy serves the built web app and the static files and proxies /api and /admin to gunicorn;
# the job worker runs beside them. The Compose stack keeps using api/Dockerfile.
# Build context is the repository root:  docker build -f deploy/railway/Dockerfile .

FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
RUN npm run build

FROM caddy:2 AS caddy

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=8

# WeasyPrint (PDF output) needs Pango and Cairo at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 shared-mime-info fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY api/requirements.txt .
RUN pip install -r requirements.txt

COPY api/ .
RUN python manage.py collectstatic --noinput

COPY --from=web /web/dist /srv/web
COPY --from=caddy /usr/bin/caddy /usr/bin/caddy
COPY deploy/railway/Caddyfile /etc/caddy/Caddyfile
COPY deploy/railway/start.sh deploy/railway/run.sh /usr/local/bin/

# The container starts as root only to hand the mounted files volume to the application user
# (start.sh); every process then runs as that user.
RUN useradd --create-home app && mkdir -p /srv/files && chown -R app:app /app /srv/files \
    && chmod +x /usr/local/bin/start.sh /usr/local/bin/run.sh

EXPOSE 8080
CMD ["/usr/local/bin/start.sh"]
