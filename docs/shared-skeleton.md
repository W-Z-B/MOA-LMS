# Keeping the shared skeleton in step

**Version 0.1 draft, 6 October 2026.** Checklist item 0.24 (gap G1).

The three GSA systems, the HRMS, the SRMS and the LMS, are built on the same skeleton: five backend modules
that do the same job in each. This page sets out how a fix made in one system reaches the other two. It is a
procedure only: nothing in it changes code in any repository.

## 1. Why

- **The LMS took its skeleton from the HRMS before HRMS pull requests 15 to 39.** Those pull requests
  hardened the HRMS: sign-in and sessions, accounts, an audit log that shows tampering, privacy rights and
  retention. The feature audit found thirteen weaknesses in the LMS that the HRMS had already fixed or that
  its checks would catch (Feature Audit, finding 6; gap G1).
- **The HRMS versions are the hardened ones.** Its threat model (`HRMS/gsa-hrms/docs/security/threat-model.md`)
  has been reviewed at every pull request since 16, and each weakness it found was fixed in the code there
  first.
- **A security fix found in one system must reach all three.** The same attacks apply to each, and an
  attacker needs only the weakest. A fix left in one repository is a known weakness in the other two.
- **The SRMS is still at the scaffold.** Its repository (`SRMS/gsa-srms`) has three commits and the same
  four modules as the scaffold (`core`, `iam`, `audit`, `notifications`), with no chained audit log, no upload
  check by content, no session records and no `privacy` module. It will need the most porting, and should
  take it from the leading repository named below, not from the LMS's copy.

## 2. The shared modules

Compared on 6 October 2026: the LMS on branch `feature/finish-help-golive` (this worktree), the HRMS on
`feature/phase-2-font` (its pull request 39 and the font commit after it), the SRMS on `main`.

| Module | What it holds | Leads | Why | Known differences |
|---|---|---|---|---|
| `core` | Field encryption and fingerprints (`crypto.py`, `fields.py`), the client address from Caddy (`net.py`), one error shape (`exceptions.py`), base models, uploads checked by content (`uploads.py`), Home, search and To do | **HRMS** | `crypto.py`, `fields.py`, `net.py`, `models.py` and `views.py` are identical in both; `uploads.py` was ported from the HRMS | The LMS's `uploads.py` adds PowerPoint and recorded audio (item 2.24) and reads 64 bytes, not 32; Home, search and To do are each system's own, not shared |
| `iam` | Roles and their scope, the permission layer, authenticator codes, sessions and idle time-out, sign-in limits, accounts by invitation and password links, change of sign-in email, the access review each term, the admin site | **HRMS** | Hardened in its pull requests 16, 18 and 34 and reviewed in its threat model; the LMS's accounts, email change and access review were ported from it | Campus scope is a campus record in the HRMS and a campus code plus **site membership** in the LMS; lecturers need an authenticator code in the LMS (ADR 0013); the LMS signs a person out everywhere when a role is given or taken away (`iam/sessions.py`) and has a `role_required` helper; accounts are opened from the employee record in the HRMS and from the person record (`people.PersonRef`) in the LMS |
| `audit` | The insert-only audit log, chained fingerprints and the nightly check, the audit viewer and its export | **HRMS** | The chain was built there (pull request 19) and ported unchanged: `chain.py` differs only in an item number | "The employee the record is about" is "the person" in the LMS; the LMS adds `words.py`, which says each entry in words for the viewer and for a person's own record |
| `notifications` | Notifications in the app and by email, with a link only in the email | **HRMS** for sending and what an email may carry; **LMS** for preferences and the daily summary | The HRMS's is the reviewed source for what leaves by email (its item 2.26); the LMS's is ahead in letting each person choose, kind by kind, email at once, a daily summary or none (item 2.33) | "GSA HRMS" or "GSA LMS" in the subject; the link's address comes from different settings; recipients by campus record or campus code |
| `privacy` | The versioned notice and its acknowledgement, a person's own record, correction requests, restriction and objection, the retention schedule with disposal approved by a second person, the breach register, the DPO role | **HRMS** for the framework, correction requests, restriction and objection; **LMS** for the learner-facing parts of retention and breaches | The HRMS's is more complete: it has restriction and objection (pull request 36), which the LMS has not, and the LMS's notice, record and corrections were ported from its pull request 20. The LMS is ahead where learners differ: disposal of submitted work that keeps a record of which work went but never the work or the mark, the retention rules seeded in code, a seeded notice text (`notice_text.py`), and a breach field for students under 18 | A person's own record holds the staff file in the HRMS and memberships, submissions, released marks and teaching actions in the LMS; correction requests are answered by HR in the HRMS and by a course administrator in the LMS |

