# ADR 0001: Technology stack and licence policy

**Status:** accepted for Release 1, as the GSA ecosystem's common stack (HRMS ADR 0001, 25 September 2026).
**Amended by:** [ADR 0002](0002-licence-policy.md) (licence policy, 5 October 2026).
**Date:** 5 October 2026, recording the stack the scaffold was built on.

## Context

The LMS is one of three GSA systems (HRMS, SRMS, LMS), each built and deployed on its own and joined by
service APIs (the GSA Ecosystem Architecture document, kept with the project's planning documents). The HRMS chose its stack first, from the Technology Stack
Definition: one product with no additional software licences, running the same on a GSA server or a cloud
VM, keeping personal data in Guyana, and maintainable by a small team. The SRMS and the LMS were scaffolded
on the same stack so that one team can work on all three and a fix to the shared skeleton (core, iam, audit,
notifications) can be applied to each.

## Decision

- Backend: Python 3.12, Django 5, Django REST Framework, drf-spectacular. Jobs: Procrastinate on PostgreSQL.
- Database: PostgreSQL 16. No separate cache, broker or search service.
- Front-end: React 19, TypeScript, Vite; delivered as an installable web app, phone first
  ([ADR 0011](0011-phone-delivery.md)).
- Edge and packaging: Caddy 2, Docker Engine, Docker Compose, Ubuntu Server LTS in production. A
  single-container image (`deploy/railway/Dockerfile`) serves hosted staging.
- Integration: the HRMS and the SRMS are reached over their integration APIs with scoped, hashed service
  keys. The LMS never reads another system's database.
- Licence policy: only MIT, BSD, Apache 2.0, PostgreSQL or PSF licensed components in the shipped product.
  AGPL and source-available components are excluded from the product. Amended by ADR 0002.

## Consequences

- One database to back up and secure; the same operations for GSA IT as the HRMS and the SRMS.
- Adopting Moodle (PHP, GPL) would leave this stack; that choice is recorded in
  [ADR 0004](0004-build-path.md).
- Every new dependency is checked against the licence policy, in code review and by the licence gates in CI.
