import { useState, type FormEvent } from "react";
import { errorMessage, patch, post } from "../../api/client";
import type { Criterion, Rubric, RubricKind } from "../../api/types-marking";
import { plainMark } from "../assignments/words";

interface Props {
  /** The site the rubric belongs to; null for the GSA library. */
  siteId: number | null;
  rubric?: Rubric;
  onSaved: (saved: Rubric) => void;
  onCancel: () => void;
}

const blankCriterion = (kind: RubricKind): Criterion => ({
  title: "",
  description: "",
  max_points: kind === "guide" ? "10" : null,
  levels:
    kind === "guide"
      ? []
      : [
          { points: "0", description: "" },
          { points: "5", description: "" },
          { points: "10", description: "" },
        ],
});

/**
 * Criteria and levels (item 3.09), or criteria with a maximum for a marking guide (item 3.10). Levels have
 * points in a scored rubric and descriptions only in a descriptive one.
 */
export function RubricEditor({ siteId, rubric, onSaved, onCancel }: Props) {
  const [title, setTitle] = useState(rubric?.title ?? "");
  const [description, setDescription] = useState(rubric?.description ?? "");
  const [kind, setKind] = useState<RubricKind>(rubric?.kind ?? "scored");
  const [criteria, setCriteria] = useState<Criterion[]>(
    rubric?.criteria.map((c) => ({ ...c, max_points: c.max_points && plainMark(c.max_points), levels: c.levels.map((l) => ({ ...l, points: plainMark(l.points) })) })) ?? [
      blankCriterion("scored"),
    ],
  );
  const [error, setError] = useState<string | null>(null);

  const change = (index: number, update: Partial<Criterion>) => setCriteria(criteria.map((c, i) => (i === index ? { ...c, ...update } : c)));

  function changeKind(next: RubricKind) {
    setKind(next);
    setCriteria(
      criteria.map((c) => ({
        ...c,
        max_points: next === "guide" ? (c.max_points ?? "10") : null,
        levels: next === "guide" ? [] : c.levels.length ? c.levels : blankCriterion(next).levels,
      })),
    );
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const body = {
      ...(rubric ? {} : { site: siteId }),
      title,
      description,
      kind,
      criteria: criteria.map((c) => ({
        title: c.title,
        description: c.description,
        max_points: kind === "guide" ? c.max_points : null,
        levels: kind === "guide" ? [] : c.levels.map((l) => ({ points: kind === "scored" ? l.points || "0" : "0", description: l.description })),
      })),
    };
    try {
      onSaved(rubric ? await patch<Rubric>(`/rubrics/${rubric.id}/`, body) : await post<Rubric>("/rubrics/", body));
    } catch (err) {
      setError(errorMessage(err, "Could not save the rubric."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={save} aria-label={rubric ? `Change ${rubric.title}` : "New rubric"}>
      <h3>{rubric ? `Change “${rubric.title}”` : "New rubric or marking guide"}</h3>
      <div className="grid2">
        <label>
          Title
          <input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={160} />
        </label>
        <label>
          Kind
          <select value={kind} onChange={(e) => changeKind(e.target.value as RubricKind)}>
            <option value="scored">Rubric with points: the levels fill the mark</option>
            <option value="descriptive">Rubric with descriptions only: the marker gives the mark</option>
            <option value="guide">Marking guide: points up to each criterion's maximum</option>
          </select>
        </label>
        <label className="span2">
          Description (optional)
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
      </div>
      {criteria.map((c, index) => (
        <fieldset key={index}>
          <legend>Criterion {index + 1}</legend>
          <div className="stack">
            <label>
              Criterion {index + 1} title
              <input value={c.title} onChange={(e) => change(index, { title: e.target.value })} required maxLength={200} />
            </label>
            <label>
              {kind === "guide" ? "What the marker looks for" : "Description (optional)"}
              <input value={c.description} onChange={(e) => change(index, { description: e.target.value })} />
            </label>
            {kind === "guide" ? (
              <label>
                Maximum points for criterion {index + 1}
                <input type="number" min={0.5} step="0.5" value={c.max_points ?? ""} onChange={(e) => change(index, { max_points: e.target.value })} required />
              </label>
            ) : (
              <>
                {c.levels.map((l, li) => (
                  <div className="category-row" key={li}>
                    <label className="name">
                      Level {li + 1} of criterion {index + 1}
                      <input
                        value={l.description}
                        onChange={(e) => change(index, { levels: c.levels.map((x, xi) => (xi === li ? { ...x, description: e.target.value } : x)) })}
                        required
                      />
                    </label>
                    {kind === "scored" && (
                      <label>
                        Points
                        <input
                          type="number"
                          min={0}
                          step="0.5"
                          value={l.points}
                          onChange={(e) => change(index, { levels: c.levels.map((x, xi) => (xi === li ? { ...x, points: e.target.value } : x)) })}
                        />
                      </label>
                    )}
                    <button
                      type="button"
                      className="secondary"
                      disabled={c.levels.length === 1}
                      aria-label={`Remove level ${li + 1} of criterion ${index + 1}`}
                      onClick={() => change(index, { levels: c.levels.filter((_, xi) => xi !== li) })}
                    >
                      Remove
                    </button>
                  </div>
                ))}
                <div className="actions">
                  <button type="button" className="secondary" onClick={() => change(index, { levels: [...c.levels, { points: "0", description: "" }] })}>
                    Add a level
                  </button>
                </div>
              </>
            )}
            <div className="actions">
              <button type="button" className="secondary danger-text" disabled={criteria.length === 1} onClick={() => setCriteria(criteria.filter((_, i) => i !== index))}>
                Remove criterion {index + 1}
              </button>
            </div>
          </div>
        </fieldset>
      ))}
      <div className="actions">
        <button type="button" className="secondary" onClick={() => setCriteria([...criteria, blankCriterion(kind)])}>
          Add a criterion
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit">{rubric ? "Save changes" : "Save the rubric"}</button>
      </div>
    </form>
  );
}
