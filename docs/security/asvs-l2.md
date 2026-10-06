# Review against OWASP ASVS Level 2

**Version 1.0, 6 October 2026,** checklist item 7.01. Prepared by the development team; reviewed at every
release gate and when the code changes in a way this review covers.

## What this is

The OWASP Application Security Verification Standard (ASVS) is a published list of the security checks a
web application should pass. Level 2 is the level recommended for systems that hold personal data, such as
learners' work and marks. This review takes every Level 1 and Level 2 requirement of ASVS version 4.0.3,
chapters V1 to V14, and records whether the GSA LMS meets it today, with the evidence: the file and
function, the setting, or the test that shows it.

**Scope.** The code and configuration on branch `feature/finish-operations` (base `dd12db6`): the API
(`api/**`), the web app (`web/src/**`, `web/public/sw.js`), the edge (`deploy/Caddyfile*`), the production
and hosted stacks (`compose.yml`, `deploy/compose.prod.yml`, `deploy/railway/*`), the pipeline
(`.github/workflows/ci.yml`) and the scripts (`scripts/*`). Level 3 requirements are left out, as are the
operating system and network of the production host, which is not chosen yet (item 7.04).

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

| Status | Count |
|---|---|
| Met | 163 |
| Partly met | 54 |
| Not met | 15 |
| Not applicable | 25 |
| **Total (Level 1 and Level 2)** | **257** |

Of the 54 partly met, 11 are being built now in this branch's operations work (structured logs and a
metrics address, item 7.10; backup and restore scripts, item 7.09; a software bill of materials, item 7.20)
and are marked "being built". None of those files existed when this review was finished: `api/config/` has
no observability module, `settings.LOGGING` is the plain console handler, `/api/health/` checks only the
database, `scripts/` has no backup, restore or drill script, `deploy/monitoring/` does not exist, and the
pipeline makes no bill of materials. They are counted as partly met until they are merged.

No finding is judged critical. The ones that matter most are the authenticator code that can be guessed
without limit and reused within its minute (2.2.1, 2.8.4), roles given in the admin site without an entry
in the chained audit log (7.1.3, 4.3.3), API answers that browsers may keep (8.2.1), and a reason that may
describe a disability kept unencrypted (6.1.2).

## Not met: to fix

In order of importance. The list holds every requirement not met, and every one partly met, whose gap can be
closed in this repository's code or configuration; the file to change is named.

