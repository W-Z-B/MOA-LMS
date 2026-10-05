# ADR 0009: Test tooling, quality gates and locked dependencies

**Status:** proposed. Implemented by the pull request for checklist item 0.20; merging it accepts this
decision. Same tools and gates as HRMS ADR 0009.
**Date:** 5 October 2026.

## Context

Gold standard is a set of measures with proof (the Implementation Checklist, section 1): 88 percent of
backend lines under test, main journeys tested end to end on desktop and phone, nothing merged unless the
pipeline passes. On 5 October 2026 the LMS had 23 backend tests and no web tests; nothing checked
accessibility, the phone layout, licences, known vulnerabilities or committed secrets; dependencies were
unpinned version ranges; and the API documentation check reported 52 errors (13 unique) while CI still
passed. The HRMS had already closed the same gaps in its pull request 15.

## Decision

**Tools added (all development or CI only; none ships in the product):**

| Tool | Licence | Use |
|---|---|---|
| Vitest, @vitest/coverage-v8, jsdom | MIT | Web component and logic tests with coverage thresholds |
| Testing Library (react, dom, jest-dom, user-event) | MIT | Tests that act as a user would |
| Playwright (@playwright/test and its container image) | Apache-2.0 | Browser journeys on desktop and a 360px phone |
| @axe-core/playwright, axe-core | MPL-2.0 | WCAG 2.2 AA checks on every journey screen |
| pytest-cov | MIT | Backend coverage threshold |
| pip-audit | Apache-2.0 | Known vulnerabilities in the locked Python packages |
| pip-tools | BSD-3-Clause | Locks Python dependencies with hashes |
| gitleaks (container image in CI) | MIT | Secrets in the whole git history |

**Gates (CI, `.github/workflows/ci.yml`):** ruff lint and format; Django checks including
`check --deploy`; complete OpenAPI documentation (`spectacular --validate --fail-on-warn`); backend tests
with a coverage floor; web lint, type-check, tests with coverage thresholds and a production build; a
page-weight budget for the application shell (160 KB compressed); licence gates for Python and the web,
each after its own tests; pip-audit and npm audit; browser journeys with accessibility and reflow checks;
gitleaks; every production image built, the web bundle included, and checked to carry no test tools.

**Coverage floor:** `fail_under` in `api/pyproject.toml` starts at 82, the level measured on 5 October 2026
(82.21 percent of lines and branches), so the gate is green on the day it is switched on. It ratchets: each
pull request that adds tests raises it to the new level rounded down, until it reaches the gold standard's
88 (item 7.05). It is never lowered without a reason in the pull request.

**Journey data:** the LMS's demonstration data needs the HRMS and the SRMS. The journeys run the LMS on its
own, so `seed_journeys --fictional` creates a small fictional cast with accounts and teaches one course site
with the demonstration material.

**Locked dependencies:** `api/requirements.in` lists what the product needs and `api/requirements-dev.in`
the tools; `requirements.txt` and `requirements-dev.txt` pin the whole tree with hashes, and images install
with `--require-hashes`. Production images leave the tools out (`INSTALL_DEV=0`). `web/package-lock.json`
pins the web tree. GitHub Actions are pinned to commits. An upgrade is a pull request that re-locks and
passes every gate, then is rehearsed on staging.

## Consequences

- Every change, including an upgrade, is proven by the same gates before it merges.
- A pull request takes longer in CI (about ten minutes, mostly the browser journeys).
- The gates bind only when branch protection requires them (decision D11, item 0.22).
- Base images (Python, Node, Caddy, PostgreSQL) still follow version tags so that security patches arrive.
  Pinning them by digest needs automated update pull requests, a repository setting for the owner.
