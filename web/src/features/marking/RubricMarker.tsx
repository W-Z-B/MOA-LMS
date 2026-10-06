import type { Rubric, RubricScore } from "../../api/types-marking";
import { plainMark } from "../assignments/words";

interface Props {
  rubric: Rubric;
  scores: RubricScore[];
  onChange: (scores: RubricScore[]) => void;
  disabled?: boolean;
}

/**
 * Marking with a rubric or marking guide (items 3.09, 3.10), as Canvas's rubric in SpeedGrader: one level
 * chosen for each criterion (or points up to each maximum in a guide), with an optional comment. The scores
 * fill the mark; with a descriptive rubric the marker gives the mark.
 */
export function RubricMarker({ rubric, scores, onChange, disabled }: Props) {
  const score = (criterion: number) => scores.find((s) => s.criterion === criterion);
  const put = (criterion: number, change: Partial<RubricScore>) => {
    const current = score(criterion) ?? { criterion, level: null, points: null, comment: "" };
    onChange([...scores.filter((s) => s.criterion !== criterion), { ...current, ...change }]);
  };

  return (
    <div className="rubric-marker">
      {rubric.criteria.map((c) => {
        const id = c.id!;
        const given = score(id);
        return (
          <fieldset key={id} disabled={disabled}>
            <legend>
              {c.title}
              {rubric.kind === "guide" && ` (up to ${plainMark(c.max_points)})`}
            </legend>
            {c.description && <p className="muted small">{c.description}</p>}
            {rubric.kind === "guide" ? (
              <label>
                Points for {c.title}
                <input
                  type="number"
                  min={0}
                  max={Number(c.max_points)}
                  step="0.5"
                  value={given?.points ?? ""}
                  onChange={(e) => put(id, { points: e.target.value === "" ? null : e.target.value })}
                />
              </label>
            ) : (
              <div className="level-choices">
                {c.levels.map((l) => (
                  <label key={l.id} className={given?.level === l.id ? "level-choice chosen" : "level-choice"}>
                    <input
                      type="radio"
                      name={`criterion-${id}`}
                      checked={given?.level === l.id}
                      onChange={() => put(id, { level: l.id!, points: rubric.kind === "scored" ? l.points : null })}
                    />
                    <span>
                      {rubric.kind === "scored" && <strong>{plainMark(l.points)} </strong>}
                      {l.description}
                    </span>
                  </label>
                ))}
              </div>
            )}
            <label>
              Comment on {c.title} (optional)
              <input value={given?.comment ?? ""} onChange={(e) => put(id, { comment: e.target.value })} />
            </label>
          </fieldset>
        );
      })}
    </div>
  );
}
