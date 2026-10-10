# What the LMS records about activity (item 1.20)

Activity tracking is kept to what teaching and security need. This page lists everything the LMS records
when people use it, so that the privacy notice can say it and anyone adding a feature can check it.

| What | When | Kept where | Who reads it | How long |
|---|---|---|---|---|
| Sign-in and sign-out, with the network address | Each time | Audit log | Administrators, the auditor; the person in My data | The audit log's period (proposal 7 years) |
| Failed and successful sign-in attempts | Each attempt | Sign-in attempts (account lockout) | The system | 1 year, removed nightly |
| Authenticator code accepted or refused | Each time (administrative roles) | Audit log | Administrators, the auditor | With the audit log |
| Download of a course file or a submission | Each time | Audit log | Administrators, the auditor | With the audit log |
| Submission of work, with the time and the late flag | Each time | Submissions, audit log | The student, the course's teaching staff | 6 years after the term (proposal) |
| A mark given or changed, and its release | Each time | Marks, audit log | The student once released, the course's teaching staff | 6 years after the term (proposal) |
| A change to a course (content, assignment, membership) | Each time | Audit log, with who and why | Administrators, the auditor; the person who made it in My data | With the audit log |
| Reading of the privacy notice | Once per version | Acknowledgements, audit log | Administrators, the DPO | With the account |
| Viewing or downloading one's own record | Each time | Audit log | Administrators, the auditor | With the audit log |
| Notifications sent, and whether read | Each one | Notifications | The person | 2 years, removed nightly |
| First opening of a course item (a page opened, a file downloaded, or marked complete), once per item | The first time only | Item completions | The student; the course's teaching staff, as progress and course analytics (items 2.16, 6.01, 6.02) | With the course's records |
| Early alerts: a visible rule (missed work, falling marks, no recorded activity for a number of days) matched, with its evidence and what a person decided | Checked nightly; one alert per piece of evidence | Early alerts, audit log | The course's teaching staff and course administrators; never shown to the student as a label; included in the copy of a person's record produced for a request (item 6.05) | With the course's records |
| Viewing or exporting a report that leaves a course (courses, staff development) | Each time | Audit log | Administrators, the auditor | With the audit log |
| Opening an outside tool (LTI launch): which tool, which course, whether names or emails were sent | Each launch | Audit log | Administrators, the auditor | With the audit log |
| A score an outside tool posts, and a tool reading a class list | Each time | Tool scores, audit log | The student, the course's teaching staff | With the marks; the audit log |
| A question to the AI study helper: when, by whom, whether answered, which items were the sources (never the question or the answer) | Each question | AI exchanges | The system | 1 year, removed nightly (rule `ai-exchanges`) |
| An AI draft for a lecturer, and the record it was saved as | Each draft | AI exchanges, audit log ("AI-drafted") | Administrators, the auditor | Drafts 1 year; the audit entry with the audit log |
| A secure exam sitting's integrity event: the quiz window lost or regained focus, or a copy, paste or right-click attempt on the exam page (item 3.25) | Each event, only while a secure exam attempt is open | Quiz attempts (`AttemptEvent`) | The course's teaching staff, same as the attempt's full event log; never shown to the student as a label | With the attempt |

## What the LMS does not record

- How long anyone spends on a page, how often they open a page, or how they move through a course. Only the
  first opening of each item is kept, as progress; "last seen" on a course is worked out from what is
  already recorded (that first opening, hand-ins, quiz attempts, posts, messages and classes attended), not
  from page views.
- Location, device fingerprints, keystrokes or screen activity.
- Any cookie other than the session and the form-protection (CSRF) cookie. No analytics, advertising or
  third-party script is loaded.

## Adding something to this list

A feature that records anything new about what people do needs, before it is merged:

1. a line in this table;
2. the matching sentence in the privacy notice (`api/privacy/notice_text.py` for the seeded draft, and a
   new published version once GSA has approved the change);
3. a retention rule, or a statement that it goes with the audit log;
4. a note in the impact assessment (`dpia.md`).

Tracking of time on page or of page views stays off unless GSA decides otherwise and the notice says so.

## Early alerts (item 6.05, decision D5, ADR 0007)

Early alerts follow rules anyone can read, never a prediction. The rules and their thresholds are data a
course administrator changes (Admin, and the Insights tab of a course shows them):

- **Missed work:** a number of pieces of work past their due date with nothing handed in, within a window
  of days (to start: 2 in 28 days).
- **Falling marks:** the two latest marks are, on average, a number of percentage points below the
  student's earlier marks, the latest within a window of days (to start: 15 points, 28 days).
- **No visits:** nothing recorded on the course for a number of days (to start: 14).

Each alert shows its evidence. The course's teaching staff are told how many new alerts there are; a
person acknowledges each, acts on it (usually by writing to the student in Messages, which is recorded with
the alert) or dismisses it with a reason. Nothing is decided or sent to the student by the system, and the
student never sees an alert as a label. The same evidence never raises a second alert, so a dismissal
stands. Alerts are part of the student's record: an administrator or the DPO includes them in the copy
produced for a request.

## Reports that leave a course (items 6.03, 6.04, 6.06)

Reports for heads of department, the Registrar, HR and the Ministry hide every total about fewer than
`REPORT_MIN_GROUP` (5) people, and one more group where a single hidden one could be worked out from the
total. Exports are CSV files whose cells cannot start a formula, and each view and export is audited.
