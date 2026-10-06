# Data protection impact assessment: GSA LMS

**Draft 1.0, 6 October 2026, ready for GSA's review and signature** (checklist item 0.21; signed under item
7.03). Prepared by the development team for GSA's Data Protection Officer. It covers the learner and teaching
data of the Learning Management System, including students under 18. It follows the structure of the HRMS
assessment (`HRMS/gsa-hrms/docs/privacy/dpia.md`), which covers staff records; the two are read together, as
the LMS takes its staff from the HRMS.

Draft 0.1 (5 October 2026) recorded the privacy features built for checklist items 1.17 to 1.21: the chained
audit log and its viewer, the privacy notice and its acknowledgement, a person's own record, correction
requests, the retention schedule with disposal approved by a second person, the breach register, and the
access review each term. Draft 1.0 adds everything built since: quizzes, practical assessment with
photographs and an optional location, the field logbook and competency records, attendance, forums and
messages, accommodations and extensions, certificates and their public check, the calendar feed, staff
development and the term life-cycle. It adds likelihood and severity to each risk, the consultation, the
questions GSA must answer before signing, and an action list.

GSA is the data controller and owns this assessment; the development team keeps it current as the system
changes. **It is signed in section 11 before any real student record is loaded.** Where a fact is GSA's to
give, this document says so in **bold** and does not guess it; section 9 lists those questions together.

## 1. Legal position

The Data Protection Act No. 18 of 2023 received assent on 16 August 2023. A Commissioner was appointed in
January 2026; reports up to September 2026 say no commencement order has been issued. The LMS is built to
the Act now, so that nothing has to change on the day it commences.

The points below follow the summary of the Act by Jack A. Alli, Sons & Co. ("Data Protection Act 2023:
Summary of Main Requirements"), the same summary used for the HRMS assessment, which does not give section
numbers. **GSA's legal adviser should map each point to the Act's sections and confirm it, in particular
what the Act says about children's data and who may act for a child.** The Electronic Communications and
Transactions Act No. 12 of 2023 gives electronic records legal standing, which supports electronic
submissions, receipts and certificates. The Cybercrime Act 2018 bears on forums and messages.

## 2. Why an assessment is needed

The Act requires an assessment before processing likely to result in a high risk to people's rights. The
LMS processes, for every student and for the staff who teach them:

- the work students hand in, the marks and feedback they receive, quiz attempts, and whether work was late:
  records that decide progression and can affect a person's future;
- data about students who may be under 18 (school leavers entering certificate and diploma programmes);
- possibly health data: the reason for an accommodation or an extension may describe a disability or an
  illness;
- photographs taken during practical work, which may show people and may carry a location;
- forums and private messages, where learners, some of them minors, write to each other and to staff;
- a record of activity (sign-ins, downloads, submissions, check-ins) that, if extended, could become
  monitoring.

Each of these is a reason for care; together they make an assessment necessary even before the Act
commences.

## 3. The processing

**Controller:** Guyana School of Agriculture. **Data Protection Officer:** **to be named by GSA**; the
system has a `dpo` role for whoever GSA names, and the Act requires one for a public body. **Processors:**
the production hosting provider (**in Guyana, to be chosen**, item 7.04) and any service provider
contracted to run or support the system. The Act requires processors to be registered and bound by a
written contract stating the subject-matter and duration, the nature and purpose, the types of data and
categories of people, and the controller's obligations and rights (item 7.21). Staging on Railway (United
States) holds fictional data only and is never used for personal data.

### 3.1 What is processed, and why

