# GSA LMS

Learning Management System for the Guyana School of Agriculture (Ministry of Agriculture).
One of three systems in the GSA ecosystem, built and deployed separately and joined by service APIs:

| System | Owns | Repository |
|---|---|---|
| HRMS | Staff, positions, campuses and organisational units | `HRMS/gsa-hrms` |
| SRMS | Programmes, courses, applicants, students, offerings, enrolments, results | `SRMS/gsa-srms` |
| **LMS (this one)** | Course sites, content, assignments, submissions, coursework marks | `LMS/gsa-lms` |

The LMS owns no person and no result. Staff come from the HRMS, students and class lists from the
SRMS, and coursework totals go back to the SRMS, which adds the examination mark and publishes.

Same stack and licence policy as the HRMS: Django 5, Django REST Framework, PostgreSQL 16, React,
Caddy, Docker Compose. Only permissive licences ship, with the named LGPL and MPL exceptions of
[ADR 0002](docs/adr/0002-licence-policy.md). Setup: [docs/SETUP.md](docs/SETUP.md); how to contribute and the
quality gates: [CONTRIBUTING.md](CONTRIBUTING.md); decisions: [docs/adr](docs/adr/README.md).

**Status:** scaffold with working API and web screens. 21 backend tests pass against PostgreSQL.

## Modules

| Directory | What exists |
|---|---|
| `api/people` | Person references keyed by employee number or student number |
| `api/courses` | Course sites (from SRMS offerings or created locally, academic or staff development), memberships, modules, pages, files and links, announcements that notify students, completions; access is decided by site membership; students see published material only; files are served through authenticated, audited downloads |
| `api/assessments` | Assignments with weights, submissions (text or file, late flag, closed when late work is not allowed), marking with release control, gradebook, weighted coursework percentage |
| `api/integration` | Scoped service keys; sites and class lists pulled from the SRMS; coursework totals pushed to the SRMS; staff training completions pushed to the HRMS |
| `api/core`, `api/audit`, `api/iam`, `api/notifications` | Shared skeleton: field encryption, insert-only audit log, system roles, session login with TOTP, account lockout, notifications |
| `web/` | My courses, course site with content, assignments (submit, mark, release), gradebook and announcements |

## Setup

```bash
cp .env.example .env && sh scripts/gen-secret.sh      # paste the two lines into .env, set DB_PASSWORD
docker compose up -d --build
docker compose exec api python manage.py migrate
docker compose exec api python manage.py seed
docker compose exec api python manage.py createsuperuser
```

Open https://lms.localhost:8445.

| Command | Purpose |
|---|---|
| `docker compose run --rm api pytest -q` | Backend tests (PostgreSQL required) |
| `docker compose run --rm api ruff check .` | Lint |
| `cd web && npm run lint && npm run build` | Front-end checks |

## Joining the ecosystem

```bash
docker network create gsa-ecosystem                                   # once per host
# Keys issued in the HRMS and the SRMS for the client named "lms" go in .env:
#   HRMS_API_KEY (scopes staff:read org:read training:write)
#   SRMS_API_KEY (scopes academics:read marks:write)
docker compose -f compose.yml -f compose.ecosystem.yml up -d
docker compose exec api python manage.py sync_ecosystem                        # sites and class lists
docker compose exec api python manage.py sync_ecosystem --push-marks           # coursework to the SRMS
docker compose exec api python manage.py sync_ecosystem --push-training        # completions to the HRMS
```

The site and class-list sync also runs nightly at 02:00. A student who drops a course in the SRMS is
deactivated in the site, never deleted, so their submissions remain on record.

## Coursework rule

A marked assignment counts with its mark. An overdue assignment with no submission counts as zero.
A submitted but unmarked assignment is pending and does not count. The total is weighted by each
assignment's weight and sent to the SRMS as a percentage.

## Rules

- User accounts are linked to a person reference; sign-on across the three systems is an open
  decision recorded in the ecosystem architecture document.
- Never commit secrets. `.env` is ignored; `.env.example` holds placeholders only.
- Branching: trunk-based, `feature/<area>-<name>` branches, pull request with green CI into `main`.

## Hosted staging (Railway)

A staging and demonstration copy runs on Railway in the project "GSA Ecosystem", beside the other two
systems, with fictional data only. How it is built and configured: [deploy/railway/README.md](deploy/railway/README.md).

## Demonstration data

The LMS owns no person and no class list, so `seed_demo` first pulls sites and class lists from the SRMS
and names from the HRMS, then adds two weeks of content, an announcement, two assignments, submissions and
marks to each course site, and one staff-development site with a completion. Load the demonstration data of
the HRMS and the SRMS first. **Never run it on a database that holds real records.**

```bash
docker compose exec api python manage.py seed_demo --fictional
docker compose exec api python manage.py sync_ecosystem --push-marks --push-training
```

The second command returns the coursework totals to the SRMS and reports the completion to the HRMS. Both
are idempotent.
