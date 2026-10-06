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
| Opening an outside tool (LTI launch): which tool, which course, whether names or emails were sent | Each launch | Audit log | Administrators, the auditor | With the audit log |
| A score an outside tool posts, and a tool reading a class list | Each time | Tool scores, audit log | The student, the course's teaching staff | With the marks; the audit log |
| A question to the AI study helper: when, by whom, whether answered, which items were the sources (never the question or the answer) | Each question | AI exchanges | The system | 1 year, removed nightly (rule `ai-exchanges`) |
| An AI draft for a lecturer, and the record it was saved as | Each draft | AI exchanges, audit log ("AI-drafted") | Administrators, the auditor | Drafts 1 year; the audit entry with the audit log |

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