**Names adapted when porting.** A fix keeps its logic and changes its words:

| HRMS | LMS | SRMS |
|---|---|---|
| employee (`people.Employee`) | person (`people.PersonRef`) | student or staff member (to confirm when ported) |
| HR, HR officer | course administrator | Registry (to confirm) |
| campus scoping (a campus record on the role) | campus code on the role, plus site membership for teaching | campus (to confirm) |
| "GSA HRMS" in emails and pages | "GSA LMS" | "GSA SRMS" |
| HRMS checklist item numbers (for example 1.26) | the LMS's own (for example 1.17) | the SRMS's own |

## 3. The rule for a change to a shared module

A pull request or commit that changes `core`, `iam`, `audit`, `notifications` or `privacy` **names the module
in its title**, for example "iam: a role taken away signs the person out everywhere". This lets anyone reading
the history of any of the three repositories find what may need porting, with
`git log --oneline -- api/iam` or by the title.

Its description says whether the change is a fix that the other systems need, a change for this system only,
or not yet decided.

## 4. Porting a fix

1. **Find the fix and its tests in the leading repository.** Read the commit, not only the pull request's
   title. Note the files, the tests that prove it, and the threat-model or impact-assessment entry that
   records it.
2. **Check whether each other repository has the same code.** Compare the files side by side. The weakness
   may be there in the same form, in a different form (names adapted), or not at all (never built, or fixed
   another way). Record "not affected" with the reason if so.
3. **Port it with the names adapted** (section 2). Keep the logic the same; change only names, words and
   item numbers. Do not mix the port with other work.
4. **Port the tests too.** A fix without its test can come undone unseen. Adapt the test data to the system,
   and check that the test fails without the fix.
5. **Run the gates** of the receiving repository (its `CONTRIBUTING.md`): backend tests with coverage, lint
   and format, the API documentation check, the production security check, and the web checks if the web is
   touched.
6. **Reference the source commit in the commit message**, on a line of its own:
   `Ported from HRMS <hash>` (or `from LMS <hash>`, `from SRMS <hash>`), with the pull request number if
   there is one. Update the receiving system's threat model or impact assessment if the fix is recorded in
   the source's.
7. **Record it in the "Ported fixes" log** at the end of this page, in the receiving repository's copy, and
   mark the source's entry once all three systems have it or are recorded as not affected.

A security fix is ported **before the next release** of each receiving system. Other fixes are ported at the
next comparison (section 5) at the latest.

## 5. The comparison at each release

At each release of any of the three systems:

1. Compare the five shared modules side by side across the three repositories (a file-by-file comparison of
   `api/core`, `api/iam`, `api/audit`, `api/notifications` and `api/privacy`).
2. List every difference, and for each say why it exists: names adapted, a feature one system needs and the
   others do not, or a fix not yet ported.
3. For each fix not yet ported, decide: port it (section 4), or record the difference here with the reason
   it stays.
4. Update the table in section 2 and the differences in section 6.

## 6. Differences found on 6 October 2026, to decide

