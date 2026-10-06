# Data protection impact assessment: GSA LMS

**Draft 0.1, 5 October 2026,** prepared by the development team for GSA's Data Protection Officer.
It covers the learner and teaching data of the Learning Management System, including students under 18.
It follows the structure of the HRMS assessment (`HRMS/gsa-hrms/docs/privacy/dpia.md`), which covers staff
records; the two are read together, as the LMS takes its staff from the HRMS. GSA is the data controller and
owns this assessment; the development team keeps it current as the system changes. It is signed in
section 9 before any real student record is loaded.

Draft 0.1 records the privacy features built for checklist items 1.17 to 1.21: the chained audit log and its
viewer, the privacy notice and its acknowledgement, a person's own record, correction requests, the retention
schedule with disposal approved by a second person, the breach register, and the access review each term.

## 1. Legal position

The Data Protection Act No. 18 of 2023 received assent on 16 August 2023; press reports up to September
2026 say no commencement order has been issued. The LMS is built to the Act now, so that nothing has to
change on the day it commences. The points below follow the published summary of the Act used for the
HRMS assessment, which does not give section numbers. **GSA's legal adviser should map each point to the
Act's sections and confirm it, in particular what the Act says about children's data.**

## 2. Why an assessment is needed

The LMS processes, for every student and for the staff who teach them:

- the work students hand in, the marks and feedback they receive, and whether work was late: records that
  decide progression and can affect a person's future;
- data about students who may be under 18 (school leavers entering certificate and diploma programmes);
- a record of activity (sign-ins, downloads, submissions) that, if extended, could become monitoring.

Each of these is a reason for care; together they make an assessment prudent even before the Act
commences.

## 3. The processing

**Controller:** Guyana School of Agriculture. **Data Protection Officer:** to be designated; the system has
a `dpo` role for whoever GSA names. **Processors:** the hosting provider for production (in Guyana,
to be confirmed). Staging on Railway (United States) holds fictional data only.

| People | Data | Source | Purpose | Lawful basis (as summarised) |
|---|---|---|---|---|
| Students | Name, student number, email, campus | The SRMS | Knowing who belongs to which course | Functions of a public body (education) |
| Students | Course memberships (from SRMS class lists) | The SRMS | Giving access to course material | Functions of a public body |
| Students | Submitted work (files and text), time of submission, late flag | The student | Assessment | Functions of a public body |
| Students | Marks and feedback, released or not | Lecturers | Assessment; coursework totals sent to the SRMS | Functions of a public body |
| Students | The words of their work and its fingerprints, compared with other GSA work on GSA's server; matching passages (item 3.20, ADR 0020) | The LMS | Academic integrity: evidence for a lecturer to judge, never a decision by itself | Functions of a public body |
| Students | Peer reviews they write and receive (item 4.13): seen by classmates without names | Students | Learning by assessing; optionally part of the mark | Functions of a public body |
| Open-course learners (only if GSA turns it on, ADR 0021) | Name and email address they give, network address of the request | The person | Short courses for farmers and extension officers | Consent given when registering; to confirm with GSA |
| Students and staff | Completions of a course site | The LMS | Records of learning; staff development completions sent to the HRMS | Functions of a public body; employment contract (staff) |
| Staff | Name, employee number, email, campus | The HRMS | Knowing who teaches | Employment contract |
| Staff | Memberships as lecturer or assistant; what they did (content, marks, announcements) | The LMS | Running courses; accountability | Employment contract; functions of a public body |
| Everyone with an account | Username, roles, sign-ins and sign-outs with network address, failed sign-in attempts, downloads, the audit log of changes | The system | Security; showing who did what | The Act's security duty; functions of a public body |
| Everyone with an account | Notifications sent to them, whether read | The system | Telling people about their courses | Functions of a public body |
| Everyone with an account | Which version of the privacy notice they read and when; correction requests and answers | The person, course administrators | Showing that people were told, and that requests were answered | The Act's duties to inform and to correct |

**Recipients:** lecturers and teaching assistants (their own courses only), course administrators and
administrators, the auditor and the DPO (read-only), the SRMS (coursework totals) and the HRMS (staff
development completions). Nothing is shared for marketing. No analytics or advertising service is used.

**Transfers outside Guyana:** none planned for real data. To confirm: where GSA's email service is hosted
(notifications are emailed) and where off-site backups are kept.

## 4. Students under 18

The LMS holds no date of birth (the SRMS owns it), so it cannot tell who is under 18 and treats every
student alike, with the protections below applying to all. Points for GSA:

- The notice is written in plain words a school leaver can follow; it says a parent or guardian may ask on
  a student's behalf through the Registry.
