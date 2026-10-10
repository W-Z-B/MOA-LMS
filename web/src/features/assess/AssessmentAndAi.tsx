import "./assess.css";

/**
 * Guidance for lecturers on assessment in the age of AI (item 6.13; decisions D4 and D5, ADRs 0006, 0007 and
 * 0045). The same words as docs/guides/assessment-and-ai.md: change both together.
 */
export default function AssessmentAndAi() {
  return (
    <article className="guide stack" aria-labelledby="guide-title">
      <div className="page-head">
        <h1 id="guide-title">Assessment and AI: guidance for lecturers</h1>
      </div>
      <p className="lead">
        Tools that write fluent text on request are free and on every phone. A piece of written work handed in from home can no longer show, on its own,
        what a student knows. This page says how GSA assesses fairly anyway, what the LMS does and does not do, and how to read a similarity report.
      </p>

      <section aria-labelledby="lanes">
        <h2 id="lanes">The two-lane approach</h2>
        <p>
          <strong>Lane 1, the secure lane:</strong> assessment done where you can see the student do the work.
        </p>
        <ul>
          <li>Practicals and field tasks observed against a checklist (Practicals in the LMS).</li>
          <li>Oral questions, short vivas and presentations with questions afterwards.</li>
          <li>Tests sat in the room: online in the lab, or on paper (a quiz's On paper part).</li>
          <li>The logbook signed off by a supervisor who saw the work.</li>
        </ul>
        <p>
          What a student shows in Lane 1 is theirs, and at an agricultural school most of what matters can be seen: handling animals, taking soil
          samples, calibrating a sprayer, keeping field records. <strong>The marks that decide whether a student passes should come mainly from Lane 1.</strong>
        </p>
        <p>
          <strong>Lane 2, the open lane:</strong> work done in the student's own time, such as reports, essays, projects and reflections. Students may use AI
          tools in the ways the assignment allows, and say what they used. Lane 2 is for practice, feedback and learning to use tools well: mark it for the
          thinking you asked for, and expect tools to have been used.
        </p>
      </section>

      <section aria-labelledby="design">
        <h2 id="design">Designing for each lane</h2>
        <ul>
          <li>Say in each assignment's instructions which lane it is in and what use of AI is allowed: none, for ideas and checking only, or freely with a note of how.</li>
          <li>For written work, keep "Students accept the academic integrity statement with each hand-in" ticked: they confirm the work is theirs and say which tools they used.</li>
          <li>Tie written work to something only your students have: their own plot, the farm's records, data from a practical, a photograph they took.</li>
          <li>Ask for the working, not only the answer: field notes, drafts, photographs of each stage.</li>
          <li>Follow a written piece with a five-minute conversation: ask the student to explain a choice. It tells you more than any software.</li>
          <li>Use peer review for drafts: students learn by judging work against the rubric, and you see who understands it.</li>
          <li>Where a written test must count, hold it in the room, in the lab or on paper; a paper quiz is marked and counted like the online one.</li>
        </ul>
      </section>

      <section aria-labelledby="declared">
        <h2 id="declared">Declared AI use</h2>
        <p>
          Students are told what each assignment allows and to say what they used, for what and how. "I used a chat assistant to suggest headings, then wrote
          each section myself" is a good declaration. A declared, allowed use is never misconduct. An undeclared use where the assignment forbids it is
          handled like any other breach of the integrity statement: by a person, with the student heard.
        </p>
      </section>

      <section aria-labelledby="no-detector">
        <h2 id="no-detector">Why there is no AI detector</h2>
        <p>GSA decided not to use any tool that claims to tell whether a person or a machine wrote a text.</p>
        <ul>
          <li>They are wrong often enough to harm students: they flag writers whose first language is not English, writers with a plain style, and work tidied by spelling tools.</li>
          <li>Rewording fools them, so they catch the careless and miss the deliberate.</li>
          <li>Their number looks like evidence but cannot be checked or explained, and the Data Protection Act 2023 gives people the right to have a decision about them reviewed by a person.</li>
          <li>Most send students' work to a company abroad, a transfer of personal data out of Guyana.</li>
        </ul>
        <p>Never paste a student's work into an outside detector.</p>
      </section>

      <section aria-labelledby="similarity">
        <h2 id="similarity">The similarity check, and how to read it</h2>
        <p>
          Each piece of work handed in is compared, on GSA's own server, with every other GSA submission, past and present. The report is beside the mark
          on the marking screen, for the course's teaching staff only; students never see it.
        </p>
        <ul>
          <li><strong>Overall overlap:</strong> the share of the work's words found, in runs of eight words or more, in some other GSA submission.</li>
          <li><strong>Matching passages</strong> side by side: this work, and the other work.</li>
          <li><strong>Who:</strong> the other work is named only if you teach its course too; otherwise it says "Another GSA submission" and the year.</li>
          <li><strong>Left out:</strong> passages in quotation marks, and the wording of the assignment's own instructions.</li>
          <li><strong>Not found:</strong> copying from the web, books or other institutions, reworded copying, and photographs or scans of handwriting.</li>
        </ul>
        <p>
          <strong>Overlap is evidence for a person to judge, not a verdict.</strong> Text matches for good reasons: a shared source, set phrases of the subject,
          a method sheet everyone was given, group work the course allows, or the student's own earlier work. One long passage identical to a classmate's
          work this term is worth a conversation; a high figure made of standard wording means nothing.
        </p>
        <ol>
          <li>Read the passages yourself and decide whether they matter.</li>
          <li>Talk to the student; ask them to explain their work and how it was written.</li>
          <li>If you still think there is misconduct, follow GSA's procedure. The report goes with your referral as evidence, never as the whole case.</li>
          <li>Never name another student to a student, and never put the report in feedback.</li>
        </ol>
      </section>

      <p className="muted small">Questions about a case: the course administrator. About the similarity check itself: the LMS administrator.</p>
    </article>
  );
}
