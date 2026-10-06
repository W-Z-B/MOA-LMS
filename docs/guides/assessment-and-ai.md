# Assessment in the age of AI: guidance for lecturers

Item 6.13. Decisions behind it: D4 ([ADR 0006](../adr/0006-academic-integrity.md), [ADR 0021](../adr/0021-similarity-check-method.md))
and D5 ([ADR 0007](../adr/0007-ai-assistance.md)). The same guidance is in the LMS under
**Help: Assessment and AI** (`web/src/features/assess/AssessmentAndAi.tsx`, at `#/help/assessment-and-ai`); change both together.

Tools that write fluent text on request are free and on every phone. A piece of written work handed in
from home can no longer show, on its own, what a student knows. This guide says how GSA assesses fairly
anyway, what the LMS does and does not do, and how to read a similarity report.

## The two-lane approach

Think of every assessment as belonging to one of two lanes.

**Lane 1: the secure lane.** Assessment done where you can see the student do the work:

- practicals and field tasks observed against a checklist (Practicals in the LMS);
- oral questions, short vivas and presentations with questions afterwards;
- tests sat in the room, online in the lab or on paper (paper quizzes in the LMS);
- the logbook signed off by a supervisor who saw the work.

What a student shows in Lane 1 is theirs. At an agricultural school most of what matters can be seen:
handling animals, taking soil samples, calibrating a sprayer, keeping records in the field. **The marks
that decide whether a student passes a course should come mainly from Lane 1.**

**Lane 2: the open lane.** Work done in the student's own time: reports, essays, projects, reflections.
Students may use AI tools in Lane 2 in the ways the assignment allows, and they say what they used. Lane 2
is where students practise, get feedback and learn to use tools well. Mark it for the thinking you asked
for, and expect tools to have been used.

### Designing for each lane

- Say in each assignment's instructions which lane it is in, and what use of AI is allowed: none, for
  ideas and checking only, or freely with a note of how.
- Keep the academic integrity statement on for written work (the assignment's setting "Students accept
  the academic integrity statement with each hand-in"). The student confirms the work is theirs and says which tools they used and how.
- Tie written work to something only your students have: their own field plot, the farm's own records,
  data they collected in a practical, a visit to a named farm, a photograph they took.
- Ask for the working, not only the answer: field notes, drafts, photographs of each stage.
- Follow a written piece with a short conversation. Five minutes asking a student to explain a choice in
  their report tells you more than any software. Record it as an oral in the gradebook if it counts.
- Use peer review for drafts (the assignment's peer review option): students learn by judging others'
  work against the rubric, and you see who understands the rubric.
- Where a written test must count, hold it in the room: in the computer lab as a quiz, or on paper with
  the quiz's On paper part (print it from the bank, key the answers in, and it is marked and counted like the
  online quiz).

## Declared AI use

Students are told:

- what each assignment allows (the instructions say);
- to say what they used, for what, and how: "I used a chat assistant to suggest headings, then wrote
  each section myself" is a good declaration;
- that a declared, allowed use is never misconduct; an undeclared use where the assignment forbids it is
  handled like any other breach of the integrity statement, by a person, with the student heard.

## Why there is no AI detector

GSA decided not to use any tool that claims to tell whether a person or a machine wrote a text (ADR 0006).

- Such tools are wrong often enough to harm students. They flag writers whose first language is not
  English, writers who use a simple, plain style, and work that was edited with spelling and grammar
  tools. A false accusation does lasting harm, and it falls hardest on the students least able to argue.
- They are easily fooled by rewording, so they catch the careless and miss the deliberate.
- They give a number that looks like evidence but cannot be checked or explained, and the Data
  Protection Act 2023 gives people the right to have a decision about them reviewed by a person.
- Most send students' work to a company abroad, which is a transfer of personal data out of Guyana.

The LMS therefore never scores work for "AI writing", and no one at GSA should paste students' work into
an outside detector.

## The similarity check, and how to read it

Each piece of work handed in is compared, on GSA's own server, with every other GSA submission, past and
present (item 3.20). The report is for the course's teaching staff only; students never see it.

- **Overall overlap** is the share of the work's words that also appear, in runs of eight words or more,
  in some other GSA submission.
- **Matching passages** are shown side by side: this work on one side, the other work on the other.
- **Who the other work belongs to** is shown only if you also teach on that course. Otherwise the report
  says "Another GSA submission" and the year. Ask the lecturer of that course if you need to know more.
- **Left out:** passages in quotation marks (the student is saying they are someone else's words) and
  the wording of the assignment's own instructions.
- **Not found:** copying from the web, from books or from other institutions (only GSA's work is
  compared), reworded copying, and photographs or scans of handwriting, which are not read.

Overlap is evidence for a person to judge, not a verdict. There are good reasons for text to match:
a shared source quoted without quotation marks, set phrases of the subject ("integrated pest
management"), a method sheet everyone was given, group work the course allows, or the student's own
earlier work. A high number with matches only to standard wording means nothing; a modest number with one
long passage identical to a classmate's work this term is worth a conversation.

When a report worries you:

1. Read the passages yourself. Decide whether they matter.
2. Talk to the student. Ask them to explain their work and how it was written. Note what they say.
3. If you still think there is misconduct, follow GSA's academic misconduct procedure. The report can
   go with your referral as evidence; it is never the whole case.
4. Never mention another student's name to a student, and never put the report in feedback.

## Questions

Ask the course administrator, or the academic board's integrity lead, about a case. Ask the LMS
administrator about the similarity check itself.