| # | Requirement | What is missing | Where | Suggested fix |
|---|---|---|---|---|
| 1 | 2.2.1, 2.8.4, 2.8.5 | The authenticator code has no limit of its own: only the general 600 requests a minute, so a person who has the password can try every code within the 8-hour session. A code can also be used again within its 90 seconds | `api/iam/views.py` `mfa_verify`; `api/iam/models.py` `TotpDevice` | Count refused codes per account (as `account_locked` does for passwords): after 5 in 15 minutes, end the session and refuse codes for the window. Keep the last accepted time step on `TotpDevice` and refuse a code for that step or an earlier one; audit and tell the person when a used code is offered again |
| 2 | 4.3.3, 7.1.3, 7.2.2, 2.5.7, 2.8.6 | Roles are given and taken only in the Django admin site, and removing someone's authenticator is done there too. Neither is written to the chained audit log, and there is no second person or reason | `api/iam/admin.py`, `api/iam/sessions.py` `roles_changed` | Record `role_given`, `role_taken` and `authenticator_reset` with the actor, the before and after and a reason (override `save_model` and `delete_model`, or port the HRMS accounts screen). Make an authenticator reset an audited action that ends every session and tells the person |
| 3 | 8.2.1 | API answers carry no `Cache-Control`, so a shared computer's browser may keep marks or submissions after sign-out | `api/config/settings.py` MIDDLEWARE; a new middleware in `api/core/` | Add `Cache-Control: no-store` to every `/api/` response that has not set its own (the calendar feed keeps `private, max-age=900`). Add `Content-Disposition: attachment` to JSON answers at the same time (14.4.2) |
| 4 | 6.1.2, 7.1.2 | An accommodation's reason, which may describe a disability (health data), is stored unencrypted; an extension's reason is copied in clear into the audit log's reason column | `api/assessments/models.py` `Accommodation.reason`, `Extension.reason`; `api/assessments/arrangements_api.py` line 101 | Make `Accommodation.reason` an `EncryptedTextField` (with a data migration). Do not copy an extension's reason into the audit entry: record that one was given, as `_kept` does for accommodations |
| 5 | 7.1.1, audit integrity | The privacy notice acknowledgement records the address from `X-Forwarded-For`, which the client writes; a forged or malformed value is stored or fails | `api/privacy/views.py` `_client_ip` | Remove `_client_ip` and use `core.net.client_ip`, as every other record does |
| 6 | 5.2.6, 12.6.1 | The SRMS and HRMS client follows the `next` address a sibling system returns, sending the LMS's service key to whatever host it names | `api/integration/client.py` `pages` | Follow `next` only when it starts with `base_url` (or rebuild it from its path and query); refuse otherwise |
| 7 | 8.2.3 | When the server ends a session (idle or time limit) the phone keeps the lecturer's field copy of a class list; it is cleared only by pressing Sign out | `web/src/App.tsx` `SIGNED_OUT_EVENT` handler | Call `clearFieldCopies()` in that handler too |
| 8 | 5.3.3 | A message waiting to send is shown with `dangerouslySetInnerHTML` before the server has cleaned it. Production's Content-Security-Policy stops scripts, but the development stack has none | `web/src/features/messages/MessagesScreen.tsx` line 275 | Show the waiting text as plain text (or through the forum markup converter that the composer uses) |
| 9 | 1.2.1 | The API connects to PostgreSQL as the user the image creates, which owns the tables and is a superuser: it could switch off the audit log's trigger | `compose.yml`, `deploy/compose.prod.yml`; an init script for `db` | Run migrations as the owner and the application as a role with only SELECT, INSERT, UPDATE, DELETE, and no right to alter the audit table |
| 10 | 2.2.3, 2.5.5 | No email when a password is changed or chosen through a link, or when an authenticator is added | `api/iam/views.py` `change_password_view`, `set_password_view`, `mfa_verify` | Send a short notice to the account's address ("your password was changed; if it was not you, tell the course administrator"), as the email change already does |
| 11 | 3.4.4 | Cookies are not named with the `__Host-` prefix | `api/config/settings.py`; `web/src/api/client.ts` `csrfToken` | When `DEBUG` is off set `SESSION_COOKIE_NAME = "__Host-sessionid"` and `CSRF_COOKIE_NAME = "__Host-csrftoken"`, and read that name in the web client |
| 12 | 7.4.1, 7.4.3 | An unexpected error answers Django's plain "Server Error (500)": no `{code, detail}` and no reference to quote to support | `api/core/exceptions.py`; `api/config/urls.py` `handler500` | Answer `{"code": "server_error", "detail": ..., "reference": <id>}` and log the error with that id (planned with error tracking, item 7.10) |
| 13 | 8.3.8 | The retention schedule has no rule for messages, quiz attempts and their events, attendance records, practical evidence (photographs and locations), certificate checks, idempotency keys or the session list; the forum rule still says there are no forums | `api/privacy/retention.py` `RULES` | Add a rule for each, as proposals for GSA (see the impact assessment, section 7), and correct the forum note |
| 14 | 8.3.5 | Downloads and one's own record are audited, but a member of staff opening a student's submission, quiz attempt, gradebook or accommodation in the API is not | `api/assessments/marking_api.py`, `api/quizzes/api.py`, `api/assessments/gradebook_api.py`, `api/assessments/arrangements_api.py` | Record a `viewed` entry when someone other than the student opens a submission or an attempt, and when an accommodation's reason is read (principle 9 of the feature audit) |
| 15 | 12.4.2 | Uploaded files are checked by their contents but not scanned for viruses | `api/core/uploads.py` `validate_upload`; `compose.yml` | Add a virus scanner as a separate service (ClamAV runs as its own process; its licence needs a named exception under ADR 0002) and call it from `validate_upload`, refusing a file that it flags or cannot scan |
| 16 | 2.1.12, 2.1.8 | No "show password" control and no strength indicator where a password is chosen | `web/src/features/auth/SetPasswordScreen.tsx`, `LoginScreen.tsx`, `web/src/features/account/PasswordSection.tsx` | A show/hide button on each password field; a plain-words indicator of length and whether the password is on the common list |
| 17 | 2.1.7 | Passwords are checked against Django's list of 20,000 common passwords, not a list of passwords known to have leaked | `api/config/settings.py` AUTH_PASSWORD_VALIDATORS | A validator over a larger local list of leaked passwords, shipped with the image (an online check would send data abroad) |
| 18 | 1.1.2, 1.1.7 | The definition of done does not yet ask for the threat model to be updated, and there is no secure coding checklist | `CONTRIBUTING.md` | Add both lines to the definition of done; link this review and `threat-model.md` |
| 19 | 14.4.5 | HSTS is sent without `includeSubDomains` | `deploy/Caddyfile.prod`, `deploy/railway/Caddyfile`; settings `SILENCED_SYSTEM_CHECKS` | Add it once GSA's domain and its other services are known |
| 20 | 2.3.2 | Only authenticator apps; no security keys or passkeys | `api/iam/` | Add WebAuthn (passkeys) as a second kind of authenticator, after Release 1 |
| 21 | 2.4.5 | No secret "pepper" added to password hashing | `api/config/settings.py` PASSWORD_HASHERS | A custom hasher that applies an HMAC with a key held outside the database before PBKDF2; low priority |
| 22 | 11.1.2 | No check that a quiz or a form is done in a humanly possible time | `api/quizzes/services.py` | Flag (not refuse) attempts submitted faster than a set minimum, for the lecturer to see in the attempt's events |
| 23 | 7.2.1 | Failed sign-ins and lockouts are kept only in `LoginAttempt`, which is removed after 12 months, not in the chained audit log | `api/iam/views.py` `login_view` | Audit `login_failed` (username typed, address) and `locked_out`; keep `LoginAttempt` for the lockout arithmetic only |
| 24 | 1.6.3, 6.2.4 | Changing `FIELD_ENCRYPTION_KEY` means re-encrypting everything at once; every key derives from it | `api/core/crypto.py` | Accept a list of keys (`MultiFernet`): encrypt with the newest, read with any; a management command re-encrypts in the background; keep old chain keys for verifying earlier audit entries |
| 25 | 1.14.2 | Base images follow tags (`python:3.12-slim`, `caddy:2`, `node:22-alpine`, `postgres:16-alpine`), so a moved tag changes what is built | `api/Dockerfile`, `web/Dockerfile`, `deploy/railway/Dockerfile`, `compose.yml` | Pin each by digest and let a scheduled job propose updates |
| 26 | 12.1.3 | No limit on how much one student may store, beyond each hand-in's size | `api/assessments/api.py` `submit`; `api/forums/api.py` | A per-person allowance on each site, counted as the site allowance is (`courses/storage.py`) |

