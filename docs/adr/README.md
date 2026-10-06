# Decision records

One file per significant decision: the context, the decision and its consequences. A decision is changed by
a new record that amends or replaces it, never by editing an accepted one. The D numbers are the decisions
in section 4 of the GSA LMS Gold Standard Feature Audit; the item numbers are those of the Implementation
Checklist. Both documents are kept with the project's planning documents, not in this repository.

On 5 October 2026 development continued on the audit's recommended answers. Those records say "accepted on
the recommended answer"; GSA may revise any of them by a new record.

| Record | Decision | Plan | Status |
|---|---|---|---|
| [0001](0001-stack-selection.md) | Technology stack and licence policy | | Accepted for Release 1; licence policy amended by 0002 |
| [0002](0002-licence-policy.md) | Licence policy, amended to match what ships (named LGPL and MPL exceptions) | | Proposed; accepted when the item 0.20 pull request merges |
| [0003](0003-scope-and-releases.md) | Scope and releases from the 42-feature audit | D0 | Accepted on the recommended answer |
| [0004](0004-build-path.md) | Continue the GSA LMS, with Moodle as the reference | D15 | Accepted on the recommended answer |
| [0005](0005-quizzes-built-in.md) | Quizzes built into the LMS, with question import | D1 | Accepted on the recommended answer |
| [0006](0006-academic-integrity.md) | Academic integrity without detectors or webcams | D4 | Accepted on the recommended answer |
| [0007](0007-ai-assistance.md) | What AI may be used for | D5 | Accepted on the recommended answer |
| [0008](0008-attendance-in-the-lms.md) | The LMS takes attendance; the SRMS receives the totals | D6 | Accepted on the recommended answer |
| [0009](0009-quality-tooling.md) | Test tooling, quality gates and locked dependencies | | Proposed; accepted when the item 0.20 pull request merges |
| [0010](0010-navigation-by-role.md) | Navigation by role: a Home for each role, search, and To do | | Accepted on the recommended answer (as HRMS ADR 0010) |
| [0011](0011-phone-delivery.md) | Phones use the installable web app, with push and offline work | | Accepted on the recommended answer (as HRMS ADR 0005) |
| [0012](0012-new-components.md) | New components approved under the licence policy | D10 | Accepted on the recommended answer |
| [0013](0013-lecturer-authenticator-code.md) | Lecturers use an authenticator code | D14 | Accepted on the recommended answer |
| [0014](0014-packaged-content.md) | Packaged content: SCORM and H5P players | D2 | Proposed, open |
| [0015](0015-video-and-captions.md) | Where video is kept, and how it is made light and captioned | D3 | Accepted on the recommended answer |
| [0016](0016-accounts-and-sign-on.md) | Accounts for students and lecturers, and when one sign-on comes | D7 | Proposed, open |
| [0017](0017-competency-records.md) | Competency records beside marks | D8 | Proposed, open |
| [0018](0018-text-and-whatsapp-notices.md) | Text messages and WhatsApp for urgent notices only | D12 | Proposed, open |
| [0019](0019-required-training.md) | The HRMS says which staff must take which training | D13 | Proposed, open |
| [0020](0020-reports-by-role-grant.md) | Who reads the reports that leave a course: heads of department by unit, the Registrar by campus | | Proposed; built this way, GSA to confirm |
| [0021](0021-similarity-check-method.md) | How the similarity check compares work: winnowed fingerprints on GSA's server | D4 | Accepted, carrying out 0006 |
| [0022](0022-open-short-courses.md) | Open short courses for farmers and extension officers: built, switched off | D0 | Proposed, open |

## Open decisions with no record yet

| Decision | Question | Why there is no record |
|---|---|---|
| D9 | GSA's outstanding answers: what is used today, courses and lecturers per campus, the coursework and examination split, competency-based programmes, attendance rules, devices and connectivity, a data protection contact, hosting | An information request to GSA (item 0.14), not a design choice: GSA-LMS-Information-Request.md, kept with the planning documents, version 1.0 of 6 October 2026, reply requested by 27 October 2026. No real learner data is loaded until it is answered. |
| D11 | Branch protection and the issue board | A repository setting for the owner (item 0.22); the gates in [ADR 0009](0009-quality-tooling.md) bind only once it is on. |

To accept a proposed record, change its status line to "Accepted", with the date and who decided, in a pull
request. To revise one accepted on the recommended answer, write a new record that replaces it.
