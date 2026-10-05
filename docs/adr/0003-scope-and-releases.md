# ADR 0003: Scope and releases from the 42-feature audit

**Status:** accepted on the recommended answer, 5 October 2026 (decision D0); GSA may revise.
**Date:** 5 October 2026.

## Context

The GSA LMS Gold Standard Feature Audit (version 1.0, 5 October 2026) consolidates 55 features found across
eight leading systems into 42, and checks each against the build and against Guyana's law. Two are fully
built, nine partly, three exist only as a data outline and 28 have not been started. The Implementation
Checklist turns them into 171 numbered items in eight phases. Building all of it before anyone uses it would
delay the benefit by a year.

## Decision

1. The 42 features are the scope of the LMS.
2. They are delivered in three releases:
   - **Release 1:** hardening to the HRMS's level, the teaching core, quizzes and rubrics, the gradebook and
     the SRMS link, phone and offline reading. Aimed at the first semester after acceptance, so lecturers
     start a term with it rather than join mid-term.
   - **Release 2:** practical and competency assessment first, then forums and messages, staff development,
     certificates, packaged content and analytics.
   - **Release 3:** interoperability (LTI, Common Cartridge, xAPI), early alerts, live classes and AI
     assistance, each when Release 1 and 2 are in daily use.
3. Item numbers in the checklist are permanent; commits and pull requests cite them.

## Consequences

- Every pull request names the checklist items it delivers (`.github/pull_request_template.md`).
- The release dates follow GSA's answers to the information request (decision D9, open).
- A feature added later is a new checklist item and, if it changes scope, a new decision record.