| Difference | Where it is | Proposed |
|---|---|---|
| Restriction and objection | HRMS only (pull request 36, `d3b5399`) | Port to the LMS if GSA decides learners need them (LMS impact assessment, section 6); then to the SRMS |
| A role given or taken away signs the person out everywhere, by a signal on the role | LMS (`iam/sessions.py`, from `70645fa`) | Compare with how the HRMS ends sessions when roles change; port to the HRMS if it leaves a gap |
| Audit entries said in words | LMS only (`audit/words.py`) | Port to the HRMS when its audit viewer is next changed |
| Notification preferences and the daily summary | LMS only (item 2.33, `628f5e5`) | Offer to the HRMS; not a security fix |
| Breach field for students under 18 | LMS only | Port to the SRMS when its privacy module is built |
| A shared phone never sends one person's waiting work under another's session (offline queue) | LMS web (`efc50b1`); the HRMS's `offlineQueue.ts` records no owner | Outside the five modules but under the same rule: check the HRMS web and port if affected |
| The whole hardened skeleton | HRMS and LMS; not in the SRMS | Port from the leading repository, module by module, before the SRMS holds real data |

## 7. Ports already made

The LMS's Phase 1 brought the HRMS's hardening across on 5 October 2026, before this procedure existed. They
are recorded here as the starting point; the commits named are real.

| Module | What | From HRMS | To LMS | Tests in the LMS |
|---|---|---|---|---|
| `audit`, `core` | Chained fingerprints, the nightly check and the audit viewer; `fingerprint()` and `chain_key()` | Pull request 19, `bc713b0` | `109d75c` | `audit/test_chain.py` |
| `iam`, `core` | Sign-in limit per address, verified sessions, idle time-out, client address from Caddy, one error shape | Pull requests 16 and 18, `d07aa49` and `1eaba81` | `70645fa` | `iam/test_sessions.py`, `core/test_net.py`, `iam/tests.py` |
| `core` | Uploads checked by their content | `core/uploads.py` (commit not recorded in the LMS message) | `813fafb` | `core/test_uploads.py` |
| `privacy` | The notice, a person's own record, corrections, retention with reviewed disposal, breaches | Pull requests 20 and 21, `a19bc99` and `8fec4f5` | `2d4fdf4` | `privacy/tests.py`, `privacy/test_retention.py` |
| `iam` | Access review reminder each term | Pull request 18, `1eaba81` | `14feff4` | `iam/test_review.py` |
| `iam` | Accounts by invitation and one-use password links | Pull request 18, `1eaba81` | `b525f19` | `iam/test_accounts.py` |
| `iam` | Sign-in email changes only once the new address confirms it | Pull request 34, `a7217f7` | `85a4c72` | `iam/test_email_change.py` |

## 8. Who does what

| Who | Does |
|---|---|
| The developer who makes a fix in a shared module | Names the module in the title; says in the description whether the other systems need it; opens the port, or a task for it, in each other repository |
| The developer who ports | Follows section 4; records it in the log |
| The reviewer of the pull request | Checks the title names the module, the tests came across, and the commit message names the source |
| The release lead of each system | Runs the comparison in section 5 before the release and signs off the differences |
| GSA's IT Officer | Receives the list of differences recorded at each release, so that GSA knows what is the same and what is not across its three systems |

## 9. Later: one shared package

Keeping three copies in step by hand works while the systems are young and the team is small. Later the five
modules could become one package that all three systems install, so that a fix is made once. **This is a
note only, not a plan.** It would need a decision record weighing: how the names that differ (employee,
person, student) are handled; how a change is released to three systems at once without breaking one; who
owns the package; and whether GSA's support arrangements can maintain it. Until such a decision is made, the
procedure on this page applies.

## Ported fixes

One line per port, in the receiving repository's copy of this page.

| Date | Module | Fix | From repo and commit | To repo and commit | Tests |
|---|---|---|---|---|---|
| | | | | | |
