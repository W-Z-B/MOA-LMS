# ADR 0004: Continue the GSA LMS, with Moodle as the reference

**Status:** accepted on the recommended answer, 5 October 2026 (decision D15); GSA may revise.
**Date:** 5 October 2026.

## Context

The region runs Moodle: the University of Guyana and every UWI campus use it, and a Moodle site for GSA
appears in search results (it did not answer when checked on 5 October 2026). Moodle is free, complete, and
lecturers may already know it. Its phone app works offline better than any rival.

But Moodle is GPL and written in PHP. Canvas and Open edX are AGPL. Only Sakai, among the major systems, is
under a permissive licence. Adopting Moodle would break the licence policy every GSA system follows
([ADR 0002](0002-licence-policy.md)) and the one-family rule with the HRMS and the SRMS: the integration with
both, the shared security skeleton and the phone-first frame would all have to be rebuilt as Moodle plugins.

## Decision

1. Continue the GSA LMS on the ecosystem stack ([ADR 0001](0001-stack-selection.md)).
2. Use Moodle as the **reference for depth**: quiz question types, competencies, attendance, offline rules
   and privacy tools. Lecturers who know Moodle should find what they expect.
3. Use Moodle as a **source**: its questions (Moodle XML, GIFT) and, later, whole courses (Common Cartridge)
   import into the LMS (items 3.07, 6.08).
4. No Moodle code is copied into the LMS; it is read for behaviour only.

## Consequences

- The LMS keeps one owner per fact with the HRMS and the SRMS, the same security controls, and one team.
- Breadth on day one is smaller than Moodle's; the three releases ([ADR 0003](0003-scope-and-releases.md))
  close the gap, quizzes first ([ADR 0005](0005-quizzes-built-in.md)).
- If GSA values Moodle's breadth on day one above these, adopting it remains a reasonable choice. It should
  be made now, not after Release 1 (item 0.25).
