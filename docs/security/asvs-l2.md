# Review against OWASP ASVS Level 2

**Version 1.1, 6 October 2026,** checklist item 7.01. Prepared by the development team; reviewed at every
release gate and when the code changes in a way this review covers. Version 1.0 was the first pass; this
version checks again every row the fixes, the operations work and the merge of `main` touched (see
[What changed since version 1.0](#what-changed-since-version-10)).

## What this is

The OWASP Application Security Verification Standard (ASVS) is a published list of the security checks a
web application should pass. Level 2 is the level recommended for systems that hold personal data, such as
learners' work and marks. This review takes every Level 1 and Level 2 requirement of ASVS version 4.0.3,
chapters V1 to V14, and records whether the GSA LMS meets it today, with the evidence: the file and
function, the setting, or the test that shows it.

**Scope.** The code and configuration on branch `feature/finish-operations` (base `dd12db6`, with `main`
merged in at `57405ee`, which brought the outside tools over LTI 1.3, AI assistance, insights, help requests,
lecture video and push notices): the API (`api/**`), the web app (`web/src/**`, `web/public/sw.js`), the edge
(`deploy/Caddyfile*`), the production, monitoring and hosted stacks (`compose.yml`, `deploy/compose.prod.yml`,
`deploy/monitoring/*`, `deploy/railway/*`), the pipeline (`.github/workflows/ci.yml`) and the scripts
(`scripts/*`). Level 3 requirements are left out, as are the operating system and network of the production
host, which is not chosen yet (item 7.04).

**Method.** Each requirement was checked by reading the code that would meet it, not its description, and
by finding the test that proves it where one exists. A requirement is:

- **Met** when the code or configuration does what it asks, with evidence;
- **Partly met** when part of it is done, or it is done in one place and not another; the gap is named;
- **Not met** when nothing does it yet;
- **Not applicable** when the LMS has nothing it applies to (no SOAP, no SMS codes, for example).

Requirement wording is summarised in a few words; the standard itself has the full text. Numbers the
standard withdrew in version 4.0.3 (for example 1.4.2, 4.1.4, 7.3.2, 13.1.2, 13.2.4 and 14.3.1) are left
out, which leaves the 257 requirements counted below. Where several requirements share one answer (2.6.1 to
2.6.3, for example) they share a row and are counted one by one.

## Summary

| Status | Version 1.0 | Now |
|---|---|---|
| Met | 163 | 182 |
| Partly met | 54 | 41 |
| Not met | 15 | 11 |
| Not applicable | 25 | 23 |
| **Total (Level 1 and Level 2)** | **257** | **257** |

No finding is judged critical. The ones that matter most now are: records other than roles and
authenticators (marks among them) can be changed in the Django admin site without an entry in the chained
audit log (7.1.3, 4.3.3); the application still connects to PostgreSQL as the superuser that could switch
off the audit log's protection (1.2.1); a small Word or PowerPoint file read for AI drafting can exhaust the
API's memory (12.1.2); the API documentation page runs a script from a public CDN at "latest" (10.3.2);
and `FIELD_ENCRYPTION_KEY` cannot be changed at all (1.6.3, 6.2.4).

**Still not done, checked again on 6 October 2026:** the least-privilege database role (1.2.1), `__Host-`
cookie names (3.4.4), a virus scan of uploads (12.4.2), a list of encryption keys (`MultiFernet`) so the key
can be changed (1.6.3, 6.2.4), base images pinned by digest (1.14.2), passkeys (2.3.2), a password strength
indicator and a show-password control (2.1.8, 2.1.12), a list of leaked passwords (2.1.7), `includeSubDomains`
on HSTS (14.4.5), `Content-Disposition` on API answers (14.4.2), a pepper (2.4.5), a quota per student
(12.1.3), a check on humanly possible times (11.1.2), the missing retention rules (8.3.8), audit of staff
viewing students' work (8.3.5), and the definition of done (1.1.2, 1.1.7). Each is in the table below.

### What changed since version 1.0

Built and checked in the code on this branch:

- **Monitoring (item 7.10):** JSON logs with request ids and error groups, a request log, a metrics
  address behind `METRICS_TOKEN`, no-store on every API answer, a last-resort error answer with a reference
  (`config/observability.py`); a health check of the database, the file store and the job queue
  (`config/views.py`); Prometheus rules and Alertmanager (`deploy/monitoring/`); tests
  `config/test_observability.py`. Rows 1.7.1, 7.1.1, 7.2.2, 7.3.1, 7.4.1, 7.4.3, 8.2.1, 11.1.8, 14.5.1.
- **Backups (item 7.09):** daily backups encrypted with `age` before they touch the disk, copied off site
  with `rclone`, a restore that checks itself, and a timed drill (`scripts/backup.sh`, `restore.sh`,
  `restore-drill.sh`). Row 14.1.4.
- **Bills of materials (item 7.20):** CycloneDX files and `THIRD-PARTY-NOTICES.md` from CI (job `sbom`,
  `scripts/third_party_notices.py`). Row 14.2.5.
- **The fixes of version 1.0's list** (commit `09a175b`): authenticator codes count towards the lockout and
  are accepted once (2.2.1, 2.8.4); notices when a password or authenticator changes (2.2.3, 2.5.5); failed
  sign-ins and lockouts in the chained audit log (7.2.1); roles and authenticator resets in the Django admin
  audited (2.8.6, and part of 7.1.3 and 4.3.3); an accommodation's reason encrypted (6.1.2, 1.8.2); a
  sibling's `next` page followed only on its own host (part of 5.2.6); the notice acknowledgement's address
  from `core.net`; the field class list cleared on a time-out (part of 8.2.3); a waiting message shown as
  text (5.3.3).
- **The permission table (item 1.16)** and **the term life-cycle (item 7.12)**: rows 1.4.1, 1.4.4, 4.1.1,
  4.1.3, 4.2.1, 11.1.5, 13.1.4, 13.2.1.
- **The runbook (item 7.11):** key management written down (1.6.1).
- **From `main`:** outside tools over LTI 1.3 (OAuth 2 tokens and signed JSON Web Tokens: 3.5.1 and 3.5.3
  are now met, no longer not applicable), lecture video run through FFmpeg as a separate program, AI
  assistance through a model GSA hosts (off by default), help requests, insights and push notices. Their
  rows were checked again; the new gaps they bring are 5.2.6 and 12.6.1 (key-set addresses), 12.1.2
  (Office files read for AI drafting) and 8.2.3 (modules kept offline).

Newly found in this pass, not in version 1.0: the Django admin site's other models (to fix 1), the
Office files read whole for AI drafting (3), the documentation page's script from a CDN (4), and the
production override's ports and source mount (8).

## Not met: to fix

In order of importance. The list holds every requirement not met, and every one partly met, whose gap can be
closed in this repository's code or configuration; the file to change is named.

| # | Requirement | What is missing | Where | Suggested fix |
|---|---|---|---|---|
| 1 | 7.1.3, 4.3.3 | Only roles and authenticators are audited in the Django admin site. Marks, submissions, assignments, course sites, memberships, content, people, service clients, notifications and accounts (the Active, Staff and Superuser flags) are registered there with Django's plain admin, so a change made there leaves no entry in the chained audit log | `api/assessments/admin.py`, `api/courses/admin.py`, `api/people/admin.py`, `api/integration/admin.py`, `api/notifications/admin.py`; Django's own `User` admin | Register each with `AuditedAdmin` (`iam/admin.py`), make marks and submissions read-only there, and remove from the admin what the web app already does; audit changes to an account's flags |
| 2 | 1.2.1 | The API connects to PostgreSQL as the user the image creates, which owns the tables and is a superuser: it could switch off the audit log's trigger | `compose.yml`, `deploy/compose.prod.yml`; an init script for `db` | Run migrations as the owner and the application as a role with only SELECT, INSERT, UPDATE, DELETE, and no right to alter the audit table |
| 3 | 12.1.2 | AI drafting reads each part of a Word or PowerPoint file whole (`package.read`) before cutting it to 2 MB, so a small file that unpacks to gigabytes exhausts the memory of the API process | `api/assist/services.py` `_office_text` | Read through `package.open(name).read(2_000_000)`, and refuse a part whose declared size (`ZipInfo.file_size`) is over a limit |
| 4 | 10.3.2, 14.2.3 | The API documentation page loads Swagger UI from jsDelivr at "latest", with no integrity check, on the LMS's own origin, where a signed-in person's session works | `api/config/settings.py` `SPECTACULAR_SETTINGS`; `config/urls.py` | Serve Swagger UI from the image (`drf-spectacular-sidecar`, BSD, within the licence policy), or switch the documentation off in production |
| 5 | 7.1.2 | An extension's reason, which may describe an illness, is copied in clear into the audit entry's reason and snapshot | `api/assessments/arrangements_api.py` (the extension's `perform_create`) | Record that a reason was given, as `_kept` does for accommodations |
| 6 | 5.2.6, 12.6.1 | A tool's key-set address may be any https host a course administrator enters; the server fetches it and follows redirects, including to private addresses and plain http. The sibling client follows redirects too, and Python's `urllib` sends the `Authorization` header on to the new host | `api/lti/keys.py` `fetch_json`; `api/integration/client.py` `call` | Refuse redirects in both (a handler that raises on 3xx); refuse key-set addresses on private or loopback networks |
| 7 | 1.6.3, 6.2.4 | `FIELD_ENCRYPTION_KEY` cannot be changed: one key only, and the audit chain's key derives from it, so a new key would make every encrypted value unreadable and every earlier entry fail the chain check | `api/core/crypto.py`; `api/audit/chain.py` | Accept a list of keys (`MultiFernet`): encrypt with the newest, read with any; a management command re-encrypts in the background; record which key sealed each run of the chain so the check uses the right one |
| 8 | 1.14.1, 14.1.3 | The production override keeps the development ports (8082, 8445) and the host's `./api` mounted over the image's code in the API and the worker; nothing serves the admin site's static files | `deploy/compose.prod.yml`; `api/Dockerfile` | `ports: !override` with 80 and 443 for Caddy, `volumes: !override` for `api` and `worker`; `collectstatic` in the image and a server for `/static/` (the runbook gives the interim override) |
| 9 | 8.1.4, 11.1.7 | No alert on a rise in refusals (401, 403, 429) or failed sign-ins, on disk space, or on the backup metric going missing; the nightly copy of sites and class lists from the SRMS is not recorded as a run, so a failure raises nothing | `deploy/monitoring/alerts.yml`; `api/integration/tasks.py` `sync_srms` | Rules on `lms_http_requests_total{status="4xx"}` by route, on `node_filesystem_avail_bytes` and `absent(lms_backup_last_success_timestamp_seconds)`; record the SRMS copy with `integration.runs.Run` |
| 10 | 2.8.5, 2.5.7, 8.2.3 | The person is not told when a used authenticator code is offered again; an authenticator reset does not end the person's sessions; modules kept for offline reading stay on the phone after a time-out | `api/iam/views.py` `mfa_verify`; `api/iam/admin.py` `TotpDeviceAdmin`; `web/src/App.tsx` | Call `_tell` on a reused code; end every session on a reset (`iam/sessions.py`); call `clearOffline()` in the time-out handler, as Sign out does |
| 11 | 3.4.4 | Cookies are not named with the `__Host-` prefix | `api/config/settings.py`; `web/src/api/client.ts` `csrfToken` | When `DEBUG` is off set `SESSION_COOKIE_NAME = "__Host-sessionid"` and `CSRF_COOKIE_NAME = "__Host-csrftoken"`, and read that name in the web client |
| 12 | 14.4.2 | API answers carry no `Content-Disposition: attachment` | `api/config/observability.py` `NoStoreMiddleware` | Add `Content-Disposition: attachment; filename="api.json"` to JSON answers that set none |
| 13 | 8.3.8 | The retention schedule has no rule for messages, quiz attempts and their events, attendance records, practical evidence (photographs and locations), idempotency keys, the session list, LTI launches, used values and scores, push subscriptions or video; the forum rule still says there are no forums | `api/privacy/retention.py` `RULES` | Add a rule for each, as proposals for GSA (impact assessment, section 7), and correct the forum note |
| 14 | 8.3.5 | Downloads, one's own record and archive downloads are audited, but a member of staff opening a student's submission, quiz attempt, gradebook or accommodation in the API is not | `api/assessments/marking_api.py`, `api/quizzes/api.py`, `api/assessments/gradebook_api.py`, `api/assessments/arrangements_api.py` | Record a `viewed` entry when someone other than the student opens a submission or an attempt, and when an accommodation's reason is read |
| 15 | 12.4.2 | Uploaded files are checked by their contents but not scanned for viruses | `api/core/uploads.py` `validate_upload`; `compose.yml` | Add a virus scanner as a separate service (ClamAV runs as its own process; its licence needs a named exception under ADR 0002) and call it from `validate_upload`, refusing a file that it flags or cannot scan |
| 16 | 2.1.12, 2.1.8 | No "show password" control and no strength indicator where a password is chosen | `web/src/features/auth/SetPasswordScreen.tsx`, `LoginScreen.tsx`, `web/src/features/account/PasswordSection.tsx` | A show/hide button on each password field; a plain-words indicator of length and whether the password is on the common list |
| 17 | 2.1.7 | Passwords are checked against Django's list of 20,000 common passwords, not a list of passwords known to have leaked | `api/config/settings.py` AUTH_PASSWORD_VALIDATORS | A validator over a larger local list of leaked passwords, shipped with the image (an online check would send data abroad) |
| 18 | 1.1.2, 1.1.7 | The definition of done does not yet ask for the threat model to be updated, and there is no secure coding checklist | `CONTRIBUTING.md` | Add both lines to the definition of done; link this review and `threat-model.md` |
| 19 | 14.4.5 | HSTS is sent without `includeSubDomains` | `deploy/Caddyfile.prod`, `deploy/railway/Caddyfile`; settings `SILENCED_SYSTEM_CHECKS` | Add it once GSA's domain and its other services are known |
| 20 | 2.3.2 | Only authenticator apps; no security keys or passkeys | `api/iam/` | Add WebAuthn (passkeys) as a second kind of authenticator, after Release 1 |
| 21 | 2.4.5 | No secret "pepper" added to password hashing | `api/config/settings.py` PASSWORD_HASHERS | A custom hasher that applies an HMAC with a key held outside the database before PBKDF2; low priority |
| 22 | 11.1.2 | No check that a quiz or a form is done in a humanly possible time | `api/quizzes/services.py` | Flag (not refuse) attempts submitted faster than a set minimum, for the lecturer to see in the attempt's events |
| 23 | 1.14.2 | Base images follow tags (`python:3.12-slim`, `caddy:2`, `node:22-alpine`, `postgres:16-alpine`, `alpine:3`), and the monitoring images version tags, so a moved tag changes what is built | `api/Dockerfile`, `web/Dockerfile`, `deploy/railway/Dockerfile`, `compose.yml`, `deploy/monitoring/compose.monitoring.yml` | Pin each by digest and let a scheduled job propose updates |
| 24 | 12.1.3 | No limit on how much one student may store, beyond each hand-in's size | `api/assessments/api.py` `submit`; `api/forums/api.py` | A per-person allowance on each site, counted as the site allowance is (`courses/storage.py`) |

Accepted as designed, not listed above: sibling systems keep static, scoped, hashed keys (2.10.1, 3.5.2), as
in the HRMS; offline work and kept modules stay on the phone for their owner (8.2.2, ADR 0011); the PDF
engine and XML parsing run in the API's own process (14.2.6), with the PDF engine fetching nothing and XML
guarded, while FFmpeg runs apart; giving a role asks for nothing beyond the verified session (3.7.1).

## Remains open (needs GSA or hosting)

These cannot be closed in the code alone.

| Requirement | What is needed | From whom |
|---|---|---|
| 1.7.2, 7.3.4 | Logs sent to a separate system the application cannot change; the production clock kept by NTP (asked for in `docs/runbook.md`) | Hosting (item 7.04) |
| 1.9.1, 1.9.2, 9.2.2, 9.2.3 | Whether traffic between containers, to the HRMS and SRMS, and to an AI model if GSA switches one on, crosses a network GSA does not control; if so, TLS inside too | Hosting (item 7.04) |
| 1.14.1, 14.1.3 | Firewall and host hardening of the production server | Hosting (item 7.04) |
| 6.1.1 | Disk encryption of the production database and file volume | Hosting (item 7.04) |
| 6.4.1, 6.4.2 | A secrets store for `DJANGO_SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, the database password and `VAPID_PRIVATE_KEY`, rather than environment variables; GSA may accept environment variables for Release 1 | Hosting, GSA |
| 9.1.2, 9.2.1 | A TLS test of the production address (SSL Labs or `testssl.sh`); a public certificate, not the internal one for an isolated network | Hosting |
| 10.3.3 | DNS records kept tidy so that no sub-domain can be taken over | GSA (domain) |
| 2.5.4 | On the hosted stack, remove `DJANGO_SUPERUSER_PASSWORD` from the platform after the first sign-in (`deploy/railway/run.sh`) | Whoever deploys |
| 2.5.7 | Approval of the identity check before an authenticator is reset, now written in `docs/runbook.md` | GSA |
| 8.3.2 | Whether learners need restriction and objection in the LMS, as the HRMS has (impact assessment, section 6) | GSA |
| 1.2.2 | Whether the network between Caddy and the API is shared with anything else on the production host | Hosting (item 7.04) |
| 10.2.1 | Before AI assistance is switched on: the model and the server it runs on (decision D5, impact assessment section 7b); before a tool receives names or emails: the reason, recorded (section 7a) | GSA |
| Item 7.02 of the plan | An independent penetration test of the three systems | GSA |

## V1 Architecture, design and threat modelling

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 1.1.1 | 2 | Secure development life cycle | Met | `CONTRIBUTING.md` definition of done; CI gates in `.github/workflows/ci.yml` (lint, checks, tests with 90% coverage floor, licences, vulnerabilities, secrets, journeys); decision records in `docs/adr/` |
| 1.1.2 | 2 | Threat modelling for each design change | Partly met | `docs/security/threat-model.md`, version 1.1 of 6 October 2026, covers the outside tools, AI assistance, lecture video, push notices and the operations controls added since version 1.0; the definition of done does not yet ask for it to be updated (to fix 18) |
| 1.1.3 | 2 | Security constraints in user stories | Met | Checklist items carry their rules; refusals are tested (e.g. `courses/test_scope.py`) |
| 1.1.4 | 2 | Trust boundaries and flows documented | Met | `docs/architecture.md`; threat model section 3, including the outside tools, the AI model and the video converter |
| 1.1.5 | 2 | Architecture and connected services analysed | Met | `docs/architecture.md` integration table; threat model sections 3 and 4; `docs/lti.md`, `docs/ai.md` |
| 1.1.6 | 2 | Centralised, reusable security controls | Met | `iam/permissions.py` `RolePermission`; `courses/access.py`; `core/uploads.py`; `courses/richtext.py`; `core/net.py`; `terms/guard.py` (closed sites); `config/observability.py` (logs, errors, metrics) |
| 1.1.7 | 2 | Secure coding checklist available | Partly met | `CONTRIBUTING.md` rules on secrets; no secure coding checklist (to fix 18) |
| 1.2.1 | 2 | Low-privilege accounts for components | Partly met | API and hosted image run as `app` (`api/Dockerfile` `USER app`; `deploy/railway/start.sh` `setpriv`); the database connection uses the superuser the image creates (to fix 2); FFmpeg runs as `app` in the job worker |
| 1.2.2 | 2 | Communication between components authenticated | Partly met | Database password required (`compose.yml` `DB_PASSWORD:?`); sibling systems by scoped key (`integration/auth.py`); the metrics by token (`METRICS_TOKEN`); Caddy to API unauthenticated on the private network |
| 1.2.3 | 2 | One vetted authentication mechanism | Met | Django sessions for people; `ServiceKeyAuthentication` for sibling systems; outside tools by a signed client assertion and a short bearer token (`lti/services.py` `issue_token`, `bearer_tool`); the admin site accepts only the web sign-in (`iam/admin_site.py`) |
| 1.2.4 | 2 | All authentication pathways equally strong | Met | Admin has no password form (`LmsAdminSite.login`); test `iam/tests.py::test_admin_needs_the_verified_web_sign_in` |
| 1.4.1 | 2 | Access control at trusted enforcement points | Met | Server only: `RolePermission` on every view, scoped querysets; every route and method tried for every role, refusals included (`config/test_permission_table.py`, item 1.16) |
| 1.4.4 | 2 | Single access control mechanism | Met | `RolePermission` plus `courses/access.py` (`site_role`, `visible_sites`, `TaughtRecord`); one guard for closed sites, whatever the address (`terms/guard.py`) |
| 1.4.5 | 2 | Feature or attribute-based access control | Met | Access by site membership and role (`courses/access.py` `site_role`) |
| 1.5.1 | 2 | Input and output requirements defined | Met | Serializers per endpoint; OpenAPI schema validated in CI (`spectacular --validate --fail-on-warn`) |
| 1.5.2 | 2 | No serialisation with untrusted clients | Met | JSON only; no pickle or YAML (searched) |
| 1.5.3 | 2 | Input validation on the server | Met | DRF serializers; model constraints (e.g. latitude range in `practicals/models.py`) |
| 1.5.4 | 2 | Output encoding near the interpreter | Met | React escaping; `richtext.clean` on the server; `html.escape` in `certificates/api.py` and `certificates/pdf.py` |
| 1.6.1 | 2 | Key management policy | Met | Written in the runbook, section "Keys" (`docs/runbook.md`): every secret, where it is, who holds it and how it is changed; a sealed copy opened by two people; two holders of the backup keys, kept off the server |
| 1.6.2 | 2 | Key material protected | Met | Keys from the environment only; separate keys derived per purpose (`core/crypto.py` `chain_key`, `fingerprint`; `attendance/codes.py` `_key`); the LTI private key encrypted at rest (`lti/models.py` `PlatformKey`); the backup's private keys never on the server (`scripts/backup.sh`) |
| 1.6.3 | 2 | Keys replaceable, re-encryption planned | Partly met | Service keys (`create_service_client`) and the LTI platform key (`lti/keys.py` `make_key`) can be replaced; `FIELD_ENCRYPTION_KEY` cannot: one key only (`core/crypto.py` `_fernet`), and the audit chain's key derives from it (to fix 7; `docs/runbook.md`, "Keys") |
| 1.6.4 | 2 | No secrets on the client | Met | No key or secret reaches the web app; only the public VAPID key, as push requires |
| 1.7.1 | 2 | Common logging format | Met | One JSON object a line with the request's id, for the API and the worker (`config/observability.py` `JsonFormatter`, `RequestObservabilityMiddleware`; `settings.LOGGING`); test `config/test_observability.py::test_logs_are_one_json_object_a_line_with_extra_fields_and_the_request_id`; the audit log is uniform (`audit/models.py`) |
| 1.7.2 | 2 | Logs sent to a remote system | Not met | Remains open (hosting): logs go to standard output and Docker's files on the same server |
| 1.8.1 | 2 | Sensitive data identified and classified | Met | Threat model section 1; `docs/privacy/what-we-record.md`; impact assessment |
| 1.8.2 | 2 | Protection levels with requirements | Met | Levels stated (threat model section 1); health data encrypted (6.1.2) |
| 1.9.1 | 2 | Encrypted communication between components | Partly met | TLS at Caddy; inside the stack, to the HRMS and SRMS, and to an AI model at an `http` address, plain HTTP on a private network (`.env.example`); outside tools only over https (`lti/api.py` `_secure`); remains open (hosting) |
| 1.9.2 | 2 | Authenticity of each side verified | Partly met | As 1.9.1 |
| 1.10.1 | 2 | Source control with traceable changes | Met | Git; commits cite checklist items; secret scan over the history (`ci.yml` job `secrets`) |
| 1.11.1 | 2 | Components and their functions documented | Met | `docs/architecture.md` apps table |
| 1.11.2 | 2 | High-value flows thread-safe | Met | `quizzes/services.py` `save_answer` (`select_for_update`); advisory locks in `audit/chain.py` and `certificates/services.py`; `practicals/offline.py`; LTI nonces and token ids used once by a unique constraint (`lti/models.py` `UsedValue`) |
| 1.12.2 | 2 | Uploads served as attachments, not inline | Met | `FileResponse(..., as_attachment=True)` in every download; a lecture video plays inline only as the copies FFmpeg made, typed `video/mp4` (`video/api.py`); files never served from `MEDIA_URL` (`config/urls.py`) |
| 1.14.1 | 2 | Components segregated by network | Partly met | Only Caddy publishes ports (`compose.yml`); Prometheus and Alertmanager publish none (`deploy/monitoring/compose.monitoring.yml`); Caddy refuses `/api/metrics`; the production override still publishes the development ports (to fix 8); host firewall remains open (hosting) |
| 1.14.2 | 2 | Signed binaries, trusted deployment | Partly met | Packages locked with hashes; CI actions pinned to commits; FFmpeg built from Debian's source and checked to be LGPL (`api/Dockerfile`); images not signed, base and monitoring images by tag (to fix 23) |
| 1.14.3 | 2 | Pipeline warns of vulnerable components | Met | `pip-audit` and `npm audit` in `ci.yml` |
| 1.14.4 | 2 | Pipeline verifies a secure deployment | Met | `ci.yml` job `compose`; `check --deploy --fail-level WARNING` |
| 1.14.5 | 2 | Deployments in containers or sandboxes | Met | Docker Compose; non-root API and worker; FFmpeg a separate program built without network or devices (`api/Dockerfile`) |
| 1.14.6 | 2 | No unsupported client technology | Met | No Flash, applets or plug-ins |

## V2 Authentication

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 2.1.1 | 1 | Passwords of 12 characters or more | Met | `settings.AUTH_PASSWORD_VALIDATORS` `min_length: 12` |
| 2.1.2 | 1 | 64 characters allowed, at most 128 | Met | `max_length=128` on `PasswordSetSerializer`, `PasswordChangeSerializer` |
| 2.1.3 | 1 | No truncation | Met | PBKDF2 hashes the whole password |
| 2.1.4 | 1 | Any printable Unicode | Met | No character restrictions |
| 2.1.5 | 1 | People can change their password | Met | `iam/views.py` `change_password_view` |
| 2.1.6 | 1 | Change needs the current password | Met | Same view, `wrong_password` refusal |
| 2.1.7 | 1 | Checked against leaked passwords | Partly met | `CommonPasswordValidator` only (to fix 17) |
| 2.1.8 | 1 | Strength meter | Not met | None in `SetPasswordScreen.tsx` or `PasswordSection.tsx` (to fix 16) |
| 2.1.9 | 1 | No composition rules | Met | Length, common list, numeric-only and similarity only |
| 2.1.10 | 1 | No forced rotation or history | Met | None configured |
| 2.1.11 | 1 | Paste and password managers allowed | Met | No paste blocking; `autocomplete="new-password"` and `current-password` on account screens |
| 2.1.12 | 1 | Option to show the password | Not met | No show/hide control (to fix 16) |
| 2.2.1 | 1 | Protection against guessing | Met | Passwords: lockout by account and by address (`iam/services.py` `account_locked`, `address_blocked`; tests `iam/tests.py::test_account_locks_after_repeated_failures`, `::test_one_address_failing_across_many_accounts_is_held_back`). Authenticator codes: a wrong or reused code counts as a failed sign-in; at the limit the session ends and the account waits out the lockout (`iam/views.py` `mfa_verify`, `_too_many_codes`; test `iam/test_asvs.py::test_wrong_authenticator_codes_lock_the_account_and_end_the_session`) |
| 2.2.2 | 1 | Weak authenticators only as second factors | Met | No SMS or email codes |
| 2.2.3 | 1 | Notice after authentication details change | Met | A notice in the LMS and by email when the password is changed or set, or an authenticator set up (`iam/views.py` `_tell`; test `iam/test_asvs.py::test_setting_up_an_authenticator_and_changing_a_password_are_told_to_the_person`); an email change tells the old address (`iam/email_change.py`) |
| 2.3.1 | 1 | Initial secrets random and short-lived | Met | Invitation link, one use, 7 days (`iam/accounts.py` `LinkTokens`) |
| 2.3.2 | 2 | Security keys supported | Not met | Authenticator apps only (to fix 20) |
| 2.3.3 | 2 | Renewal instructions for time-bound authenticators | Not applicable | None issued |
| 2.4.1 | 2 | Passwords stored with a slow hash | Met | Django PBKDF2-SHA256 (Django 5.2.17) |
| 2.4.2 | 2 | Salt of at least 32 bits | Met | Django's random salt per password |
| 2.4.3 | 2 | PBKDF2 iterations high | Met | 1,000,000 iterations, Django 5.2 default |
| 2.4.4 | 2 | bcrypt work factor | Not applicable | bcrypt not used |
| 2.4.5 | 2 | Secret salt (pepper) | Not met | To fix 21 |
| 2.5.1 | 1 | Recovery secret not sent in clear | Met | A one-use link, never a password (`iam/accounts.py` `send_reset`) |
| 2.5.2 | 1 | No hints or secret questions | Met | None |
| 2.5.3 | 1 | Recovery never reveals the password | Met | Link to choose a new one |
| 2.5.4 | 1 | No shared or default accounts | Partly met | None in code; hosted first administrator from a platform variable to remove after first sign-in (`deploy/railway/run.sh`); remains open |
| 2.5.5 | 1 | Notice when a factor changes | Met | As 2.2.3 |
| 2.5.6 | 1 | Secure forgotten-password process | Met | `forgot_password_view`: same answer for every name, 60-minute one-use link, 5 asks per address and 3 links per account in 15 minutes |
| 2.5.7 | 2 | Lost factor: identity proven again | Partly met | A reset is audited as `authenticator_reset` (`iam/admin.py` `TotpDeviceAdmin`; test `iam/test_asvs.py::test_roles_and_authenticators_changed_in_the_django_admin_are_audited`); the identity check is written in `docs/runbook.md` ("Resetting someone's authenticator"); the reset does not end the person's sessions (to fix 10); GSA to approve the procedure (remains open) |
| 2.6.1 to 2.6.3 | 2 | Look-up secrets (3 requirements) | Not applicable | No recovery codes |
| 2.7.1 to 2.7.4 | 1 | Out-of-band codes (4 requirements) | Not applicable | No SMS, telephone or push codes |
| 2.7.5, 2.7.6 | 2 | Out-of-band codes (2 requirements) | Not applicable | As above |
| 2.8.1 | 1 | Time-based codes have a lifetime | Met | `pyotp` 30-second steps, one step either side (`mfa_verify`) |
| 2.8.2 | 2 | Code secrets protected | Met | `TotpDevice.secret` is an `EncryptedTextField`; left out of the admin form (`iam/admin.py`) |
| 2.8.3 | 2 | Approved algorithms for codes | Met | RFC 6238 through `pyotp` |
| 2.8.4 | 2 | A code used only once | Met | The last accepted time step is kept and a code for it or an earlier one refused (`iam/models.py` `TotpDevice.last_used_step`; `MFA_REFUSE_REUSED_CODES`, on by default); test `iam/test_asvs.py::test_an_authenticator_code_is_accepted_once` |
| 2.8.5 | 2 | Reuse logged and the person told | Partly met | A reused code is refused, audited (`mfa_failed` with `reused`) and counted towards the lockout; the person is not told (to fix 10) |
| 2.8.6 | 2 | Code generators can be revoked | Met | Device removable in the admin site, audited as `authenticator_reset` (`iam/admin.py`) |
| 2.9.1 to 2.9.3 | 2 | Cryptographic authenticators (3 requirements) | Not applicable | None used |
| 2.10.1 | 2 | Service credentials not static | Partly met | Sibling systems use static keys, scoped, hashed, rotatable, last use recorded (`integration/models.py` `ServiceClient`); outside tools hold no static secret: a signed client assertion, used once, buys a token of `LTI_TOKEN_SECONDS` (`lti/services.py` `issue_token`) |
| 2.10.2 | 2 | No default service passwords | Met | `DB_PASSWORD:?` in `compose.yml`; keys of 32 characters or more (`MIN_KEY_LENGTH`) |
| 2.10.3 | 2 | Service secrets stored protected | Met | Keys stored as SHA-256, compared in constant time (`ServiceClient.authenticate`); LTI tokens stored as SHA-256 (`lti/models.py` `AccessToken`) |
| 2.10.4 | 2 | Secrets not in source code | Met | Environment only, `VAPID_PRIVATE_KEY` and `METRICS_TOKEN` included; `.gitignore` covers `.env` and the monitoring's token and mail password files; gitleaks over the whole history (`ci.yml`) |

## V3 Session management

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 3.1.1 | 1 | No session token in URLs | Met | Session cookie only; password links carry their token after `#`, which the browser does not send; the calendar feed's address is a deliberate, revocable secret (`calendars/api.py`) |
| 3.2.1 | 1 | New token at sign-in | Met | Django `login()` cycles the key (`iam/views.py` `login_view`) |
| 3.2.2 | 1 | At least 64 bits of entropy | Met | Django session keys (32 random characters) |
| 3.2.3 | 1 | Token stored safely in the browser | Met | HttpOnly cookie; nothing in browser storage |
| 3.2.4 | 2 | Token made with a secure generator | Met | Django `get_random_string` (`secrets`) |
| 3.3.1 | 1 | Sign-out ends the session | Met | `logout_view`; `iam/sessions.py` `forget_session`; test `iam/test_sessions.py::test_signing_out_removes_the_session_from_the_list` |
| 3.3.2 | 1 | Time-outs (30 minutes idle, 12 hours at most) | Met | 30 minutes idle, 8 hours in all (`iam/middleware.py`); tests `::test_an_idle_session_ends_with_the_reason`, `::test_a_busy_session_still_ends_at_the_absolute_limit` |
| 3.3.3 | 2 | End other sessions after a password change | Met | `change_password_view` ends the others; `set_password_view` ends all |
| 3.3.4 | 2 | See and end active sessions | Met | `sessions_view`, `end_session_view`, `end_other_sessions_view`; `iam/test_sessions.py` |
| 3.4.1 | 1 | Cookie Secure | Met | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` when `DEBUG` is off |
| 3.4.2 | 1 | Cookie HttpOnly | Met | `SESSION_COOKIE_HTTPONLY = True` |
| 3.4.3 | 1 | Cookie SameSite | Met | Django default `Lax` |
| 3.4.4 | 1 | `__Host-` prefix | Not met | Default names `sessionid`, `csrftoken` (to fix 11) |
| 3.4.5 | 1 | Cookie path set | Met | The LMS has its own host; path `/` |
| 3.5.1 | 2 | Revocable OAuth grants | Met | Outside tools hold OAuth 2 tokens from the LMS (LTI Advantage); a course administrator who switches a tool off stops all its tokens at once (`lti/services.py` `bearer_tool`); people grant no OAuth access of their own |
| 3.5.2 | 2 | Sessions rather than static API secrets | Partly met | People use sessions; sibling systems static scoped keys (2.10.1); outside tools short tokens |
| 3.5.3 | 2 | Stateless tokens signed | Met | LTI messages are JSON Web Tokens signed RS256 both ways; only RS256 accepted; `exp`, `iat`, `iss` and the audience checked; nonces and `jti` used once (`lti/keys.py` `verify_from_tool`; `lti/models.py` `UsedValue`); tests `lti/tests.py::test_a_launch_cannot_be_replayed`, `::test_token_refusals` |
| 3.7.1 | 1 | Re-authentication before sensitive actions | Partly met | Current password to change password or email (`email_views.py`); authenticator code once per session; giving roles asks nothing more |

## V4 Access control

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 4.1.1 | 1 | Enforced on the server | Met | `RolePermission`; scoped querysets; every route and method tried for every role (`config/test_permission_table.py`) |
| 4.1.2 | 1 | Access attributes cannot be changed by users | Met | Roles from `RoleScope`; membership from the SRMS sync; ids checked by `TaughtRecord` |
| 4.1.3 | 1 | Least privilege | Met | Students see their own work and released marks (`site_gradebook`, `visible_submissions`); auditor read-only; a closed site read-only to all but course administrators (`terms/guard.py`; test `terms/tests.py::test_a_closed_site_is_read_only_to_its_lecturer_but_not_to_a_course_administrator`); tests `courses/test_scope.py` and the permission table (`config/test_permission_table.py`, every endpoint, method and role) |
| 4.1.5 | 1 | Fails securely | Met | Unknown or forbidden ids read as not found (`TaughtRecord`); `visible_sites` returns nothing for an account with no person; a tool asking about a course it is not placed on reads not found (`lti/services.py` `placed_site`) |
| 4.2.1 | 1 | Protection against direct object references | Met | `visible_submissions`, `visible_sites`, `taught_sites`; test `courses/test_scope.py::test_work_on_another_site_cannot_be_marked_or_opened`; the permission table checks that a list a role may use never shows a record it may not see (`config/test_permission_table.py`) |
| 4.2.2 | 1 | Protection against cross-site request forgery | Met | DRF `SessionAuthentication` enforces CSRF; `web/src/api/client.ts` sends `X-CSRFToken`; the LTI addresses tools call take a signed token or a bearer token, not a cookie |
| 4.3.1 | 1 | Administrative interfaces need a second factor | Met | `iam/admin_site.py` `has_permission`; tests `iam/tests.py::test_admin_needs_the_verified_web_sign_in`, `::test_admin_asks_staff_for_a_code_even_when_their_roles_do_not` |
| 4.3.2 | 1 | No directory listing or metadata files | Met | Caddy `file_server` without browse; `.git` not in any image (`.dockerignore`) |
| 4.3.3 | 2 | Extra checks for high-value actions | Partly met | Authenticator code for administrators, course administrators and teaching staff (`iam/services.py` `requires_mfa`); disposal needs a second person (`privacy/retention_views.py`); roles given in the admin site are audited (`iam/admin.py`) but need no second person; other records changed in the admin site are not audited (to fix 1) |

## V5 Validation, sanitisation and encoding

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 5.1.1 | 1 | Repeated parameters handled | Met | DRF parsing; serializers take one value per field |
| 5.1.2 | 1 | No mass assignment | Met | Explicit serializer fields; no `fields = "__all__"` |
| 5.1.3 | 1 | Input validated by allow-list | Met | Serializers, choice fields, `core/uploads.py` kinds |
| 5.1.4 | 1 | Structured data validated | Met | `quizzes/schemas.py` `validate_response`; database constraints |
| 5.1.5 | 1 | Redirects only to allowed places | Met | No redirect to an address a person gives; the admin login goes to `/`; LTI answers go only to an address the tool registered (`lti/services.py` `authenticate`; test `lti/tests.py::test_the_answer_goes_only_to_an_address_the_tool_registered`) |
| 5.2.1 | 1 | HTML from users sanitised | Met | `courses/richtext.py` `clean` (nh3 allow-list) for pages, forums, messages and quiz text; test `courses/test_content.py::test_page_html_is_cleaned_against_the_allow_list` |
| 5.2.2 | 1 | Unstructured data sanitised | Met | Same; plain text becomes escaped paragraphs (`text_to_html`) |
| 5.2.3 | 1 | No email header injection | Met | Django mail refuses line breaks in headers; subjects are fixed text |
| 5.2.4 | 1 | No dynamic code execution | Met | No `eval` in the API or the web app |
| 5.2.5 | 1 | No template injection | Met | No user templates; certificates built from escaped text (`certificates/pdf.py`) |
| 5.2.6 | 1 | Protection against server-side request forgery | Partly met | Sibling `next` pages followed only on the same host (`integration/client.py` `pages`; test `config/test_observability.py::test_a_sibling_systems_next_page_elsewhere_is_not_followed`); push only to known push services (`notifications/push.py` `allowed_endpoint`); the AI model only at `AI_OLLAMA_URL`; the PDF engine fetches nothing. A tool's key-set address may be any https host a course administrator enters, fetched by the server with redirects followed, and the sibling client follows redirects with its key (to fix 6) |
| 5.2.7 | 1 | Scriptable SVG refused | Met | SVG is not an accepted kind (`core/uploads.py`) |
| 5.2.8 | 1 | Markdown and similar sanitised | Met | Forum markup converted then cleaned on the server; KaTeX with `trust: false` (`web/src/features/content/maths.ts`) |
| 5.3.1 | 1 | Output encoded for its context | Met | React; `html.escape` |
| 5.3.2 | 1 | Character set preserved | Met | UTF-8 throughout |
| 5.3.3 | 1 | Protection against cross-site scripting | Met | Server-cleaned HTML placed with `dangerouslySetInnerHTML`; a waiting message shown as text (`MessagesScreen.tsx`); AI answers shown as text; LTI pages escaped, with a strict policy of their own (`lti/views.py` `_page`); CSP `script-src 'self'`, checked in journeys (`web/e2e/support.ts`) |
| 5.3.4 | 1 | Parameterised queries | Met | ORM; the two raw statements take parameters (`audit/chain.py`, `certificates/services.py`) |
| 5.3.5 | 1 | Encoding where no parameters | Met | No string-built SQL |
| 5.3.6 | 1 | No JSON injection | Met | DRF JSON renderer |
| 5.3.7 | 1 | No LDAP injection | Not applicable | No LDAP |
| 5.3.8 | 1 | No OS command injection | Met | FFmpeg, FFprobe and the captioning program run with argument lists the LMS builds, never through a shell (`video/convert.py` `run`, `video/transcribe.py`); nothing else runs a command |
| 5.3.9 | 1 | No local or remote file inclusion | Met | Files stored under random names (`core/uploads.py` `_stored`) |
| 5.3.10 | 1 | No XPath or XML injection | Met | Quiz imports refuse document types and entities (`quizzes/formats.py` `refuse_unsafe_xml`) |
| 5.4.1 | 2 | Memory-safe code | Met | Python and TypeScript |
| 5.4.2 | 2 | No format-string flaws | Met | No user text used as a format string |
| 5.4.3 | 2 | Integer limits checked | Met | Serializer and model limits; Python integers do not overflow |
| 5.5.1 | 1 | Serialised objects protected | Met | Sessions kept on the server; tokens signed |
| 5.5.2 | 1 | XML parsers restricted | Met | `refuse_unsafe_xml` before every parse |
| 5.5.3 | 1 | No untrusted deserialisation | Met | JSON only; tokens from tools decoded by PyJWT with RS256 alone (`lti/keys.py`) |
| 5.5.4 | 1 | Browsers parse JSON safely | Met | `JSON.parse` and `response.json()` |

## V6 Stored cryptography

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 6.1.1 | 2 | Regulated personal data encrypted at rest | Partly met | Secrets encrypted (authenticator secrets, certificate codes, calendar tokens, the LTI private key, push subscription keys); learners' records rely on disk encryption of the production host; remains open (hosting) |
| 6.1.2 | 2 | Health data encrypted at rest | Met | `Accommodation.reason` is an `EncryptedTextField` (`assessments/models.py`, migration `0007_accommodation_reason_encrypted`); masked in the audit log; test `iam/test_asvs.py::test_an_accommodations_reason_is_encrypted_at_rest` |
| 6.1.3 | 2 | Financial data encrypted at rest | Not applicable | None held |
| 6.2.1 | 1 | Crypto fails securely | Met | Fernet (authenticated); `decrypt` raises on a wrong key (`core/crypto.py`) |
| 6.2.2 | 2 | Proven crypto | Met | `cryptography` Fernet, HMAC-SHA256, PBKDF2; RSA 2048 (RS256) for LTI; ECDSA P-256 for push |
| 6.2.3 | 2 | Safe modes and IVs | Met | Fernet chooses a random IV and authenticates |
| 6.2.4 | 2 | Algorithms and keys replaceable | Partly met | One module (`core/crypto.py`); no `MultiFernet`, so the key cannot be changed (to fix 7) |
| 6.2.5 | 2 | No weak modes or hashes | Met | SHA-256; SHA-1 only inside TOTP as RFC 6238 requires |
| 6.2.6 | 2 | Nonces not reused | Met | Fernet |
| 6.3.1 | 2 | Secure random numbers | Met | `secrets`, `SystemRandom` (`quizzes/services.py`, `courses/groups.py`, `assessments/marking_api.py`); LTI hints and client ids (`lti/models.py`) |
| 6.3.2 | 2 | Random identifiers | Met | `uuid4` for stored names |
| 6.4.1 | 2 | Secrets management solution | Not met | Environment variables; remains open (hosting) |
| 6.4.2 | 2 | Keys kept from the application | Not met | Keys in application memory; remains open (GSA may accept for Release 1) |

## V7 Error handling and logging

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 7.1.1 | 1 | No credentials in logs | Met | Passwords never recorded; `PasswordResetRequest` keeps no typed text; `audit/services.py` `snapshot` masks encrypted fields; the request log never writes a query string, a body or the ids in an address (`config/observability.py`); the notice acknowledgement takes its address from `core.net` (`privacy/views.py`) |
| 7.1.2 | 1 | No other sensitive data in logs | Partly met | Accommodation reasons encrypted and masked; AI questions never logged (`docs/ai.md`); an extension's reason is still copied into the audit entry (`assessments/arrangements_api.py`, reason and snapshot) (to fix 5) |
| 7.1.3 | 2 | Security events logged | Partly met | Sign-ins, failures and lockouts, refused and reused codes, password changes, downloads, and roles and authenticator resets in the admin site audited; every request with its status in the request log (`config/observability.py`); other changes in the Django admin site not audited (to fix 1) |
| 7.1.4 | 2 | Events carry what an investigation needs | Met | `AuditLog`: time, actor, address (`core/net.py`), action, entity, before and after, reason; the request log adds the request's id |
| 7.2.1 | 2 | Authentication decisions logged | Met | Successful and failed sign-ins and lockouts in the chained audit log, against the account; a name that matches no account is never written (`iam/views.py` `login_view`; test `iam/test_asvs.py::test_failed_sign_ins_reach_the_chained_audit_log_without_unknown_names`) |
| 7.2.2 | 2 | Access control decisions logged | Met | Every refusal is in the request log with its status, route and account (`config/observability.py` `RequestObservabilityMiddleware`); test `config/test_observability.py::test_every_answer_carries_a_request_id_and_is_counted` |
| 7.3.1 | 2 | Log injection prevented | Met | Logs are JSON lines (`JsonFormatter`), so text a person typed cannot forge a line; the audit log stores JSON values |
| 7.3.4 | 2 | Time synchronised | Not met | Remains open (hosting); NTP asked for in `docs/runbook.md` (Install) |
| 7.4.1 | 1 | Generic error with a reference | Met | Refusals are `{code, detail}` (`core/exceptions.py`; test `config/tests.py::test_every_refusal_carries_a_code`); an unhandled error answers `{code, detail, reference}` with the request's id and nothing of the error (`config/observability.py` `server_error`); test `config/test_observability.py::test_an_unhandled_error_answers_with_a_reference_not_the_error` |
| 7.4.2 | 2 | Consistent exception handling | Met | `api_exception_handler`; services raise refusals with codes |
| 7.4.3 | 2 | Last-resort error handler | Met | `handler500` (`config/urls.py`); every unhandled error logged with its trace and counted by group (`RequestObservabilityMiddleware.process_exception`; test `config/test_observability.py::test_an_unhandled_error_is_counted_by_group`) |

## V8 Data protection

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 8.1.1 | 2 | Not cached in server components | Met | No shared cache; the service worker keeps only the shell and the modules a person chose to keep, in their own cache (`web/public/sw.js`) |
| 8.1.2 | 2 | Temporary copies protected | Met | Uploads handled by Django's temporary files, removed after the request |
| 8.1.3 | 2 | Few parameters sent | Met | Session cookie and CSRF cookie only |
| 8.1.4 | 2 | Abnormal request numbers detected | Partly met | Requests counted by route and status, with alerts on errors, slowness, the job queue, sibling runs, the audit chain and backups (`deploy/monitoring/alerts.yml`); limits for sign-in, links, certificate checks, AI (30 a minute) and help requests; no alert on a rise in refusals (to fix 9) |
| 8.2.1 | 1 | Anti-caching headers | Met | `Cache-Control: no-store` on every `/api/` answer that sets none of its own (`config/observability.py` `NoStoreMiddleware`); test `config/test_observability.py::test_api_answers_are_never_cached` |
| 8.2.2 | 1 | Browser storage holds no sensitive data | Partly met | Offline queue (`web/src/app/offlineQueue.ts`), the field copy of a class list (`fieldCopy.ts`), waiting photographs (`photoOutbox.ts`) and modules kept for reading offline (`features/media/offlineStore.ts`) are kept by design for work without signal, each tied to its owner (ADR 0011) |
| 8.2.3 | 1 | Cleared when the session ends | Partly met | The field copy is cleared on Sign out (`Shell.tsx`) and when a session times out (`web/src/App.tsx`); modules kept for offline reading are cleared on Sign out but not on a time-out, though served only to their owner (to fix 10); queued writes wait for their owner |
| 8.3.1 | 1 | Sensitive data in the body, not the address | Met | Certificate check by POST (`certificates/api.py`); no personal data in query strings |
| 8.3.2 | 1 | People can export or remove their data | Partly met | Export: `privacy/views.py` `own_record_download`; removal only by the retention schedule; restriction and objection not built (impact assessment section 6) |
| 8.3.3 | 1 | Clear notice of use | Met | Versioned notice read and acknowledged at sign-in (`acknowledge_view`; `privacy/notice_text.py`); GSA to approve the text |
| 8.3.4 | 1 | Sensitive data identified, with a policy | Met | `docs/privacy/what-we-record.md`; impact assessment |
| 8.3.5 | 2 | Access to sensitive data audited | Partly met | Downloads, own-record views, archive downloads and tools' class-list readings audited; staff opening work, attempts, gradebooks and accommodations not (to fix 14) |
| 8.3.6 | 2 | Sensitive memory cleared | Not applicable | Python manages memory; nothing can be overwritten reliably |
| 8.3.7 | 2 | Approved encryption | Met | Fernet |
| 8.3.8 | 2 | Retention and deletion | Partly met | `privacy/retention.py` `RULES` with reviewed disposal and nightly purge, now also course sites (archived) and AI-help records; no rule yet for messages, quiz attempts and their events, attendance, practical evidence, idempotency keys, the session list, LTI launches and scores, push subscriptions or video; the forum rule still says there are no forums (to fix 13) |

## V9 Communication

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 9.1.1 | 1 | TLS for all client traffic | Met | Caddy automatic HTTPS with redirect (`deploy/Caddyfile.prod`); the platform's edge on staging (`deploy/railway/Caddyfile`) |
| 9.1.2 | 1 | Strong cipher suites only | Met | Caddy defaults; to be confirmed by a test of the production address (remains open) |
| 9.1.3 | 1 | TLS 1.2 or later only | Met | Caddy defaults |
| 9.2.1 | 2 | Trusted certificates | Partly met | Let's Encrypt on a public name; the isolated-network option uses an internal certificate (Caddyfile comments); remains open (hosting) |
| 9.2.2 | 2 | TLS for every connection | Partly met | SMTP with STARTTLS (`EMAIL_USE_TLS`); push services and tools' key sets over https; database, Caddy to API, sibling systems and an AI model at an `http` address on private networks; remains open (hosting) |
| 9.2.3 | 2 | Connections to external systems authenticated | Partly met | Sibling systems by scoped key; outside tools by their RSA keys; transport authenticity depends on 9.2.2 |
| 9.2.4 | 2 | Certificate revocation checked | Met | Caddy staples revocation status where the authority offers it |

## V10 Malicious code

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 10.2.1 | 2 | No unauthorised data collection | Met | No analytics or third-party script in the app; CSP `connect-src 'self'`; `what-we-record.md`; AI off by default and only a model GSA hosts (`assist/providers.py`); a push notice carries only a title and a link, encrypted for the device (`notifications/push.py` `payload`); tools get names and emails only where allowed (`docs/lti.md`) |
| 10.2.2 | 2 | No unnecessary device permissions | Met | Camera, microphone and location asked only on a tap (`practicals/FieldWidgets.tsx` `LocationButton`, `marking/FeedbackFiles.tsx`); `Permissions-Policy` limits them to the LMS |
| 10.3.1 | 1 | Updates over a secure, trusted channel | Met | The service worker updates from the same HTTPS origin |
| 10.3.2 | 1 | Integrity of code (no untrusted CDN) | Partly met | No CDN in the app; CSP `script-src 'self'`. The API documentation page (`/api/docs/`, signed-in people only in production) loads Swagger UI from jsDelivr at "latest", with no integrity check (drf-spectacular's default) (to fix 4) |
| 10.3.3 | 1 | No sub-domain takeover | Not applicable | No domain yet; remains open (GSA) |

## V11 Business logic

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 11.1.1 | 1 | Steps in order | Met | Authenticator code before access; notice before use; a marked submission cannot be replaced (`assessments/api.py` `submit`) |
| 11.1.2 | 1 | Realistic human time | Partly met | Attempt events record timing (`quizzes/models.py` `AttemptEvent`); no minimum time (to fix 22) |
| 11.1.3 | 1 | Limits on business actions | Met | One check-in per class (`attendance/api.py`); attempt limits (`quizzes/services.py`); link and certificate-check limits |
| 11.1.4 | 1 | Anti-automation | Met | `UserRateThrottle` 600 a minute; certificate checks 30 a minute (`CheckThrottle`); calendar feed limits; AI 30 a minute (`assist/api.py` `AiThrottle`); help requests `HELP_REQUESTS_PER_HOUR` |
| 11.1.5 | 1 | Limits matching business risks | Met | Server time decides lateness; work cannot be replaced after the due date or once marked; marks released only by teaching staff; locked once the SRMS accepts them; closed sites refuse changes (`terms/guard.py`) |
| 11.1.6 | 2 | No race conditions | Met | `select_for_update` on attempts; idempotency keys (`practicals/offline.py`); advisory locks |
| 11.1.7 | 2 | Unusual activity monitored | Partly met | Alerts on errors, a new error group, failed jobs, sibling runs, the audit chain and backups (`deploy/monitoring/alerts.yml`); a broken chain and a recorded breach alert the administrators in the LMS; no alert on unusual activity such as a rise in refusals or failed sign-ins (to fix 9) |
| 11.1.8 | 2 | Configurable alerting | Met | Rules in `deploy/monitoring/alerts.yml`, sent by severity through `alertmanager.yml`; each names its section of `docs/runbook.md` |

## V12 Files and resources

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 12.1.1 | 1 | No very large files | Met | Caddy refuses bodies over 60 MB, and over 1100 MB at the video address only; 50, 20 and 15 MB per kind (`settings.UPLOAD_LIMIT_*`) and 1024 MB a video (`UPLOAD_LIMIT_VIDEO_MB`); site allowance (`courses/storage.py`) |
| 12.1.2 | 2 | Archives checked before unpacking | Partly met | Quiz packages: member count and unpacked size (`quizzes/formats.py` `_zip_documents`); Office files only listed at upload (`core/uploads.py` `MAX_ZIP_ENTRIES`). AI drafting reads a Word or PowerPoint part whole before cutting it to 2 MB (`assist/services.py` `_office_text`), so a small file that unpacks to gigabytes fills the memory (to fix 3) |
| 12.1.3 | 2 | Quota per person | Partly met | Per-site allowance; 10 photographs per request (`practicals/uploads.py`); no quota per student (to fix 24) |
| 12.2.1 | 2 | Type checked by contents | Met | `core/uploads.py` `sniff`; tests `core/test_uploads.py`; a video's container header checked (`video/api.py` `looks_like_video`), then FFprobe must find a picture in it (`video/convert.py` `probe`) |
| 12.3.1 | 1 | File names not used for paths | Met | Random stored names; `original_name` drops folders (test `::test_the_original_name_never_carries_a_folder`) |
| 12.3.2 | 1 | File names cannot disclose files | Met | As 12.3.1 |
| 12.3.3 | 1 | File names cannot fetch remote files | Met | As 12.3.1 |
| 12.3.4 | 1 | Protection against reflected downloads | Met | Downloads are attachments named by Django's encoder |
| 12.3.5 | 1 | File metadata never reaches the operating system | Met | No shell calls |
| 12.3.6 | 2 | Uploaded files never run | Met | Never included or executed; the PDF engine fetches nothing; videos are read only by FFmpeg built without network or devices (`api/Dockerfile`), with a time-out |
| 12.4.1 | 1 | Stored outside the web root, limited permissions | Met | `/srv/files` volume, owned by `app`, reached only through authenticated downloads |
| 12.4.2 | 1 | Virus scan | Not met | To fix 15 |
| 12.5.1 | 1 | Only intended files served | Met | Caddy serves the built app and static files only |
| 12.5.2 | 1 | Uploads never run as HTML or script | Met | Attachments with `nosniff`; video copies played as `video/mp4` |
| 12.6.1 | 1 | Outbound requests by allow-list | Partly met | As 5.2.6 (to fix 6) |

## V13 API and web service

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 13.1.1 | 1 | Same parsers and encodings throughout | Met | One DRF API, JSON |
| 13.1.3 | 1 | No secrets in API addresses | Met | Keys in the `Authorization` header; the calendar feed address is a deliberate, revocable secret, encrypted at rest and rate-limited; an LTI login hint in a tool's address is single-use and expires in `LTI_LAUNCH_SECONDS` |
| 13.1.4 | 2 | Authorisation at address and record | Met | `RolePermission` and scoped querysets; the permission table (`config/test_permission_table.py`) |
| 13.1.5 | 2 | Unexpected content types refused | Met | DRF parsers answer 415; the LTI services accept their own media types only (`lti/views.py` `LineItemParser`, `ScoreParser`) |
| 13.2.1 | 1 | Only valid HTTP methods | Met | Viewsets expose only their actions; every plain view declares its methods (test `config/test_permission_table.py::test_every_plain_view_declares_its_methods`) |
| 13.2.2 | 1 | JSON validated | Met | Serializers; OpenAPI schema checked in CI |
| 13.2.3 | 1 | Cookie-based API protected from CSRF | Met | As 4.2.2 |
| 13.2.5 | 2 | Content-Type checked | Met | As 13.1.5 |
| 13.2.6 | 2 | Headers and payload trustworthy | Met | TLS; idempotency fingerprints (`practicals/offline.py`) |
| 13.3.1 | 1 | SOAP schema validation | Not applicable | No SOAP |
| 13.3.2 | 2 | SOAP message security | Not applicable | No SOAP |
| 13.4.1, 13.4.2 | 2 | GraphQL (2 requirements) | Not applicable | No GraphQL |

## V14 Configuration

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 14.1.1 | 2 | Repeatable build and deployment | Met | Dockerfiles, Compose, CI job `compose` |
| 14.1.2 | 2 | Compiler hardening flags | Not applicable | No compiled code of our own |
| 14.1.3 | 2 | Server configuration hardened | Partly met | `check --deploy` in CI; Caddy defaults; the production override still publishes the development ports and mounts the source (to fix 8); host hardening remains open (hosting) |
| 14.1.4 | 2 | Redeploy or restore from a runbook | Met | Encrypted backup, restore with checks, and a timed drill (`scripts/backup.sh`, `restore.sh`, `restore-drill.sh`; the drill passed in 1 min 40 s on a test stack); install, upgrade, restore and keys in `docs/runbook.md` |
| 14.2.1 | 1 | Components up to date | Met | `pip-audit`, `npm audit` in CI; locked versions |
| 14.2.2 | 1 | Unneeded features removed | Met | Production images carry no test tools (CI check); API documentation for signed-in people only (`DocsPermission`) |
| 14.2.3 | 1 | Integrity of external assets | Partly met | The app loads nothing from outside; the API documentation page does (as 10.3.2, to fix 4) |
| 14.2.4 | 2 | Components from trusted sources | Met | PyPI with hashes; npm lockfile; licence gates (`scripts/check_licences.py`, `check_npm_licences.mjs`) |
| 14.2.5 | 2 | Inventory of components | Met | CycloneDX bills of materials for what ships, Python and web, on every run and attached to each release (`ci.yml` job `sbom`), with `THIRD-PARTY-NOTICES.md` (`scripts/third_party_notices.py`), FFmpeg and OpenH264 named; lockfiles list every package. The images' system packages are not listed |
| 14.2.6 | 2 | Third-party libraries contained | Partly met | FFmpeg runs as a separate program with a time-out (`video/convert.py`); the PDF engine and the XML parsing run in the API's own process |
| 14.3.2 | 1 | Debug off in production | Met | `DEBUG` defaults to off; `check --deploy` in CI |
| 14.3.3 | 1 | No version numbers in headers | Met | No `X-Powered-By`; the `Server` header names Caddy without a version |
| 14.4.1 | 1 | Content-Type with character set | Met | JSON and `text/html; charset=utf-8` |
| 14.4.2 | 1 | API answers as attachments | Not met | Answers carry `Cache-Control: no-store` but no `Content-Disposition: attachment` (to fix 12) |
| 14.4.3 | 1 | Content-Security-Policy | Met | `deploy/Caddyfile.prod`, `deploy/railway/Caddyfile`; violations fail the journeys (`web/e2e/support.ts`); the certificate page sets its own |
| 14.4.4 | 1 | `X-Content-Type-Options: nosniff` | Met | Caddy and `SECURE_CONTENT_TYPE_NOSNIFF` |
| 14.4.5 | 1 | Strict-Transport-Security | Partly met | One year, without `includeSubDomains` (to fix 19) |
| 14.4.6 | 1 | Referrer-Policy | Met | `strict-origin-when-cross-origin`; `no-referrer` on the certificate page |
| 14.4.7 | 1 | No framing by other sites | Met | `frame-ancestors 'none'`; `X-Frame-Options: DENY` |
| 14.5.1 | 1 | Only used methods; others logged | Met | Viewsets expose only their actions; every 405 is in the request log with its route and account (`config/observability.py`) |
| 14.5.2 | 1 | Origin header not used for access control | Met | Used only by the CSRF check |
| 14.5.3 | 1 | CORS by strict allow-list | Met | `CORS_ALLOWED_ORIGINS` from the configured HTTPS hosts |
| 14.5.4 | 2 | Proxy headers trusted only from the proxy | Met | `X-Real-IP` set by Caddy (`core/net.py`); the API is not published (`compose.yml`) and listens on 127.0.0.1 when hosted (`deploy/railway/run.sh`); test `iam/tests.py::test_a_forged_forwarded_for_header_does_not_reach_the_records` |

## Next review

At Gate 1 and before go-live (item 7.01 is closed when no high or critical finding is open). Owner: the
Technical Lead, with GSA's IT Officer. The independent penetration test (item 7.02) checks this review.