Accepted as designed, not listed above: sibling systems keep static, scoped, hashed keys (2.10.1, 3.5.2), as
in the HRMS; offline work is kept on the phone for its owner (8.2.2, ADR 0011); third-party libraries run
in the API's own process (14.2.6), with the PDF engine fetching nothing and XML guarded.

## Remains open (needs GSA or hosting)

These cannot be closed in the code alone.

| Requirement | What is needed | From whom |
|---|---|---|
| 1.7.2, 7.3.4 | Logs sent to a separate system the application cannot change; the production clock kept by NTP | Hosting (item 7.04), runbook (item 7.11) |
| 1.9.1, 1.9.2, 9.2.2, 9.2.3 | Whether traffic between containers and to the HRMS and SRMS crosses a network GSA does not control; if so, TLS inside too | Hosting (item 7.04) |
| 1.14.1, 14.1.3 | Firewall and host hardening of the production server | Hosting (item 7.04) |
| 6.1.1 | Disk encryption of the production database and file volume | Hosting (item 7.04) |
| 6.4.1, 6.4.2 | A secrets store for `DJANGO_SECRET_KEY`, `FIELD_ENCRYPTION_KEY` and the database password, rather than environment variables; GSA may accept environment variables for Release 1 | Hosting, GSA |
| 9.1.2, 9.2.1 | A TLS test of the production address (SSL Labs or `testssl.sh`); a public certificate, not the internal one for an isolated network | Hosting |
| 10.3.3 | DNS records kept tidy so that no sub-domain can be taken over | GSA (domain) |
| 2.5.4 | On the hosted stack, remove `DJANGO_SUPERUSER_PASSWORD` from the platform after the first sign-in (`deploy/railway/run.sh`) | Whoever deploys |
| 2.5.7 | A written procedure for proving who someone is before their authenticator is reset | GSA, runbook (item 7.11) |
| 8.3.2 | Whether learners need restriction and objection in the LMS, as the HRMS has (impact assessment, section 6) | GSA |
| 1.2.2 | Whether the network between Caddy and the API is shared with anything else on the production host | Hosting (item 7.04) |
| Item 7.02 of the plan | An independent penetration test of the three systems | GSA |

