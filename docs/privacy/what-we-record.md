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
| The words of each hand-in, its fingerprints and what it shares with other GSA work (item 3.20) | Each hand-in | Similarity tables, on GSA's server | The course's teaching staff; the other work named only to staff of both courses | With the submission: deleted with it |
| Viewing or re-running a similarity report | Each time | Audit log | Administrators, the auditor | With the audit log |
| Peer reviews written: rubric scores and comment (item 4.13) | Each review | Peer reviews, audit log | The reviewer; the student reviewed once released, without the reviewer's name; the teaching staff | With the submission |
| Paper quiz answers keyed in (item 3.24) | Each answer sheet | Quiz attempts, audit log | The student as the quiz's review options allow, the teaching staff | With quiz attempts |
| Registration for an open short course: name, email, network address (item 5.07, when GSA turns it on) | Each request | Open registrations | The system | Unconfirmed: deleted when the link expires (48 hours); confirmed: with the account |

## What the LMS does not record

- How long anyone spends on a page, which pages or materials they open (other than downloads), or how they
  move through a course.
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
