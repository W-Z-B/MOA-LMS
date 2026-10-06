# ADR 0046: Open short courses for farmers and extension officers

**Status:** proposed, open (decision D0: whether GSA offers open short courses). Built switched off.
**Date:** 6 October 2026.

## Context

Feature 35 of the audit asks whether the LMS should also carry short courses for farmers and extension
officers outside GSA's enrolled students (item 5.07). That widens who holds an account: people who are
neither staff in the HRMS nor students in the SRMS, who sign themselves up. It is GSA's choice whether to
offer such courses at all, so the decision belongs to D0 (the scope of the LMS). The audit records it as a
"could", if GSA chooses.

## Decision

1. The feature is built and **off**: `OPEN_COURSES_ENABLED=0` by default. While off, every open-course
   endpoint answers 404 with `open_courses_off` and the web app shows no link to it.
2. A third kind of course site, **open**, for short courses. A course administrator writes its catalogue
   entry (summary, audience, hours, places and completion rules) as for a staff-development course.
3. A **public page** lists published open sites with a catalogue entry, with the privacy notice in force.
4. **Self-registration with email confirmation.** A person gives their name and email address and accepts
   the privacy notice. Nothing is made until they follow the emailed link, within `OPEN_CONFIRM_HOURS`
   (48), and choose a password; their email address is their username. Only a fingerprint of the link is
   kept, and unconfirmed requests are deleted when the link expires. The answer is the same whether or not
   an address already has an account.
5. **A separate learner role** (`learner`; person kind `learner`, numbers OL000001 ...). A learner sees open
   sites only. `courses.access` refuses every academic or staff-development site to a learner, even if a
   membership or role is given by mistake. No authenticator code is asked of learners: they cannot mark
   or change results.
6. **Rate limits:** `OPEN_REGISTRATIONS_PER_ADDRESS` (5) an hour from one network address, three a day for
   one email address, and a ceiling of 30 requests a minute on the public pages.
7. **Completion certificates** come from the staff-development completion rules and certificate templates
   (items 5.03, 5.08): completing an open course issues a certificate the public page can check.
   Completions of open courses are never sent to the HRMS.

## What GSA needs to decide

- Whether to offer open short courses at all (D0); if so, who runs them and which courses.
- Whether learners must be adults (the Data Protection Act 2023 treats children's data with more care);
  the registration page would then ask for a confirmation of age.
- The retention period for learner accounts and their work, to add to the retention schedule.
- The email address the registration mail is sent from (`SMTP_FROM`).

## Consequences

- Turning it on is a setting, not a release. Turning it off again hides the catalogue and registration;
  existing learners can still sign in and finish their courses.
- The privacy notice must say that the LMS holds learners' names and email addresses (docs/privacy).