| People | Data | Source | Purpose | Lawful basis (as summarised) |
|---|---|---|---|---|
| Students | Name, student number, email, campus | The SRMS | Knowing who belongs to which course | Functions of a public body (education) |
| Students | Course memberships, from SRMS class lists | The SRMS | Giving access to course material | Functions of a public body |
| Students | Submitted work (files and text), time of submission, late flag, receipt code and content fingerprint | The student | Assessment; proof of what was handed in and when | Functions of a public body |
| Students | Marks, rubric scores, written and spoken feedback, released or not | Lecturers | Assessment; coursework totals sent to the SRMS | Functions of a public body |
| Students | Quiz attempts: answers, marks, and the events of each attempt (started, answer saved, page changed, submitted), in server time | The student, the system | Assessment; fairness when an attempt is questioned | Functions of a public body |
| Students | Practical observations against criteria, logbook entries, photographs and scans of their work, and a location if the person recording taps "Add my location" | Lecturers, assessors, the student | Competency-based assessment (TVET Act 2004 standards) | Functions of a public body |
| Students | Competency results by unit and element | Lecturers | Records of competence alongside marks (ADR 0017) | Functions of a public body |
| Students | Attendance at classes: present, late or absent, check-in time | The student (check-in code), lecturers (register) | Attendance where a programme makes it a condition (ADR 0008); totals sent to the SRMS | Functions of a public body |
| Students | Accommodations (extra time, extra days, another format) and why; extensions to a due date and why | Course administrators, lecturers | Treating students fairly; equal access | Functions of a public body; **where the reason concerns health, the Act's conditions for health data apply: GSA's legal adviser to confirm which** |
| Students and staff | Forum posts, reports of posts, acceptance of the conduct statement, participation marks | The person, moderators | Discussion as part of teaching; conduct | Functions of a public body |
| Students and staff | Private messages between a student and teaching staff, and staff notices to a group; read receipts | The person | Teaching | Functions of a public body |
| Students and staff | Completions of a course site; certificates of completion (reference, check code, fingerprint of the PDF) | The LMS | Records of learning; proof of completion; staff development completions sent to the HRMS | Functions of a public body; employment contract (staff) |
| People who check a certificate on the public page | The reference they asked about, whether the code matched, the network address, and when | The person checking | Confirming a certificate is genuine; stopping guessing; telling the holder | Legitimate interests of the person checking and of the holder |
| Staff | Name, employee number, email, campus, post and unit | The HRMS | Knowing who teaches; staff development | Employment contract |
| Staff | Memberships as lecturer or assistant; what they did (content, marks, announcements, decisions on enrolment requests, stand-ins) | The LMS | Running courses; accountability | Employment contract; functions of a public body |
| Staff | Staff development enrolments, learning paths, required training assigned by the HRMS | The person, managers, the HRMS | Development and required training | Employment contract |
| Everyone with an account | Username, roles, sign-ins and sign-outs with network address, devices signed in, failed sign-in attempts, requests for a password link, changes of sign-in email, downloads, the audit log of changes | The system | Security; showing who did what | The Act's security duty; functions of a public body |
| Everyone with an account | Notifications sent to them, whether read, and how they want them by email | The system, the person | Telling people about their courses | Functions of a public body |
| Everyone with an account | A private calendar feed address, if they make one | The person | Due dates and classes in a phone's calendar | Functions of a public body (at the person's request) |
| Everyone with an account | Which version of the privacy notice they read and when; correction requests and answers | The person, course administrators | Showing that people were told, and that requests were answered | The Act's duties to inform and to correct |

**Record of processing activities:** the Act requires the controller to keep one (purposes, categories of
people and data, recipients, transfers, time limits for erasure, security measures). This section and
section 7 are its starting point for the LMS.

### 3.2 Flows to and from the other GSA systems

The LMS owns no person and no result: it holds people by reference to the systems that own them
(`docs/architecture.md`).

| Flow | What it carries | What it never carries |
|---|---|---|
| SRMS to LMS, nightly | Offerings; students' number, name, email and campus; class lists | Date of birth, national identifiers, address, fees, results of other courses |
| LMS to SRMS | Each student's weighted coursework percentage; attendance totals for courses that need them (SRMS side not built yet) | Individual submissions, feedback, attempts or messages |
| HRMS to LMS | Staff number, name, email, campus, post, unit; required training | National identifiers, pay, health, address |
| LMS to HRMS | Staff development completions | Anything about students |
| SRMS and HRMS from LMS | Course sites: code, title, term, campus (scope `sites:read`) | Anything about people |

