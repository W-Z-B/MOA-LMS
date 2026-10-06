FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=8

# 1 adds the development and test tools (pytest, ruff, pip-audit, pip-tools). The Compose development
# stack sets it; production images leave it at 0 and carry only what the product runs.
ARG INSTALL_DEV=0

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 libcairo2 libgdk-pixbuf-2.0-0 shared-mime-info fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Both files pin exact versions with hashes (pip-compile), so every build installs the same packages.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --require-hashes -r requirements.txt \
    && if [ "$INSTALL_DEV" = "1" ]; then pip install --require-hashes -r requirements.txt -r requirements-dev.txt; fi

COPY . .
# The API runs unprivileged. /srv/files is the document volume: creating it here with the right owner
# means a fresh named volume inherits that ownership. For a volume created before this change run:
#   docker compose exec -u root api chown -R app:app /srv/files
RUN useradd --create-home app && mkdir -p /srv/files && chown -R app:app /app /srv/files
USER app

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
