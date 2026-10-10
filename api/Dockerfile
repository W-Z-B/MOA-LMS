# FFmpeg for lecture video (items 4.06, 4.07; ADR 0015): built here from Debian's own source package, with
# LGPL components only, and run by the job worker as a separate program (ADR 0002, point 6). Debian's
# ffmpeg package is built with --enable-gpl, so it is not used. H.264 comes from OpenH264 (BSD-2-Clause);
# AAC, JPEG (the poster frame) and WAV (for captions) are FFmpeg's own LGPL encoders. Network protocols
# are left out: the converter only ever reads and writes local files.
FROM python:3.12-slim AS ffmpeg

RUN sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
       build-essential dpkg-dev nasm pkg-config libopenh264-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN apt-get update && apt-get source --download-only ffmpeg && rm -rf /var/lib/apt/lists/* \
    && dpkg-source --skip-patches -x ffmpeg_*.dsc src \
    && cd src \
    && ./configure --prefix=/opt/ffmpeg --disable-autodetect --disable-network --disable-devices \
       --disable-doc --disable-ffplay --disable-debug --enable-small --disable-shared --enable-static \
       --enable-libopenh264 \
    && make -j"$(nproc)" && make install
# The build must say it is LGPL, and must not have been configured with GPL or non-free parts.
RUN /opt/ffmpeg/bin/ffmpeg -hide_banner -L | tr '\n' ' ' | grep -q "Lesser General Public" \
    && ! /opt/ffmpeg/bin/ffmpeg -hide_banner -buildconf | grep -q -E -- "--enable-(gpl|nonfree|version3)"

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=8

# 1 adds the development and test tools (pytest, ruff, pip-audit, pip-tools). The Compose development
# stack sets it; production images leave it at 0 and carry only what the product runs.
ARG INSTALL_DEV=0

# libopenh264-8 is the H.264 encoder the FFmpeg above uses.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 libcairo2 libgdk-pixbuf-2.0-0 shared-mime-info fonts-dejavu \
    libopenh264-8 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ffmpeg /opt/ffmpeg/bin/ffmpeg /opt/ffmpeg/bin/ffprobe /usr/local/bin/

WORKDIR /app
# Both files pin exact versions with hashes (pip-compile), so every build installs the same packages.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --require-hashes -r requirements.txt \
    && if [ "$INSTALL_DEV" = "1" ]; then pip install --require-hashes -r requirements.txt -r requirements-dev.txt; fi

COPY . .
# The admin site's style sheets and scripts, gathered at build time into /app/staticfiles. The production
# stack copies them into the volume Caddy serves at /static/ (deploy/compose.prod.yml, service "static").
RUN DJANGO_SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput --verbosity 0
# The API runs unprivileged. /srv/files is the document volume, /srv/static the admin's files for Caddy and
# /tmp the uploads on their way in: creating them here with the right owner means a fresh named volume
# inherits that ownership. For a volume created before this change run:
#   docker compose exec -u root api chown -R app:app /srv/files
RUN useradd --create-home app && mkdir -p /srv/files /srv/static \
    && chown -R app:app /app /srv/files /srv/static && chmod 1777 /tmp
USER app

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
