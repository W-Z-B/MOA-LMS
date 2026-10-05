# ADR 0007: What AI may be used for

**Status:** accepted on the recommended answer, 5 October 2026 (decision D5); GSA may revise.
**Date:** 5 October 2026.

## Context

Canvas, Brightspace and Blackboard now draft questions, rubrics and modules for lecturers to review, and
Brightspace answers students from the course's own material. Moodle 5 lets an institution choose its AI
provider, including a model run on its own server. Sending learner data to an outside AI service would be
a transfer of personal data outside Guyana under the Data Protection Act 2023, and some learners may be
under 18. Classes at GSA are small, so a prediction about an individual student would rest on very few
cases. The Act gives people a right to human review of automated decisions. The HRMS took the same line
in its decision D4 (HRMS ADR 0007).

## Decision

1. **Drafts for lecturers**, always reviewed before use: questions from their own material, rubric wording,
   alternative text for images (item 6.11).
2. **A study helper for students** that answers from the course's own material, shows its source, and is
   switched off during any assessment (item 6.12).
3. **Where it runs:** on a model GSA hosts; or, if an outside service is used, no student data is sent
   without GSA's written approval given after the impact assessment covers that use.
4. **Early alerts by visible rules, not prediction:** missed work, falling marks or no visits, each shown
   with its evidence to the lecturer and adviser (item 6.05). The system never decides about a student alone.

## Consequences

- AI work waits for Release 3, when Releases 1 and 2 are in daily use (feature 42 is a "could").
- Alerts can be explained to a student and checked by a person.
- Any use of an outside model on learner data is a new decision with its own impact assessment.
