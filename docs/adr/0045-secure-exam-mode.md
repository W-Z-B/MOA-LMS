# ADR 0045: Secure exam mode is a deterrent and a log, not a lockdown

**Status:** accepted on the recommended answer, 10 October 2026, as the web-realistic reading of
[ADR 0006](0006-academic-integrity.md) for a timed sitting (item 3.25).
**Date:** 10 October 2026.

## Context

The ecosystem gap analysis (L-W02, L-M02) asks for exam integrity during the sitting itself, distinct from
`similarity`'s post-submission plagiarism check (item 3.20). ADR 0006 already ruled out webcam proctoring,
biometric collection and AI-writing detectors for this school. A true lockdown browser -- blocking
alt-tab, blocking other applications, forcing full-screen -- needs a native app or a browser extension
installed on the student's device; nothing a web page serves can do that, in any browser, on any device.
That rules out a large part of what "secure exam" means at a commercial proctoring vendor.

What a web page can do, honestly:

- Enforce a single attempt and a server-side deadline (the time limit, attempts and window the quiz
  already has -- items 3.01 to 3.03 -- just made non-negotiable for this quiz).
- Notice, and tell the server, when the browser tab loses focus or visibility, or when someone tries to
  copy, paste or open the right-click menu on the page -- and turn those attempts' default browser action
  off as a deterrent.
- Keep a plain timeline of what it noticed, for the course's teaching staff to read afterwards.

None of this stops a determined person: another device beside the keyboard, a second browser window, or
simply closing the laptop and asking someone are all outside what any web page can see. The build says so
in the student-facing notice and in the lecturer guidance, rather than selling a guarantee it cannot keep.

## Decision

1. **Extend `quizzes.Quiz` and its existing attempt machinery, not a new app.** A secure exam is a quiz
   (`Quiz.is_secure_exam`), because every piece it needs -- time limits, a server-side deadline
   (`Attempt.deadline`, `quizzes.services.is_expired`), one-attempt enforcement, auto-submission of whatever
   was answered when time runs out, and an event log (`AttemptEvent`) -- already exists for the formative
   quiz-taking flow (items 3.01-3.08, 3.21). Building a parallel `ExamSession` concept would duplicate all
   of it and give GSA two places a quiz's timing rules could disagree. `assessments` (coursework hand-ins)
   is not touched: a secure exam is a kind of quiz, not a kind of assignment.
2. **One attempt, enforced on both ends.** `is_secure_exam=True` forces `attempts_allowed=1` in the
   serializer (mirroring how `is_practice` already forces `weight` and `attempts_allowed` to zero) and in a
   database `CheckConstraint`, so the single-attempt rule holds even if a future change to the serializer
   forgets to re-apply it. A secure exam cannot also be a practice quiz (a second constraint): the two are
   opposite settings pulling attempts in opposite directions.
3. **Default time-box behaviour: auto-submit what was answered, never discard it.** This is not new -- every
   quiz already does this (`quizzes.services.finish_if_expired` / `submit_attempt(..., auto=True)`) -- but
   it is restated here because a secure exam is exactly the case where a GSA reviewer will ask what happens
   at the deadline. The answer stays the same as any other timed quiz: whatever was saved is marked and
   counted; nothing already answered is thrown away for running out of time.
4. **What counts as a loggable integrity event.** Five kinds, added to the existing `AttemptEvent.Kind`
   rather than a new model: `focus_lost`, `focus_resumed`, `copy_attempted`, `paste_attempted`,
   `context_menu_blocked`. `focus_lost`/`focus_resumed` fire from either a `blur`/`focus` pair or a
   `visibilitychange` (tab hidden/shown) -- deduplicated client-side to one pair per excursion, since a
   single alt-tab can trigger both browser signals and a log that counts each real excursion once is more
   readable than one that counts browser events. Marking, release and the ordinary answer/submission events
   are deliberately **not** integrity events: they already have their own event log and audience
   (`AttemptViewSet.events`); mixing an accusatory signal into that administrative log would blur the two.
   Events are reported only while a secure exam attempt is in progress (`quizzes.services.
   record_integrity_event`); an ordinary quiz's browser never reports anything, and nothing is kept once the
   attempt is submitted. A ceiling (`QUIZ_INTEGRITY_EVENT_CAP`, 500 by default) stops a stuck or malicious
   page script from writing an unbounded number of rows; no student sitting an exam normally approaches it.
5. **Framing: a timeline, not a verdict.** Every label in the log describes what the page observed
   ("Left the quiz window or tab"), not what it means. The integrity log's own heading and the on-screen
   notice say plainly that this is a deterrent on a web page, not a lockdown browser or webcam proctoring,
   and that it cannot stop someone determined to get around it (copying by hand, a second device, another
   person in the room). This matches ADR 0007: no decision about a student is made by the system -- a
   lecturer reads the timeline alongside the student's answers and judges, as ADR 0006 already settled for
   the similarity check.
6. **Who reads the log: the site's teaching staff, same as the attempt's full event log.** This repo has no
   academic-integrity-officer role distinct from a course's teaching staff (`iam.Role` lists
   administrator, course administrator, lecturer, student, auditor, DPO, head of department and registrar --
   verified in this change; none of those is integrity-specific). The default is therefore the same
   audience the existing `AttemptViewSet.events` action already allows (`courses.access.can_teach`, which
   includes system administrators and course administrators as well as the site's own teaching staff), not
   a new permission. If GSA later creates an academic-integrity role, extending the check is a one-line
   change to `AttemptViewSet.integrity_log`'s permission, not a new table.
7. **The soft deterrent is honestly described.** Copy, paste and the right-click menu are suppressed with
   `preventDefault()` on the exam page and `user-select: none` on the question text (never on the answer
   fields themselves, which must stay selectable and editable); each attempt is also reported to the
   integrity log. The settings screen, the on-screen notice to the student and this record all say the same
   thing: this is a deterrent, not enforcement, and it is trivially bypassed by anyone who wants to (a
   screenshot, a phone camera, typing from memory). No feature here claims otherwise.

## What was deliberately not built (L-M01, L-M02, out of scope)

- **No lockdown browser, no blocking of other applications or windows.** Not possible from a web page; the
  honest alternative -- a native app or browser extension -- is out of scope for this phase.
- **No webcam proctoring, no AI-monitoring, no biometric capture.** Already ruled out by ADR 0006, for the
  same reasons (cost, consent, Guyana's Data Protection Act 2023, students who may be minors, and
  bandwidth). Nothing in this change revisits that.
- **L-W01 verified while reading `video` for this work:** the `video` app is recorded lecture video only
  (upload, convert to renditions, captions, offline copies) -- there is no live web-conferencing or
  live-session model anywhere in this repo. That confirms exam integrity cannot lean on a live-invigilation
  video call as part of its design; it also means L-M01 (live sessions) remains a separate, unbuilt gap
  this change does not touch.

## Consequences

- A secure exam is still, to every other part of the LMS (gradebook, coursework weighting, the SRMS export
  of results), an ordinary `Quiz` -- one with a flag that narrows its own attempt rules and turns on
  browser-side reporting. No other app needed to change.
- The integrity log can grow for a large class sitting a long exam; the cap bounds that, and the log is
  read per attempt, not loaded in bulk for a whole quiz.
- `similarity` keeps doing exactly what it already does (post-submission text comparison); this feature
  does not touch it, and the two are described separately in the lecturer-facing guidance so they are not
  confused with each other.
