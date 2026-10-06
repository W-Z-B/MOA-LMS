# ADR 0005: Quizzes are built into the LMS

**Status:** accepted on the recommended answer, 5 October 2026 (decision D1); GSA may revise.
**Date:** 5 October 2026.

## Context

Quizzes are the most used assessment tool in every system studied (feature 10). Moodle is the reference:
shared, versioned question banks, a dozen question types, random questions by category, time limits,
attempts, review options and question statistics. An outside quiz tool would need its own sign-in, would
send students' answers and marks abroad, and would put a second system between the lecturer and the
gradebook. Students answer on phones over weak signal, so a dropped connection must not lose an answer.

## Decision

1. Quizzes and question banks are built into the LMS (items 3.01 to 3.06): banks per course and shared by
   department, with categories, tags and versions; the common question types; random questions, shuffled
   answers, time limits, attempts and windows; automatic marking where possible, essays to a marking queue.
2. Answers are saved as they are given, and a quiz in progress continues after reconnecting (item 3.05).
3. Questions import and export in Moodle XML, GIFT and QTI (item 3.07), so lecturers bring what they have.
4. Quiz marks join the gradebook and the weighted coursework percentage like any other assessment.

## Consequences

- No outside service, no second sign-in, and no learner data sent abroad for quizzes.
- A large piece of work in Release 1 (Phase 3); question statistics follow the first term of use.
- Quiz security relies on question pools, windows and supervised sittings, not on webcam proctoring
  ([ADR 0006](0006-academic-integrity.md)).
