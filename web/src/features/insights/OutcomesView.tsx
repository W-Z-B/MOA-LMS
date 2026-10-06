import { useState, type FormEvent } from "react";
import { errorMessage, post, remove } from "../../api/client";
import type { EvidenceChoices, SiteOutcome, SiteOutcomes, Standings } from "../../api/types-insights";
import { Waiting } from "./shared";
import { standingText, useLoad } from "./words";

/**
 * Learning outcomes (item 3.11): the course's outcomes from the SRMS course outline, or the site's own while the
 * SRMS has none; the evidence linked to each (assignments, quiz questions, rubric criteria); and each student's
 * standing on each.
 */
export function OutcomesView({ siteId }: { siteId: number }) {
  const outcomes = useLoad<SiteOutcomes>(`/sites/${siteId}/outcomes/`, "Could not load the outcomes.");
  const standings = useLoad<Standings>(`/sites/${siteId}/outcome-standings/`, "Could not load the standings.");
  const choices = useLoad<EvidenceChoices>(`/sites/${siteId}/outcome-evidence/`, "Could not load what can be linked.");
  const [error, setError] = useState<string | null>(null);
  const data = outcomes.data;
  if (!data) return <Waiting error={outcomes.error} />;

  function changed() {
    outcomes.reload();
    standings.reload();
  }

  async function act(work: () => Promise<unknown>) {
    setError(null);
    try {
      await work();
      changed();
    } catch (err) {
      setError(errorMessage(err, "That did not go through."));
    }
  }

  return (
    <>
      <p className="muted">
        {data.from_srms
          ? `These outcomes come from the SRMS course outline for ${data.course_code}. The Registry changes them there.`
          : data.course_code
            ? `The SRMS has no outcomes for ${data.course_code} yet, so this course may have its own.`
            : "This course is not linked to an SRMS course outline, so it may have outcomes of its own."}
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {data.outcomes.length === 0 && <p className="muted">No outcomes yet.</p>}
      <ul className="rows flush outcome-list" aria-label="Learning outcomes">
        {data.outcomes.map((o) => (
          <OutcomeRow key={o.id} siteId={siteId} outcome={o} choices={choices.data} act={act} />
        ))}
      </ul>
      {data.may_add && <AddOutcome siteId={siteId} onAdded={changed} />}

      <h2 id="standings">Standing of each student</h2>
      {standings.data ? <StandingTable data={standings.data} /> : <Waiting error={standings.error} />}
    </>
  );
}

function OutcomeRow({
  siteId,
  outcome,
  choices,
  act,
}: {
  siteId: number;
  outcome: SiteOutcome;
  choices: EvidenceChoices | null;
  act: (work: () => Promise<unknown>) => Promise<void>;
}) {
  const [chosen, setChosen] = useState("");
  const pick = `evidence-${outcome.id}`;
  return (
    <li>
      <p className="outcome-text">
        <strong>{outcome.code}</strong> {outcome.text}
        {outcome.source === "local" && <span className="chip">This course's own</span>}
      </p>
      {outcome.links.length === 0 ? (
        <p className="muted small">No evidence linked yet.</p>
      ) : (
        <ul className="plain small" aria-label={`Evidence for ${outcome.code}`}>
          {outcome.links.map((link) => (
            <li key={link.id}>
              {link.title}{" "}
              <button type="button" className="link" onClick={() => act(() => remove(`/outcome-links/${link.id}/`))} aria-label={`Unlink ${link.title} from ${outcome.code}`}>
                Unlink
              </button>
            </li>
          ))}
        </ul>
      )}
      {choices && (
        <form
          className="link-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!chosen) return;
            const [kind, id] = chosen.split(":");
            act(() => post(`/sites/${siteId}/outcomes/${outcome.id}/links/`, { [kind]: Number(id) })).then(() => setChosen(""));
          }}
        >
          <label htmlFor={pick} className="sr-only">
            Evidence to link to {outcome.code}
          </label>
          <select id={pick} value={chosen} onChange={(e) => setChosen(e.target.value)}>
            <option value="">Choose evidence to link…</option>
            <optgroup label="Assignments">
              {choices.assignments.map((c) => (
                <option key={`a${c.id}`} value={`assignment:${c.id}`}>
                  {c.title}
                </option>
              ))}
            </optgroup>
            <optgroup label="Quiz questions">
              {choices.questions.map((c) => (
                <option key={`q${c.id}`} value={`question:${c.id}`}>
                  {c.title}
                </option>
              ))}
            </optgroup>
            <optgroup label="Rubric criteria">
              {choices.criteria.map((c) => (
                <option key={`c${c.id}`} value={`criterion:${c.id}`}>
                  {c.title}
                </option>
              ))}
            </optgroup>
          </select>
          <button type="submit" className="secondary" disabled={!chosen}>
            Link
          </button>
          {outcome.source === "local" && (
            <button type="button" className="secondary danger-text" onClick={() => act(() => remove(`/outcomes/${outcome.id}/`))}>
              Remove outcome
            </button>
          )}
        </form>
      )}
    </li>
  );
}

function AddOutcome({ siteId, onAdded }: { siteId: number; onAdded: () => void }) {
  const [code, setCode] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await post(`/sites/${siteId}/outcomes/`, { code, text });
      setCode("");
      setText("");
      onAdded();
    } catch (err) {
      setError(errorMessage(err, "Could not add the outcome."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={add} aria-label="Add an outcome">
      <h3>Add an outcome of this course's own</h3>
      <label>
        Code
        <input value={code} onChange={(e) => setCode(e.target.value)} maxLength={20} required />
      </label>
      <label>
        What the student can do
        <textarea value={text} onChange={(e) => setText(e.target.value)} required />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">Add outcome</button>
      </div>
    </form>
  );
}

function StandingTable({ data }: { data: Standings }) {
  if (data.outcomes.length === 0 || data.students.length === 0) return <p className="muted">Nothing to show yet.</p>;
  return (
    <>
      <div className="scroll-x" tabIndex={0} role="region" aria-labelledby="standings">
        <table>
          <thead>
            <tr>
              <th>Student</th>
              {data.outcomes.map((o) => (
                <th key={o.id} title={o.text}>
                  {o.code}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.students.map((s) => (
              <tr key={s.person_id}>
                <td>
                  {s.student_no} {s.name}
                </td>
                {data.outcomes.map((o) => {
                  const cell = s.outcomes[String(o.id)];
                  return (
                    <td key={o.id} className={cell?.standing === "not_yet" ? "standing-not-yet" : undefined}>
                      {cell ? standingText(cell.standing, cell.percent) : ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Met at {data.met_percent}% or more of the evidence: assignment marks before any late penalty, the latest marked answer to
        a question, and the points on a rubric criterion. A guide for you, not a decision.
      </p>
    </>
  );
}