Each flow uses a service key limited to its scope, kept hashed, and every call is audited.

### 3.3 Recipients

Lecturers and teaching assistants (their own courses only); course administrators and administrators; the
auditor and the DPO (read-only); the SRMS (coursework totals, attendance totals) and the HRMS (staff
development completions); anyone a holder shows a certificate to, who can check it. Nothing is shared for
marketing. No analytics, advertising or tracking service is used, and no web font or script is loaded from
another company.

### 3.4 Transfers outside Guyana

**Learner data stays in Guyana.** Production is to be hosted in Guyana (item 7.04); staging abroad holds
fictional data only; no outside AI service receives learner data (ADR 0007: only with GSA's written
approval after this assessment covers it). Two points remain for GSA (section 9): where GSA's email service
is hosted, since notifications are emailed and name the course and what happened; and where off-site backups
are kept (item 7.09). Until the email service is known to be in Guyana, email notices should carry a link
rather than marks or feedback.

## 4. Students under 18

The LMS holds no date of birth (the SRMS owns it), so it cannot tell who is under 18 and treats every
student alike, with these protections applying to all:

- the privacy notice is written in plain words a school leaver can follow, and says a parent or guardian
  may ask on a student's behalf through the Registry;
- other students never see a student's work, marks or attempts; there are no public profiles and no
  leaderboards;
- forums are inside a course; students cannot message other students unless GSA switches
  `MESSAGING_STUDENT_TO_STUDENT` on (off by default); everyone accepts a conduct statement before posting,
  posts can be reported, and moderators remove posts with a reason;
- a request by a parent or guardian is handled on paper: an administrator or the DPO produces the student's
  record (`/api/v1/privacy/people/<id>/record/`), which is audited;
- the breach register records whether students under 18 were affected, so the risk is weighed accordingly.

**For GSA to decide (section 9):** how the Registry checks that a person asking is entitled to act for a
student; whether the SRMS should send an "under 18" flag (not the date of birth) so that the LMS can apply
any extra rule the Act or GSA requires; and whether photographs of minors in practical evidence need a
rule of their own.

## 5. Necessity and proportionality

What the LMS records is kept to what teaching and security need (`what-we-record.md`):

- Sign-ins and sign-outs with the network address; failed attempts (removed after a year).
- Downloads of course files and submissions; each submission and mark; each change to a course.
- No time on page, no page views, no keystrokes, no tracking cookies, no third-party scripts.
- No location is ever taken in the background. A location is added to a practical observation or logbook
  entry only when the person taps "Add my location", and the record can be saved without it. Attendance
  check-in asks for no location (ADR 0008).
- Quiz attempt events record what the server saw (started, saved, submitted), not the screen, the camera or
  other tabs. ADR 0006 rules out detectors, webcams and lock-down browsers.
- Teaching staff learn only that an accommodation applies, never why; the audit log keeps that the reason
  changed, never the reason.
- A person's own record shows submissions as metadata (which assignment, when, late or not, the file name);
  the work itself is opened from the course, so the copy that may be emailed or saved is small.
- An unreleased mark is not shown to the student until the lecturer releases it.
- The public certificate check shows only what the certificate says, and only to someone with its code.
- The audit entry of a disposal names which work was destroyed, never its content or its mark.
- No decision about a student is made by the system alone; early alerts, when built, follow visible rules
  shown with their evidence to a person (ADR 0007).

Two points are not yet proportionate and are on the action list (section 10): photographs keep the location
the phone wrote into the file, and `what-we-record.md` and the privacy notice do not yet mention
attendance, quiz events, practical locations and read receipts.

## 6. Rights of the people concerned

