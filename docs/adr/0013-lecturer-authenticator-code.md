# ADR 0013: Lecturers use an authenticator code

**Status:** accepted on the recommended answer, 5 October 2026 (decision D14); GSA may revise.
**Date:** 5 October 2026.

## Context

Today only administrators and course administrators must enter an authenticator code at sign-in
(`iam.models.Role.MFA_REQUIRED`). Lecturers mark work and release marks, and the coursework totals they
produce are sent to the SRMS, where they become part of published results. A lecturer's password alone is
therefore enough to change a student's result. The gold standard's security measure asks for an
authenticator code for every role that can change marks.

## Decision

1. From the start of Release 1, lecturers and teaching assistants who can mark must enter an authenticator
   code, as administrators and course administrators do (item 1.11).
2. Students and auditors are not required to, but may choose to.
3. The code is the same time-based code the LMS already uses (TOTP, any authenticator app), enrolled at the
   first sign-in after the rule takes effect.

## Consequences

- A lost phone locks a lecturer out until an administrator resets their authenticator; the procedure is
  written in the administrator notes before the rule is switched on.
- Lecturers are told before the term in which the rule starts, with a short guide.
- The browser journeys sign lecturers in with a code once the rule is built.