## V1 Architecture, design and threat modelling

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 1.1.1 | 2 | Secure development life cycle | Met | `CONTRIBUTING.md` definition of done; CI gates in `.github/workflows/ci.yml` (lint, checks, tests with 90% coverage floor, licences, vulnerabilities, secrets, journeys); decision records in `docs/adr/` |
| 1.1.2 | 2 | Threat modelling for each design change | Partly met | `docs/security/threat-model.md` written 6 October 2026 for item 0.21; not yet in the definition of done |
| 1.1.3 | 2 | Security constraints in user stories | Met | Checklist items carry their rules; refusals are tested (e.g. `courses/test_scope.py`) |
| 1.1.4 | 2 | Trust boundaries and flows documented | Met | `docs/architecture.md`; threat model section 3 |
| 1.1.5 | 2 | Architecture and connected services analysed | Met | `docs/architecture.md` integration table; threat model |
| 1.1.6 | 2 | Centralised, reusable security controls | Met | `iam/permissions.py` `RolePermission`; `courses/access.py`; `core/uploads.py`; `courses/richtext.py`; `core/net.py` |
| 1.1.7 | 2 | Secure coding checklist available | Partly met | `CONTRIBUTING.md` rules on secrets; no secure coding checklist |
| 1.2.1 | 2 | Low-privilege accounts for components | Partly met | API and hosted image run as `app` (`api/Dockerfile` `USER app`; `deploy/railway/start.sh` `setpriv`); the database connection uses the superuser the image creates |
| 1.2.2 | 2 | Communication between components authenticated | Partly met | Database password required (`compose.yml` `DB_PASSWORD:?`); sibling systems by scoped key (`integration/auth.py`); Caddy to API unauthenticated on the private network |
| 1.2.3 | 2 | One vetted authentication mechanism | Met | Django sessions for people, `ServiceKeyAuthentication` for systems; the admin site accepts only the web sign-in (`iam/admin_site.py`) |
| 1.2.4 | 2 | All authentication pathways equally strong | Met | Admin has no password form (`LmsAdminSite.login`); test `iam/tests.py::test_admin_needs_the_verified_web_sign_in` |
| 1.4.1 | 2 | Access control at trusted enforcement points | Met | Server only: `RolePermission` on every view, scoped querysets |
| 1.4.4 | 2 | Single access control mechanism | Met | `RolePermission` plus `courses/access.py` (`site_role`, `visible_sites`, `TaughtRecord`) |
| 1.4.5 | 2 | Feature or attribute-based access control | Met | Access by site membership and role (`courses/access.py` `site_role`) |
| 1.5.1 | 2 | Input and output requirements defined | Met | Serializers per endpoint; OpenAPI schema validated in CI (`spectacular --validate --fail-on-warn`) |
| 1.5.2 | 2 | No serialisation with untrusted clients | Met | JSON only; no pickle or YAML (searched) |
| 1.5.3 | 2 | Input validation on the server | Met | DRF serializers; model constraints (e.g. latitude range in `practicals/models.py`) |
| 1.5.4 | 2 | Output encoding near the interpreter | Met | React escaping; `richtext.clean` on the server; `html.escape` in `certificates/api.py` and `certificates/pdf.py` |
| 1.6.1 | 2 | Key management policy | Partly met | Described in `core/crypto.py` and `docs/SETUP.md`; no written policy (runbook, item 7.11) |
| 1.6.2 | 2 | Key material protected | Met | Keys from the environment only; separate keys derived per purpose (`core/crypto.py` `chain_key`, `fingerprint`; `attendance/codes.py` `_key`) |
| 1.6.3 | 2 | Keys replaceable, re-encryption planned | Partly met | Rotation is a manual re-encryption; every key derives from `FIELD_ENCRYPTION_KEY` |
| 1.6.4 | 2 | No secrets on the client | Met | No key or secret reaches the web app |
| 1.7.1 | 2 | Common logging format | Partly met | Being built in item 7.10: the audit log is uniform (`audit/models.py`); platform logs are plain text (`settings.LOGGING`) |
| 1.7.2 | 2 | Logs sent to a remote system | Not met | Remains open (hosting); log shipping not set up |
| 1.8.1 | 2 | Sensitive data identified and classified | Met | Threat model section 1; `docs/privacy/what-we-record.md`; impact assessment |
| 1.8.2 | 2 | Protection levels with requirements | Partly met | Levels stated; an accommodation's reason is not encrypted (6.1.2) |
| 1.9.1 | 2 | Encrypted communication between components | Partly met | TLS at Caddy; inside the stack and to the HRMS and SRMS plain HTTP on a private network (`.env.example`); remains open (hosting) |
| 1.9.2 | 2 | Authenticity of each side verified | Partly met | As 1.9.1 |
| 1.10.1 | 2 | Source control with traceable changes | Met | Git; commits cite checklist items; secret scan over the history (`ci.yml` job `secrets`) |
| 1.11.1 | 2 | Components and their functions documented | Met | `docs/architecture.md` apps table |
| 1.11.2 | 2 | High-value flows thread-safe | Met | `quizzes/services.py` `save_answer` (`select_for_update`); advisory locks in `audit/chain.py` and `certificates/services.py`; `practicals/offline.py` |
| 1.12.2 | 2 | Uploads served as attachments, not inline | Met | `FileResponse(..., as_attachment=True)` in every download; files never served from `MEDIA_URL` (`config/urls.py`) |
| 1.14.1 | 2 | Components segregated by network | Partly met | Only Caddy publishes ports (`compose.yml`); host firewall remains open (hosting) |
| 1.14.2 | 2 | Signed binaries, trusted deployment | Partly met | Packages locked with hashes; CI actions pinned to commits; images not signed, base images by tag |
| 1.14.3 | 2 | Pipeline warns of vulnerable components | Met | `pip-audit` and `npm audit` in `ci.yml` |
| 1.14.4 | 2 | Pipeline verifies a secure deployment | Met | `ci.yml` job `compose`; `check --deploy --fail-level WARNING` |
| 1.14.5 | 2 | Deployments in containers or sandboxes | Met | Docker Compose; non-root API and worker |
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
| 2.2.1 | 1 | Protection against guessing | Partly met | Passwords: lockout by account and by address (`iam/services.py` `account_locked`, `address_blocked`; tests `iam/tests.py::test_account_locks_after_repeated_failures`, `::test_one_address_failing_across_many_accounts_is_held_back`); authenticator code unlimited (to fix 1) |
| 2.2.2 | 1 | Weak authenticators only as second factors | Met | No SMS or email codes |
| 2.2.3 | 1 | Notice after authentication details change | Partly met | Email change notifies the old address (`iam/email_change.py`); password and authenticator changes do not (to fix 10) |
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
| 2.5.5 | 1 | Notice when a factor changes | Partly met | As 2.2.3 |
| 2.5.6 | 1 | Secure forgotten-password process | Met | `forgot_password_view`: same answer for every name, 60-minute one-use link, 5 asks per address and 3 links per account in 15 minutes |
| 2.5.7 | 2 | Lost factor: identity proven again | Not met | Reset only by deleting the device in the admin site, unaudited (to fix 2; procedure remains open) |
| 2.6.1 to 2.6.3 | 2 | Look-up secrets (3 requirements) | Not applicable | No recovery codes |
| 2.7.1 to 2.7.4 | 1 | Out-of-band codes (4 requirements) | Not applicable | No SMS, telephone or push codes |
| 2.7.5, 2.7.6 | 2 | Out-of-band codes (2 requirements) | Not applicable | As above |
| 2.8.1 | 1 | Time-based codes have a lifetime | Met | `pyotp` 30-second steps, one step either side (`mfa_verify`) |
| 2.8.2 | 2 | Code secrets protected | Met | `TotpDevice.secret` is an `EncryptedTextField`; left out of the admin form (`iam/admin.py`) |
| 2.8.3 | 2 | Approved algorithms for codes | Met | RFC 6238 through `pyotp` |
| 2.8.4 | 2 | A code used only once | Not met | No record of the last step used (to fix 1) |
| 2.8.5 | 2 | Reuse logged and the person told | Not met | To fix 1 |
| 2.8.6 | 2 | Code generators can be revoked | Partly met | Device removable in the admin site; not audited (to fix 2) |
| 2.9.1 to 2.9.3 | 2 | Cryptographic authenticators (3 requirements) | Not applicable | None used |
| 2.10.1 | 2 | Service credentials not static | Partly met | Sibling systems use static keys, scoped, hashed, rotatable, last use recorded (`integration/models.py` `ServiceClient`) |
| 2.10.2 | 2 | No default service passwords | Met | `DB_PASSWORD:?` in `compose.yml`; keys of 32 characters or more (`MIN_KEY_LENGTH`) |
| 2.10.3 | 2 | Service secrets stored protected | Met | Keys stored as SHA-256, compared in constant time (`ServiceClient.authenticate`) |
| 2.10.4 | 2 | Secrets not in source code | Met | Environment only; `.gitignore`; gitleaks over the whole history (`ci.yml`) |

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
| 3.5.1 | 2 | Revocable OAuth grants | Not applicable | No OAuth |
| 3.5.2 | 2 | Sessions rather than static API secrets | Partly met | People use sessions; sibling systems static scoped keys (2.10.1) |
| 3.5.3 | 2 | Stateless tokens signed | Not applicable | None used |
| 3.7.1 | 1 | Re-authentication before sensitive actions | Partly met | Current password to change password or email (`email_views.py`); authenticator code once per session; giving roles asks nothing more |