- A request by a parent or guardian is handled on paper: an administrator or the DPO produces the student's
  record (`/api/v1/privacy/people/<id>/record/`), which is audited. GSA to decide how the Registry checks
  that the person asking is entitled to.
- Other students never see a student's work or marks; there are no public profiles, no leaderboards and no
  forums yet. When forums are added (feature list), posts by minors must not be visible outside the course.
- The breach register records whether students under 18 were affected, so the risk is weighed accordingly.
- **To decide:** whether the SRMS should send an "under 18" flag (not the date of birth) so that the LMS can
  apply any extra rule the Act or GSA requires.

## 5. Necessity and proportionality (item 1.20)

What the LMS records is kept to what teaching and security need (see `what-we-record.md`):

- Sign-ins and sign-outs with the network address; failed attempts (removed after a year).
- Downloads of course files and submissions; each submission and mark; each change to a course.
- No time on page, no page views, no location, no keystrokes, no tracking cookies, no third-party scripts.
- A person's own record shows submissions as metadata (which assignment, when, late or not, the file name);
  the work itself is opened from the course, so the copy that may be emailed or saved is small.
- An unreleased mark is not shown to the student until the lecturer releases it.
- The audit entry of a disposal names which work was destroyed, never its content or its mark.

## 6. Rights of the people concerned

| Right (as summarised) | How the LMS supports it | Status |
|---|---|---|
| To be told what is processed and why | A versioned notice that an administrator or the DPO publishes; each person reads and acknowledges each version once, at sign-in; the acknowledgement is recorded with the time and audited. Starting text: `privacy-notice-draft.md` | Built (1.18); GSA to approve the text |
| Access | "My data": the whole record to read and to download as a file; every viewing and download is audited. An administrator or the DPO produces it for a request made on paper | Built (1.18) |
| Rectification | A correction request names what is wrong and what it should say; a course administrator answers within `PRIVACY_RESPONSE_DAYS` (30), corrected or not changed with the reason, and the person is told. Nobody answers a request about themselves. Names, numbers and class lists are corrected in the SRMS or HRMS | Built (1.18) |
| Erasure | Disposal runs under the retention schedule, approved by a second person, each destruction audited; logs removed nightly | Built (1.19) |
| Restriction and objection | Not built in the LMS. The HRMS has them (its item 1.46); GSA to decide whether learners need them here | Open |
| Complaint to the Data Protection Commissioner | Stated in the notice | Built (1.18) |

**Breaches:** every personal data breach is recorded in the register: when found, what happened, whose
data, how many people, whether minors were affected, the risk, when contained, when the Commissioner and
the people affected were told, and what was done. Recording one alerts the administrators and the DPO; a
breach is closed only after it is contained.

## 7. Retention (proposals, to be confirmed by GSA)

The schedule is data in the system (`/api/v1/privacy/retention-rules/`); each rule shows whether GSA has
confirmed it. The LMS holds no term dates, so "the end of the term" is the last due date of the course's
assignments.

| Records | Proposal | How |
|---|---|---|
| Submitted work (files and text) | 6 years after the end of the term | Reviewed disposal; the submission record and mark stay |
| Marks, feedback and the submission record | 6 years after the end of the term | Reviewed disposal; coursework totals are kept by the SRMS |
| Forum posts | 3 years after the end of the term | No forums yet |
| Audit log (changes, sign-ins, downloads) | 7 years | Reviewed by GSA; never removed by the system, as it is chained against tampering |
| Sign-in attempts | 1 year | Removed every night at 04:00 |
| Notifications | 2 years after they were sent | Removed every night at 04:00 |
| Privacy notice acknowledgements, correction requests | As long as the account | With the account |
| Access review sign-offs | 7 years, with the audit log | |

## 8. Risks and measures

| Risk | Measures | Residual |
|---|---|---|
| A student sees another student's work or marks | Access decided by course membership; students see their own submissions and released marks only; tested refusals | Low |
| Someone changes a mark and hides it | Every mark is audited; the audit log is insert-only and chained, checked every night, with an alert to administrators and the auditor | Low |
| Activity data used to monitor students or staff | Only sign-ins, downloads and submissions are recorded; no time on page; stated in the notice | Low |
| Work kept longer than needed | Retention schedule with reviewed disposal; nightly purge of logs | Low once GSA confirms the periods |
| A role kept after someone leaves or stops teaching | Access review each term, with a reminder listing role holders and teaching staff | Low |
| A breach not handled in time | Breach register with alerts; the DPO named in the system | Medium until GSA names the DPO and a procedure |
| Data of minors handled like adults' | Same protections for all; parent or guardian requests through the Registry; minors flagged in breaches | Medium until GSA decides section 4's open points |

## 9. Sign-off

| | Name | Date |
|---|---|---|
| Data Protection Officer | | |
| Principal (for GSA as controller) | | |
