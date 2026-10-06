# ADR 0008: The LMS takes attendance; the SRMS receives the totals

**Status:** accepted on the recommended answer, 5 October 2026 (decision D6); GSA may revise.
**Date:** 5 October 2026.

## Context

Attendance at practicals is often a condition of passing. The ecosystem architecture gives attendance to no
system. The LMS is where lecturers and students are during class, in the lab and in the field, often with a
phone and without signal. Moodle's attendance tool lets students check in by scanning a code shown in the
room and feeds the gradebook. The SRMS needs only the totals, and only for programmes that make attendance
a condition.

## Decision

1. The LMS records attendance at classes and practicals: taken by the lecturer on a phone, or by students
   scanning a code shown in the room, working without signal and sent when it returns, with the time the
   person acted (item 4.15).
2. The LMS sends attendance totals to the SRMS where a programme makes attendance a condition of passing,
   over the integration API with its own scope, as coursework totals are sent today.
3. Corrections to a recorded attendance are made by the lecturer and written to the audit log.
4. No location tracking and no biometrics: a code in the room, or the lecturer's register.

## Consequences

- One owner for attendance records (the LMS) and one for results (the SRMS), as the ecosystem's rule asks.
- The SRMS needs a receiving endpoint and a scope for attendance totals; that is SRMS work, agreed with the
  Registrar along with the attendance rules (decision D9 asks for them).
- Live class links and recordings (item 4.14) sit beside attendance on the calendar.