## V4 Access control

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 4.1.1 | 1 | Enforced on the server | Met | `RolePermission`; scoped querysets |
| 4.1.2 | 1 | Access attributes cannot be changed by users | Met | Roles from `RoleScope`; membership from the SRMS sync; ids checked by `TaughtRecord` |
| 4.1.3 | 1 | Least privilege | Met | Students see their own work and released marks (`site_gradebook`, `visible_submissions`); auditor read-only; tests `courses/test_scope.py`; a permission-table test is being added (`config/test_permission_table.py`) |
| 4.1.5 | 1 | Fails securely | Met | Unknown or forbidden ids read as not found (`TaughtRecord`); `visible_sites` returns nothing for an account with no person |
| 4.2.1 | 1 | Protection against direct object references | Met | `visible_submissions`, `visible_sites`, `taught_sites`; test `courses/test_scope.py::test_work_on_another_site_cannot_be_marked_or_opened` |
| 4.2.2 | 1 | Protection against cross-site request forgery | Met | DRF `SessionAuthentication` enforces CSRF; `web/src/api/client.ts` sends `X-CSRFToken` |
| 4.3.1 | 1 | Administrative interfaces need a second factor | Met | `iam/admin_site.py` `has_permission`; tests `iam/tests.py::test_admin_needs_the_verified_web_sign_in`, `::test_admin_asks_staff_for_a_code_even_when_their_roles_do_not` |
| 4.3.2 | 1 | No directory listing or metadata files | Met | Caddy `file_server` without browse; `.git` not in any image (`.dockerignore`) |
| 4.3.3 | 2 | Extra checks for high-value actions | Partly met | Authenticator code for administrators, course administrators and teaching staff (`iam/services.py` `requires_mfa`); disposal needs a second person (`privacy/retention_views.py`); roles given in the admin site need no second person and are not audited (to fix 2) |

## V5 Validation, sanitisation and encoding

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 5.1.1 | 1 | Repeated parameters handled | Met | DRF parsing; serializers take one value per field |
| 5.1.2 | 1 | No mass assignment | Met | Explicit serializer fields; no `fields = "__all__"` |
| 5.1.3 | 1 | Input validated by allow-list | Met | Serializers, choice fields, `core/uploads.py` kinds |
| 5.1.4 | 1 | Structured data validated | Met | `quizzes/schemas.py` `validate_response`; database constraints |
| 5.1.5 | 1 | Redirects only to allowed places | Met | No redirect to a given address; the admin login goes to `/` |
| 5.2.1 | 1 | HTML from users sanitised | Met | `courses/richtext.py` `clean` (nh3 allow-list) for pages, forums, messages and quiz text; test `courses/test_content.py::test_page_html_is_cleaned_against_the_allow_list` |
| 5.2.2 | 1 | Unstructured data sanitised | Met | Same; plain text becomes escaped paragraphs (`text_to_html`) |
| 5.2.3 | 1 | No email header injection | Met | Django mail refuses line breaks in headers; subjects are fixed text |
| 5.2.4 | 1 | No dynamic code execution | Met | No `eval` in the API or the web app |
| 5.2.5 | 1 | No template injection | Met | No user templates; certificates built from escaped text (`certificates/pdf.py`) |
| 5.2.6 | 1 | Protection against server-side request forgery | Partly met | Outbound calls only to configured HRMS and SRMS addresses (`integration/client.py`); the PDF engine fetches nothing (`certificates/pdf.py` `_refuse`); `pages` follows any `next` address (to fix 6) |
| 5.2.7 | 1 | Scriptable SVG refused | Met | SVG is not an accepted kind (`core/uploads.py`) |
| 5.2.8 | 1 | Markdown and similar sanitised | Met | Forum markup converted then cleaned on the server; KaTeX with `trust: false` (`web/src/features/content/maths.ts`) |
| 5.3.1 | 1 | Output encoded for its context | Met | React; `html.escape` |
| 5.3.2 | 1 | Character set preserved | Met | UTF-8 throughout |
| 5.3.3 | 1 | Protection against cross-site scripting | Partly met | Server-cleaned HTML placed with `dangerouslySetInnerHTML`; CSP `script-src 'self'`, checked in journeys (`web/e2e/support.ts`); a waiting message is shown before cleaning (to fix 8) |
| 5.3.4 | 1 | Parameterised queries | Met | ORM; the two raw statements take parameters (`audit/chain.py`, `certificates/services.py`) |
| 5.3.5 | 1 | Encoding where no parameters | Met | No string-built SQL |
| 5.3.6 | 1 | No JSON injection | Met | DRF JSON renderer |
| 5.3.7 | 1 | No LDAP injection | Not applicable | No LDAP |
| 5.3.8 | 1 | No OS command injection | Met | No `subprocess` or `os.system` in the API |
| 5.3.9 | 1 | No local or remote file inclusion | Met | Files stored under random names (`core/uploads.py` `_stored`) |
| 5.3.10 | 1 | No XPath or XML injection | Met | Quiz imports refuse document types and entities (`quizzes/formats.py` `refuse_unsafe_xml`) |
| 5.4.1 | 2 | Memory-safe code | Met | Python and TypeScript |
| 5.4.2 | 2 | No format-string flaws | Met | No user text used as a format string |
| 5.4.3 | 2 | Integer limits checked | Met | Serializer and model limits; Python integers do not overflow |
| 5.5.1 | 1 | Serialised objects protected | Met | Sessions kept on the server; tokens signed |
| 5.5.2 | 1 | XML parsers restricted | Met | `refuse_unsafe_xml` before every parse |
| 5.5.3 | 1 | No untrusted deserialisation | Met | JSON only |
| 5.5.4 | 1 | Browsers parse JSON safely | Met | `JSON.parse` and `response.json()` |