| Right (as summarised) | How the LMS supports it | Status |
|---|---|---|
| To be told what is processed and why | A versioned notice that an administrator or the DPO publishes; each person reads and acknowledges each version once, at sign-in; the acknowledgement is recorded with the time and audited. Starting text: `privacy-notice-draft.md` | Built (item 1.18); **GSA to approve the text**, which must first be brought up to date (section 10) |
| Access | "My data": the whole record to read and to download as a file; every viewing and download is audited. An administrator or the DPO produces it for a request made on paper | Built (item 1.18) |
| Rectification | A correction request names what is wrong and what it should say; a course administrator answers within `PRIVACY_RESPONSE_DAYS` (30), corrected or not changed with the reason, and the person is told. Nobody answers a request about themselves. Names, numbers and class lists are corrected in the SRMS or HRMS | Built (item 1.18) |
| Erasure | Disposal runs under the retention schedule, approved by a second person, each destruction audited; logs removed nightly | Built (item 1.19) |
| Restriction and objection | Not built in the LMS. The HRMS has them (its item 1.46) | **GSA to decide** whether learners need them here (section 9) |
| Human review of automated decisions | No decision is made by the system alone | Holds by design (ADR 0007) |
| Complaint to the Data Protection Commissioner | Stated in the notice | Built (item 1.18) |

**Breaches:** every personal data breach is recorded in the register: when found, what happened, whose
data, how many people, whether minors were affected, the risk, when contained, when the Commissioner and the
people affected were told, and what was done. Recording one alerts the administrators and the DPO; a breach
is closed only after it is contained. The response procedure is to be written into the runbook (item 7.11).

## 7. Retention (proposals, to be confirmed by GSA)

The schedule is data in the system (`/api/v1/privacy/retention-rules/`, `api/privacy/retention.py`); each
rule shows whether GSA has confirmed it. Records are destroyed only when one person lists what is due and a
second approves; anything can be kept back with a reason (a legal hold). Sign-in attempts and old
notifications are removed every night. "The close of term" is the date a course site closes in the term
calendar (item 7.12), or, for a site whose term is not in the calendar, the last due date of its
assignments.

**Course sites (proposal, to be confirmed by GSA).** At the end of term each site is closed to new work
after its close date and a short grace (`TERM_GRACE_DAYS`, 2 days by default); it is then kept read-only for
appeals, when only a course administrator or an administrator can make a change, and that change is audited. Twelve months
after it closed (`TERM_ARCHIVE_MONTHS`), the site is archived: a read-only export is kept and nothing is
destroyed by archiving. The submissions and marks in it then follow their own rules below.

| Records | Proposal | In the system |
|---|---|---|
| Course sites | Closed at the close of term plus 2 days; read-only for appeals; archived 12 months after closing | Rule `course-sites` (item 7.12, being built) |
| Submitted work (files and text) | 6 years after the close of term | Rule `submitted-work`: reviewed disposal; the submission record and mark stay |
| Marks, feedback and the submission record | 6 years after the close of term | Rule `marks-evidence`: reviewed disposal; coursework totals are kept by the SRMS |
| Forum posts | 3 years after the close of term | Rule `forum-posts`: in the schedule, not yet applied (its note still says there are no forums) |
| Audit log (changes, sign-ins, downloads) | 7 years | Rule `audit-log`: reviewed by GSA; never removed by the system, as it is chained against tampering |
| Sign-in attempts | 1 year | Rule `login-attempts`: removed every night |
| Notifications | 2 years after they were sent | Rule `notifications`: removed every night |
| Private messages | 3 years after the close of term, as forum posts | **Proposed; no rule yet** |
| Quiz attempts and their events | With the marks: 6 years after the close of term | **Proposed; no rule yet** |
| Practical observations, logbook entries, their photographs and locations | With submitted work: 6 years after the close of term | **Proposed; no rule yet** |
| Competency results | **GSA to decide with the Council for TVET**: records of competence may need to be kept longer than marks | **No rule yet** |
| Attendance records | 6 years after the close of term, with the marks | **Proposed; no rule yet** |
| Accommodations and their reasons | 1 year after the student's last course ends | **Proposed; no rule yet** |
| Certificates | As long as GSA wants them checkable; **GSA to decide** | **No rule yet** |
| Checks of certificates on the public page | 1 year, as the HRMS's letter checks | **Proposed; no rule yet** |
| Devices signed in, offline-write keys | A device record ends with its session; offline-write keys 30 days | **Proposed; no rule yet** |
| Privacy notice acknowledgements, correction requests | As long as the account | With the account |
| Access review sign-offs, breach register | 7 years, with the audit log | |
| Backups | **Period set in item 7.09**; destroyed records stay in backups until those expire | Being built |
| Fictional demonstration data | Never on a database with real records | `seed_demo` and `seed_journeys` refuse to run without `--fictional` |

