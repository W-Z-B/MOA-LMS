# Development environment setup

Everything runs in containers. The host needs only Git and Docker Engine with the Compose plugin (Docker
Desktop on Windows or macOS is acceptable for developers; the server uses Docker Engine on Ubuntu).

## 1. Clone and configure

```bash
git clone <repository-url> gsa-lms && cd gsa-lms
cp .env.example .env
sh scripts/gen-secret.sh          # paste the two printed lines into .env
# set DB_PASSWORD to a local value; leave SMTP_* empty for development (emails print to the API log)
```

`.env` is git-ignored. Do not put real credentials in any tracked file, issue or chat.

## 2. Start the stack

```bash
docker compose up -d --build
docker compose exec api python manage.py migrate
docker compose exec api python manage.py seed           # roles and campuses
docker compose exec api python manage.py createsuperuser
```

| URL | Purpose |
|---|---|
| https://lms.localhost:8445 | Web app (Vite dev server with hot reload behind Caddy) |
| https://lms.localhost:8445/api/docs/ | OpenAPI documentation (Swagger UI) |
| https://lms.localhost:8445/api/health/ | Health check |
| https://lms.localhost:8445/admin/ | Django admin |

Caddy issues a local certificate for `lms.localhost`; trust the Caddy root CA once
(`docker compose exec caddy cat /data/caddy/pki/authorities/local/root.crt`) or accept the browser warning.
The development image includes the test and lint tools (`INSTALL_DEV=1` in `compose.yml`); production
images do not.

## 3. Daily commands

```bash
docker compose logs -f api worker              # follow logs
docker compose exec api python manage.py makemigrations
docker compose run --rm api pytest -q --cov    # backend tests and coverage (PostgreSQL required)
docker compose exec api ruff check .           # lint
docker compose exec web npm run lint           # front-end lint
docker compose exec web npm run test           # front-end component and logic tests
docker compose exec web npm run build          # type-check and production bundle
bash scripts/e2e.sh                            # browser journeys, desktop and phone, with accessibility checks
docker compose down                            # stop; add -v to drop the database
```

CONTRIBUTING.md lists every CI gate and how to run it locally.

## 4. Data

- `seed` adds the roles and the two campuses (idempotent).
- Course sites, lecturers and students come from the SRMS and names from the HRMS: join the ecosystem as the
  README describes and run `sync_ecosystem`.
- `seed_demo --fictional` adds teaching content, assignments, submissions and marks to the synced sites. Load
  the HRMS and SRMS demonstration data first.
- `seed_journeys --fictional` creates a small fictional cast with accounts (password from
  `DEMO_USER_PASSWORD`) and one taught course site, with no HRMS or SRMS. The browser journeys use it.
- None of these may run on a database that holds real records.

Accounts: today the superuser creates accounts in the Django admin and links each to its person record.
Accounts created from the synced records, with a link to choose a password, wait for decision D7
([ADR 0016](adr/0016-accounts-and-sign-on.md)). Administrators and course administrators enrol an
authenticator app at their first sign-in.

### Packaged content, the library and digital badges (items 5.10, 5.12 to 5.14, 6.08)

| Setting | Default | What it does |
|---|---|---|
| `UPLOAD_LIMIT_PACKAGE_MB` | 50 | Largest SCORM package, H5P file, cartridge or Moodle backup. Caddy refuses bodies over 60 MB: raise `request_body` in `deploy/*Caddyfile*` with it |
| `PACKAGE_MAX_ENTRIES` | 10000 | Most files a package or imported archive may hold |
| `PACKAGE_MAX_UNPACKED_MB` | 500 | Most it may unpack to (zip bombs are refused) |
| `PACKAGE_PLAY_HOURS` | 8 | How long the signed address of a package's player lasts |
| `OPEN_BADGES_ENABLED` | off | Issue each certificate also as an Open Badges 3.0 credential. Turn on only once GSA's permanent address (`PUBLIC_URL`) is settled: it is written into every credential |