## V6 Stored cryptography

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 6.1.1 | 2 | Regulated personal data encrypted at rest | Partly met | Secrets encrypted (authenticator secrets, certificate codes, calendar tokens); learners' records rely on disk encryption of the production host; remains open (hosting) |
| 6.1.2 | 2 | Health data encrypted at rest | Partly met | `Accommodation.reason` unencrypted; masked in the audit log (`arrangements_api.py` `_kept`) (to fix 4) |
| 6.1.3 | 2 | Financial data encrypted at rest | Not applicable | None held |
| 6.2.1 | 1 | Crypto fails securely | Met | Fernet (authenticated); `decrypt` raises on a wrong key (`core/crypto.py`) |
| 6.2.2 | 2 | Proven crypto | Met | `cryptography` Fernet, HMAC-SHA256, PBKDF2 |
| 6.2.3 | 2 | Safe modes and IVs | Met | Fernet chooses a random IV and authenticates |
| 6.2.4 | 2 | Algorithms and keys replaceable | Partly met | One module (`core/crypto.py`); rotation manual, no `MultiFernet` |
| 6.2.5 | 2 | No weak modes or hashes | Met | SHA-256; SHA-1 only inside TOTP as RFC 6238 requires |
| 6.2.6 | 2 | Nonces not reused | Met | Fernet |
| 6.3.1 | 2 | Secure random numbers | Met | `secrets`, `SystemRandom` (`quizzes/services.py`, `courses/groups.py`, `assessments/marking_api.py`) |
| 6.3.2 | 2 | Random identifiers | Met | `uuid4` for stored names |
| 6.4.1 | 2 | Secrets management solution | Not met | Environment variables; remains open (hosting) |
| 6.4.2 | 2 | Keys kept from the application | Not met | Keys in application memory; remains open (GSA may accept for Release 1) |

## V7 Error handling and logging

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 7.1.1 | 1 | No credentials in logs | Met | Passwords never recorded; `PasswordResetRequest` keeps no typed text; `audit/services.py` `snapshot` masks encrypted fields. The forgeable address in the notice acknowledgement is to fix 5 |
| 7.1.2 | 1 | No other sensitive data in logs | Partly met | Accommodation reasons masked; extension reasons copied into the audit reason (to fix 4) |
| 7.1.3 | 2 | Security events logged | Partly met | Sign-in, sign-out, refused codes, password changes, downloads audited; failed sign-ins in `LoginAttempt`; role changes in the admin and refusals not logged (to fix 2; request logging being built in item 7.10) |
| 7.1.4 | 2 | Events carry what an investigation needs | Met | `AuditLog`: time, actor, address (`core/net.py`), action, entity, before and after, reason |
| 7.2.1 | 2 | Authentication decisions logged | Partly met | Successful sign-ins audited; failures and lockouts only in `LoginAttempt`, removed after 12 months |
| 7.2.2 | 2 | Access control decisions logged | Partly met | Being built in item 7.10 (request logs with status); refusals are not recorded today |
| 7.3.1 | 2 | Log injection prevented | Partly met | Being built in item 7.10 (structured logs); the audit log stores JSON values |
| 7.3.4 | 2 | Time synchronised | Not met | Remains open (hosting, item 7.11) |
| 7.4.1 | 1 | Generic error with a reference | Partly met | Being built in item 7.10: refusals are `{code, detail}` (`core/exceptions.py`; test `config/tests.py::test_every_refusal_carries_a_code`); a crash gives Django's plain 500 with no reference (to fix 12) |
| 7.4.2 | 2 | Consistent exception handling | Met | `api_exception_handler`; services raise refusals with codes |
| 7.4.3 | 2 | Last-resort error handler | Partly met | Being built in item 7.10; as 7.4.1 |