## 8. Risks and measures

Likelihood and severity are judged before the measures; the residual risk is what remains with them in
place. Controls are described in the threat model (`docs/security/threat-model.md`) and checked in the
review against OWASP ASVS Level 2 (`docs/security/asvs-l2.md`).

| Risk to people | Likelihood | Severity | Measures | Residual |
|---|---|---|---|---|
| A student sees another student's work, marks or attempts | Possible | Significant | Access decided by course membership in one place (`courses/access.py`); students see their own submissions and released marks only; tested refusals (`courses/test_scope.py`) | Low |
| Someone changes a mark and hides it | Possible | Significant | Every mark is audited; the audit log is insert-only and chained, checked every night, with an alert to administrators and the auditor; marks lock once the SRMS accepts them | Low |
| An account is taken over and used to change marks | Possible | Significant | Lockout on passwords; an authenticator code for teaching staff and administrators; sessions end after 30 minutes idle and 8 hours in all. Code guessing to be limited (ASVS fix 1) | Low once fixed; Medium until then |
| Quiz answers shared, or work handed in for someone else | Likely | Moderate | Question pools and shuffling, server time limits, attempt events, receipts; no surveillance (ADR 0006) | Medium: an academic-integrity matter for lecturers, not a data protection one |
| Attendance recorded for someone not present (a code passed on) | Possible | Minor | Codes valid for one minute, one check-in per class, the lecturer's register | Medium, accepted (ADR 0008) |
| A health reason for an accommodation or extension seen by the wrong person | Possible | Significant | Reasons seen only by course administrators; masked in the audit log. To encrypt the stored reason and keep extension reasons out of the log (ASVS fix 4) | Low once fixed |
| A photograph reveals where a student lives or works, or shows a minor | Possible | Moderate | Location added only on a tap; downloads only for the course's staff and the student, audited. To remove location data from photographs on upload (section 10) | Low once fixed |
| Harmful or abusive content in forums or messages, involving minors | Possible | Significant | Conduct statement; reports and moderation with reasons; no student-to-student messages by default; everything audited | Low |
| A malicious file passed to staff through an upload | Possible | Moderate | Files checked by their contents; macros refused; downloads as attachments. Virus scan to add (ASVS fix 15) | Medium until a scan is added |
| A certificate forged, or a holder's details read by guessing | Unlikely | Moderate | Random 60-bit code, encrypted; same answer for unknown and wrong; limits; the holder told of each check | Low |
| Activity data used to monitor students or staff | Possible | Moderate | Only sign-ins, downloads, submissions, check-ins and attempt events recorded; no time on page; stated in the notice | Low |
| Data left on a shared phone | Likely | Moderate | Only the person's own work waits offline; the field class list is cleared on sign-out. To clear it on time-out too, and stop browsers keeping API answers (ASVS fixes 3 and 7) | Low once fixed |
| Work kept longer than needed | Likely until confirmed | Moderate | Retention schedule with reviewed disposal; nightly purge of logs; rules to add for messages, attempts, evidence and attendance | Low once GSA confirms the periods |
| Records lost or unavailable | Possible | Significant | Encrypted daily backups with an off-site copy and a timed restore drill (item 7.09, being built); hosting in Guyana (item 7.04) | Low once built |
| Data leaves Guyana | Possible | Moderate | Hosting in Guyana; staging fictional; no outside AI; email to carry links until its hosting is known | Low once GSA answers section 9 |
| A role kept after someone leaves or stops teaching | Possible | Moderate | Accounts closed when the SRMS or HRMS marks a person inactive; access review each term. Role changes to be audited (ASVS fix 2) | Low |
| A breach not handled in time | Possible | Significant | Breach register with alerts; the DPO named in the system; monitoring and alerts (item 7.10) | Medium until GSA names the DPO and the procedure is written |
| Data of minors handled like adults' | Likely | Moderate | Same protections for all; parent or guardian requests through the Registry; minors flagged in breaches | Medium until GSA decides section 4's open points |

