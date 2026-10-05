# Contributing to the GSA LMS

Work follows the GSA LMS Gold Standard Implementation Checklist: every change is a numbered checklist item,
built on a short branch, proven by the CI gates and reviewed in a pull request. This page says how.

## 1. Branches and pull requests

- Branch from `main`, named after the checklist item: `feature/2.07-navigation`, `fix/1.12-upload-checks`,
  `docs/0.21-threat-model`. Phase-wide work may use `feature/phase0-<topic>`.
- Commit titles start with the item number: `3.01 Question banks`.
- Open a pull request early, as a draft if it is unfinished. CI runs on every push.
- Squash-merge into `main` when every gate is green. Merging to `main` deploys to staging on Railway, so a
  merge is the owner's decision.
- A branch that builds on an unmerged one targets that branch, and is retargeted to `main` once the lower
  one merges.

## 2. Definition of done

An item is done only when all of these hold. The pull-request template repeats them.

1. Acceptance points met and shown on a phone and on a desktop.
2. Rules and permissions covered by automatic tests, including the cases that must be refused.
3. Every change it makes to marks or submissions, and every sensitive view, appears in the audit log.
4. Checked for keyboard use, screen reader labels, contrast and page weight (axe in the browser journeys;
   every screen fits a 360px phone without sideways scrolling).
5. Works, or fails clearly and safely, without signal.
6. User guide page, administrator note and interface documentation updated.
7. Reviewed, pipeline green, and running on staging with fictional data.
8. Checklist item ticked and the published plan updated. The plan is kept with the project's planning
   documents rather than in this repository.

## 3. Commands

Everything runs in containers; the host needs Git and Docker.

| Purpose | Command |
|---|---|
| Backend tests with coverage (threshold in `api/pyproject.toml`) | `docker compose run --rm api pytest -q --cov` |
| Backend lint and format | `docker compose exec api ruff check . && docker compose exec api ruff format --check .` |
| API documentation is complete | `docker compose exec api python manage.py spectacular --validate --fail-on-warn --file /dev/null` |
| Production security settings | `docker compose exec -e DJANGO_DEBUG=0 api python manage.py check --deploy --fail-level WARNING` |
| Web lint, tests with coverage, type-check and build | `docker compose exec web sh -c "npm run lint && npm run test:coverage && npm run build && npm run check:bundle"` |
| Browser journeys, accessibility and phone layout | `bash scripts/e2e.sh` (add `KEEP=1` to leave the stack up for a failure) |
| Licence gates | `node scripts/check_npm_licences.mjs` and, for Python, `docker compose run --rm -v "$PWD:/repo" -w /repo api python scripts/check_licences.py` |
| Known vulnerabilities | `docker compose exec api pip-audit --require-hashes --disable-pip -r requirements.txt -r requirements-dev.txt` |

The production security check needs a `DJANGO_SECRET_KEY` of at least 50 characters in the environment; CI
sets a placeholder.

The backend coverage floor ratchets: when a pull request raises coverage, raise `fail_under` to the new
level rounded down, until it reaches 88 ([ADR 0009](docs/adr/0009-quality-tooling.md)).

## 4. Dependencies

- **Licences ([ADR 0002](docs/adr/0002-licence-policy.md)).** Only permissive licences ship, plus named LGPL
  or MPL exceptions in `scripts/licence-policy.json`. A new exception is a reviewed change to that file with a
  reason.
- **Python.** Edit `api/requirements.in` (runtime) or `api/requirements-dev.in` (tools), then re-lock:

  ```bash
  docker compose exec api python -m piptools compile --generate-hashes --strip-extras --allow-unsafe -o requirements.txt requirements.in
  docker compose exec api python -m piptools compile --generate-hashes --strip-extras --allow-unsafe -o requirements-dev.txt requirements-dev.in
  docker compose build api
  ```

  Locking downloads every file to hash it and can take several minutes.
- **Web.** `docker compose exec web npm install --save-exact <package>@<version>` (add `--save-dev` for
  tools); commit `package.json` and `package-lock.json` together.
- An upgrade is its own pull request: re-lock, pass every gate, then rehearse on staging.

## 5. Rules that never bend

- No secrets in tracked files, issues, pull requests or chat. `.env` is ignored; `.env.example` holds
  placeholders. The secret scan runs over the whole history.
- No real personal data outside production. Development and staging use fictional data only
  (`seed_demo --fictional`, `seed_journeys --fictional`). Learner data stays in Guyana.
- Every change to marks, submissions and content goes through an audited view or service.
- No decision about a student is made by the system alone ([ADR 0007](docs/adr/0007-ai-assistance.md)).
- The LMS owns no person and no result: people come from the HRMS and the SRMS, results belong to the SRMS.
- Significant decisions are written as decision records in `docs/adr/`.

## 6. Documents to know

- Decision records: [docs/adr/README.md](docs/adr/README.md)
- Setup: [docs/SETUP.md](docs/SETUP.md); architecture: [docs/architecture.md](docs/architecture.md);
  components: [docs/components.md](docs/components.md)
- Hosted staging: [deploy/railway/README.md](deploy/railway/README.md)