## V8 Data protection

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 8.1.1 | 2 | Not cached in server components | Met | No shared cache; the service worker never stores `/api/` (`web/public/sw.js`) |
| 8.1.2 | 2 | Temporary copies protected | Met | Uploads handled by Django's temporary files, removed after the request |
| 8.1.3 | 2 | Few parameters sent | Met | Session cookie and CSRF cookie only |
| 8.1.4 | 2 | Abnormal request numbers detected | Partly met | Being built in item 7.10 (alerts); limits for sign-in, links and certificate checks today |
| 8.2.1 | 1 | Anti-caching headers | Not met | Only the certificate page sends `no-store` (to fix 3) |
| 8.2.2 | 1 | Browser storage holds no sensitive data | Partly met | Offline queue (`web/src/app/offlineQueue.ts`), the field copy of a class list (`fieldCopy.ts`) and waiting photographs (`photoOutbox.ts`) are kept by design for work without signal, each tied to its owner (ADR 0011) |
| 8.2.3 | 1 | Cleared when the session ends | Partly met | Field copy cleared on Sign out (`Shell.tsx`), not on time-out (to fix 7); queued writes wait for their owner |
| 8.3.1 | 1 | Sensitive data in the body, not the address | Met | Certificate check by POST (`certificates/api.py`); no personal data in query strings |
| 8.3.2 | 1 | People can export or remove their data | Partly met | Export: `privacy/views.py` `own_record_download`; removal only by the retention schedule; restriction and objection not built (impact assessment section 6) |
| 8.3.3 | 1 | Clear notice of use | Met | Versioned notice read and acknowledged at sign-in (`acknowledge_view`; `privacy/notice_text.py`); GSA to approve the text |
| 8.3.4 | 1 | Sensitive data identified, with a policy | Met | `docs/privacy/what-we-record.md`; impact assessment |
| 8.3.5 | 2 | Access to sensitive data audited | Partly met | Downloads and own-record views audited; staff opening work, attempts, gradebooks and accommodations not (to fix 14) |
| 8.3.6 | 2 | Sensitive memory cleared | Not applicable | Python manages memory; nothing can be overwritten reliably |
| 8.3.7 | 2 | Approved encryption | Met | Fernet |
| 8.3.8 | 2 | Retention and deletion | Partly met | `privacy/retention.py` `RULES` with reviewed disposal and nightly purge; rules missing for several records (to fix 13) |

## V9 Communication

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 9.1.1 | 1 | TLS for all client traffic | Met | Caddy automatic HTTPS with redirect (`deploy/Caddyfile.prod`); the platform's edge on staging (`deploy/railway/Caddyfile`) |
| 9.1.2 | 1 | Strong cipher suites only | Met | Caddy defaults; to be confirmed by a test of the production address (remains open) |
| 9.1.3 | 1 | TLS 1.2 or later only | Met | Caddy defaults |
| 9.2.1 | 2 | Trusted certificates | Partly met | Let's Encrypt on a public name; the isolated-network option uses an internal certificate (Caddyfile comments); remains open (hosting) |
| 9.2.2 | 2 | TLS for every connection | Partly met | SMTP with STARTTLS (`EMAIL_USE_TLS`); database, Caddy to API and sibling systems on plain HTTP inside private networks; remains open (hosting) |
| 9.2.3 | 2 | Connections to external systems authenticated | Partly met | Sibling systems by scoped key; transport authenticity depends on 9.2.2 |
| 9.2.4 | 2 | Certificate revocation checked | Met | Caddy staples revocation status where the authority offers it |

## V10 Malicious code

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 10.2.1 | 2 | No unauthorised data collection | Met | No analytics or third-party script; CSP `connect-src 'self'`; `what-we-record.md` |
| 10.2.2 | 2 | No unnecessary device permissions | Met | Camera, microphone and location asked only on a tap (`practicals/FieldWidgets.tsx` `LocationButton`, `marking/FeedbackFiles.tsx`); `Permissions-Policy` limits them to the LMS |
| 10.3.1 | 1 | Updates over a secure, trusted channel | Met | The service worker updates from the same HTTPS origin |
| 10.3.2 | 1 | Integrity of code (no untrusted CDN) | Met | No CDN; CSP `script-src 'self'` |
| 10.3.3 | 1 | No sub-domain takeover | Not applicable | No domain yet; remains open (GSA) |

## V11 Business logic

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 11.1.1 | 1 | Steps in order | Met | Authenticator code before access; notice before use; a marked submission cannot be replaced (`assessments/api.py` `submit`) |
| 11.1.2 | 1 | Realistic human time | Partly met | Attempt events record timing (`quizzes/models.py` `AttemptEvent`); no minimum time (to fix 22) |
| 11.1.3 | 1 | Limits on business actions | Met | One check-in per class (`attendance/api.py`); attempt limits (`quizzes/services.py`); link and certificate-check limits |
| 11.1.4 | 1 | Anti-automation | Met | `UserRateThrottle` 600 a minute; certificate checks 30 a minute (`CheckThrottle`); calendar feed limits |
| 11.1.5 | 1 | Limits matching business risks | Met | Server time decides lateness; work cannot be replaced after the due date or once marked; marks released only by teaching staff; locked once the SRMS accepts them |
| 11.1.6 | 2 | No race conditions | Met | `select_for_update` on attempts; idempotency keys (`practicals/offline.py`); advisory locks |
| 11.1.7 | 2 | Unusual activity monitored | Partly met | Being built in item 7.10; today a broken audit chain and a recorded breach alert the administrators |
| 11.1.8 | 2 | Configurable alerting | Partly met | Being built in item 7.10 (`deploy/monitoring/` alert rules) |