No high residual risk remains once the actions in section 10 are done. The summary consulted does not
describe a duty to consult the Commissioner before processing; the legal adviser should confirm whether one
applies to the risks left at Medium.

## 9. Questions GSA must answer before signing (decision D9)

These are GSA's to answer; the system is built so that each answer is a setting or a rule, not a rebuild.

1. Who is the Data Protection Officer, and how are they reached (for the notice)?
2. Will GSA register as a data controller when the Act commences, and its service provider as a processor?
   Who signs the processing contract (item 7.21)?
3. Where will production be hosted in Guyana (item 7.04), where is GSA's email service hosted, and where will
   off-site backups be kept (item 7.09)?
4. The retention periods in section 7, including the course-site proposal and the rows marked "GSA to
   decide".
5. Students under 18: how the Registry checks a parent's or guardian's entitlement; whether the SRMS should
   send an "under 18" flag; what the legal adviser says the Act requires for children's data; whether
   photographs of minors need their own rule.
6. Whether learners need restriction and objection in the LMS, as staff have in the HRMS.
7. Whether health reasons for accommodations may be kept in the LMS at all, or only that an accommodation
   applies, with the reason held by Student Services on paper.
8. Whether recording a location with practical evidence is wanted, or should be switched off.
9. Approval of the privacy notice text, once brought up to date.
10. Who to consult (section 10): student representatives, and parents of students under 18.

## 10. Consultation and actions

**To consult before sign-off:** GSA's Data Protection Officer; the Registrar (the SRMS and requests by
parents); the heads of department (marking and practical evidence); the IT Officer (hosting, backups,
email); student representatives, and through the Registry the parents of students under 18; GSA's legal
adviser. The outcome of each is recorded below this list when it has happened.

**Actions before real data is loaded:**

| Action | Kind | Owner | Item |
|---|---|---|---|
| Answer the questions in section 9 | Decision | GSA | D9, 7.03 |
| Bring `what-we-record.md` and the privacy notice up to date: attendance and check-in times, quiz attempt events, practical locations and photographs, message read receipts, certificate checks | Documentation | Development team, then GSA to approve | 1.18, 1.20 |
| Add retention rules for messages, quiz attempts, practical evidence, attendance, accommodations, certificate checks and session records, and correct the forum note | Code, periods from GSA | Development team | 1.19 (ASVS fix 13) |
| Encrypt accommodation reasons; keep extension reasons out of the audit log | Code | Development team | ASVS fix 4 |
| Remove location and other metadata from photographs on upload | Code | Development team | Threat model, section 5 |
| Limit authenticator code guesses; audit role changes; no caching of API answers; clear the field copy on time-out | Code | Development team | ASVS fixes 1, 2, 3, 7 |
| Virus scan of uploads | Code and configuration | Development team | ASVS fix 15 |
| Encrypted backups, off-site copy, timed restore drill | Operations | Development team, IT Officer | 7.09 |
| Monitoring and alerts | Operations | Development team | 7.10 |
| Runbook: breach procedure, key rotation, authenticator reset with proof of identity | Documentation | Development team, IT Officer | 7.11 |
| Hosting in Guyana; processing contract | Hosting, contract | GSA | 7.04, 7.21 |
| Independent penetration test | Assurance | GSA | 7.02 |

## 11. Sign-off

Signing confirms that GSA, as controller, accepts the processing described, the measures and the residual
risks in section 8, on the answers given to section 9.

| Role | Name | Decision | Date |
|---|---|---|---|
| Prepared by (development team) | | Draft 1.0 for signature | 6 October 2026 |
| Reviewed by GSA's legal adviser | | | |
| Data Protection Officer | | | |
| Approved for GSA as controller (the Principal or the Board) | | | |
| Next review | | Before each release, on any new processing, and before any outside AI service or content player is used | |