The badge signing key is made by the first credential, kept encrypted with `FIELD_ENCRYPTION_KEY`, and
published at `/api/badges/issuer.json` and `/api/badges/jwks.json`. To rotate it (if it may have been exposed,
or on GSA's schedule): `python manage.py rotate_badge_key`. The old key is retired, not removed, so the
credentials it signed still verify. Rotating `FIELD_ENCRYPTION_KEY` itself means re-encrypting the stored key
as for every encrypted field; keep the old key with the backups.

The package players are files of the web build (`/players/`), copied from `scorm-again` and `h5p-standalone`
at the versions in `web/package.json` ([ADR 0012](adr/0012-new-components.md), [ADR 0030](adr/0030-packaged-content-as-built.md)).

## 5. Branching and CI

- Short branches named after the checklist item (for example `feature/2.07-navigation`).
- Open a pull request; CI runs every gate in the definition of done ([ADR 0009](adr/0009-quality-tooling.md)).
  Merge only when green and reviewed. Branch protection is a repository setting (item 0.22).
- The workflow file is GitHub Actions syntax and runs unchanged on Forgejo or Gitea Actions if GSA hosts the
  repository in-country.

## 6. Production deployment (summary)

```bash
docker compose -f compose.yml -f deploy/compose.prod.yml up -d --build
docker compose exec api python manage.py migrate
```

The production override builds the API without development tools and the web bundle from `web/Dockerfile`;
the `web` service copies the bundle into the volume Caddy serves and exits, and Caddy starts after it. Set
`DOMAIN`, `DJANGO_DEBUG=0` and `DJANGO_ALLOWED_HOSTS`, and configure `deploy/Caddyfile.prod` for a public
certificate, an internal CA or `tls internal`. Hosted staging uses the single-container image instead
([deploy/railway/README.md](../deploy/railway/README.md)).

## 7. Tooling inventory

| Tool | Role | Licence |
|---|---|---|
| Git, GitHub or Forgejo | Version control, reviews, CI | GPL-2 (Git), MIT (Forgejo) |
| Docker Engine, Compose | Reproducible environments | Apache 2.0 |
| Python 3.12, Django 5, DRF, drf-spectacular | Backend and API documentation | PSF, BSD |
| Procrastinate | PostgreSQL-backed jobs | MIT |
| PostgreSQL 16 | Database | PostgreSQL |
| Node.js 22, Vite, React, TypeScript | Front-end | MIT, Apache 2.0 |
| Caddy 2 | TLS and reverse proxy | Apache 2.0 |
| ruff, pytest, pytest-cov, pip-audit, pip-tools | Backend quality gates and locked dependencies | MIT, Apache 2.0, BSD |
| oxlint, Vitest, Testing Library, jsdom | Front-end lint and tests | MIT |
| Playwright, axe-core | Browser journeys and accessibility checks (development only) | Apache 2.0, MPL 2.0 |
| gitleaks | Secret scan in CI | MIT |

## 8. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `scripts/e2e.sh` is slow the first time | It builds the hosted image and pulls the Playwright browsers (about 2 GB). Later runs reuse both. |
| A browser journey fails | Run `KEEP=1 bash scripts/e2e.sh`, then open `web/playwright-report/index.html`; screenshots and traces are in `web/test-results/`. |
| Tests report "skipped: database tests need PostgreSQL" | You ran pytest on the host against SQLite. Run `docker compose run --rm api pytest -q`. |
| `pytest --cov` fails with "Required test coverage ... not reached" | Coverage fell below `fail_under` in `api/pyproject.toml`. Add tests; never lower the floor without a reason in the pull request. |
| `spectacular --fail-on-warn` fails | An endpoint or serializer field is not described. Add `extend_schema` to the view or a type hint to the method field. |
| A licence gate fails | A new package's licence is not on the policy. See [ADR 0002](adr/0002-licence-policy.md) before adding an exception. |
| Upload returns 500 and the API log shows `Permission denied: '/srv/files/...'` | The `files` volume was created before the image set its owner. Run `docker compose exec -u root api chown -R app:app /srv/files` once. |
| A privileged user gets 403 asking for multi-factor verification | Enrol and verify an authenticator code through the sign-in screen. |