## V12 Files and resources

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 12.1.1 | 1 | No very large files | Met | Caddy refuses bodies over 60 MB; 50, 20 and 15 MB per kind (`settings.UPLOAD_LIMIT_*`); site allowance (`courses/storage.py`) |
| 12.1.2 | 2 | Archives checked before unpacking | Met | Quiz packages: member count and unpacked size (`quizzes/formats.py` `_zip_documents`); Office files are never unpacked, only listed (`core/uploads.py` `MAX_ZIP_ENTRIES`) |
| 12.1.3 | 2 | Quota per person | Partly met | Per-site allowance; 10 photographs per request (`practicals/uploads.py`); no quota per student |
| 12.2.1 | 2 | Type checked by contents | Met | `core/uploads.py` `sniff`; tests `core/test_uploads.py` |
| 12.3.1 | 1 | File names not used for paths | Met | Random stored names; `original_name` drops folders (test `::test_the_original_name_never_carries_a_folder`) |
| 12.3.2 | 1 | File names cannot disclose files | Met | As 12.3.1 |
| 12.3.3 | 1 | File names cannot fetch remote files | Met | As 12.3.1 |
| 12.3.4 | 1 | Protection against reflected downloads | Met | Downloads are attachments named by Django's encoder |
| 12.3.5 | 1 | File metadata never reaches the operating system | Met | No shell calls |
| 12.3.6 | 2 | Uploaded files never run | Met | Never included or executed; the PDF engine fetches nothing |
| 12.4.1 | 1 | Stored outside the web root, limited permissions | Met | `/srv/files` volume, owned by `app`, reached only through authenticated downloads |
| 12.4.2 | 1 | Virus scan | Not met | To fix 15 |
| 12.5.1 | 1 | Only intended files served | Met | Caddy serves the built app and static files only |
| 12.5.2 | 1 | Uploads never run as HTML or script | Met | Attachments with `nosniff` |
| 12.6.1 | 1 | Outbound requests by allow-list | Partly met | As 5.2.6 (to fix 6) |

## V13 API and web service

| Req | Lvl | Requirement (summary) | Status | Evidence |
|---|---|---|---|---|
| 13.1.1 | 1 | Same parsers and encodings throughout | Met | One DRF API, JSON |
| 13.1.3 | 1 | No secrets in API addresses | Met | Keys in the `Authorization` header; the calendar feed address is a deliberate, revocable secret, encrypted at rest and rate-limited |
| 13.1.4 | 2 | Authorisation at address and record | Met | `RolePermission` and scoped querysets |
| 13.1.5 | 2 | Unexpected content types refused | Met | DRF parsers answer 415 |
| 13.2.1 | 1 | Only valid HTTP methods | Met | Viewsets expose only their actions |
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
| 14.1.3 | 2 | Server configuration hardened | Partly met | `check --deploy` in CI; Caddy defaults; host hardening remains open (hosting) |
| 14.1.4 | 2 | Redeploy or restore from a runbook | Partly met | Being built in item 7.09 (backup, restore and drill scripts) and item 7.11 (runbook) |
| 14.2.1 | 1 | Components up to date | Met | `pip-audit`, `npm audit` in CI; locked versions |
| 14.2.2 | 1 | Unneeded features removed | Met | Production images carry no test tools (CI check); API documentation for signed-in people only (`DocsPermission`) |
| 14.2.3 | 1 | Integrity of external assets | Met | No external assets |
| 14.2.4 | 2 | Components from trusted sources | Met | PyPI with hashes; npm lockfile; licence gates (`scripts/check_licences.py`, `check_npm_licences.mjs`) |
| 14.2.5 | 2 | Inventory of components | Partly met | Being built in item 7.20 (bill of materials in CI); lockfiles list every package |
| 14.2.6 | 2 | Third-party libraries contained | Partly met | PDF engine with no fetching; XML guarded; not in separate processes |
| 14.3.2 | 1 | Debug off in production | Met | `DEBUG` defaults to off; `check --deploy` in CI |
| 14.3.3 | 1 | No version numbers in headers | Met | No `X-Powered-By`; the `Server` header names Caddy without a version |
| 14.4.1 | 1 | Content-Type with character set | Met | JSON and `text/html; charset=utf-8` |
| 14.4.2 | 1 | API answers as attachments | Not met | To fix 3 |
| 14.4.3 | 1 | Content-Security-Policy | Met | `deploy/Caddyfile.prod`, `deploy/railway/Caddyfile`; violations fail the journeys (`web/e2e/support.ts`); the certificate page sets its own |
| 14.4.4 | 1 | `X-Content-Type-Options: nosniff` | Met | Caddy and `SECURE_CONTENT_TYPE_NOSNIFF` |
| 14.4.5 | 1 | Strict-Transport-Security | Partly met | One year, without `includeSubDomains` (to fix 19) |
| 14.4.6 | 1 | Referrer-Policy | Met | `strict-origin-when-cross-origin`; `no-referrer` on the certificate page |
| 14.4.7 | 1 | No framing by other sites | Met | `frame-ancestors 'none'`; `X-Frame-Options: DENY` |
| 14.5.1 | 1 | Only used methods; others logged | Partly met | Being built in item 7.10: 405 answered, not logged today |
| 14.5.2 | 1 | Origin header not used for access control | Met | Used only by the CSRF check |
| 14.5.3 | 1 | CORS by strict allow-list | Met | `CORS_ALLOWED_ORIGINS` from the configured HTTPS hosts |
| 14.5.4 | 2 | Proxy headers trusted only from the proxy | Met | `X-Real-IP` set by Caddy (`core/net.py`); the API is not published (`compose.yml`) and listens on 127.0.0.1 when hosted (`deploy/railway/run.sh`); test `iam/tests.py::test_a_forged_forwarded_for_header_does_not_reach_the_records` |

## Next review

At Gate 1 and before go-live (item 7.01 is closed when no high or critical finding is open). Owner: the
Technical Lead, with GSA's IT Officer. The independent penetration test (item 7.02) checks this review.
