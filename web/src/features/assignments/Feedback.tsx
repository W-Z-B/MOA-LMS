import type { FeedbackFile, Rubric, RubricScore } from "../../api/types-marking";
import { fileSize, plainMark } from "./words";
import "../marking/marking.css";

/** Feedback files and recordings returned with the mark (item 2.24): a recording plays in the page. */
export function FeedbackList({ files, onRemove }: { files: FeedbackFile[]; onRemove?: (file: FeedbackFile) => void }) {
  if (files.length === 0) return null;
  return (
    <ul className="plain feedback-files" aria-label="Feedback files">
      {files.map((f) => (
        <li key={f.id}>
          {f.is_audio ? (
            <>
              <span className="small strong">Spoken feedback: {f.filename}</span>
              <audio controls preload="none" src={f.download_url} aria-label={`Spoken feedback ${f.filename}`} />
            </>
          ) : (
            <a href={f.download_url} className="file-link">
              {f.filename} ({fileSize(f.size)})
            </a>
          )}
          {onRemove && (
            <button type="button" className="link small" onClick={() => onRemove(f)}>
              Take back {f.filename}
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

const KIND_WORDS = { scored: "Rubric", descriptive: "Rubric (descriptions only)", guide: "Marking guide" } as const;

/**
 * A rubric as students see it with the assignment (item 3.09), and, once marked, the level chosen for each
 * criterion and the marker's comment. A marking guide shows each criterion's maximum and the points given.
 */
export function RubricView({ rubric, scores = [] }: { rubric: Rubric; scores?: RubricScore[] }) {
  const byCriterion = new Map(scores.map((s) => [s.criterion, s]));
  return (
    <details className="rubric-view" open={scores.length > 0}>
      <summary>
        {KIND_WORDS[rubric.kind]}: {rubric.title}
      </summary>
      {rubric.description && <p className="muted small">{rubric.description}</p>}
      <ul className="plain">
        {rubric.criteria.map((c) => {
          const given = c.id !== undefined ? byCriterion.get(c.id) : undefined;
          return (
            <li key={c.id ?? c.title} className="criterion">
              <strong>{c.title}</strong>
              {rubric.kind === "guide" && <span className="muted small"> (up to {plainMark(c.max_points)})</span>}
              {c.description && <p className="muted small">{c.description}</p>}
              {rubric.kind === "guide" ? (
                given && <p className="small">Given: {plainMark(given.points)}</p>
              ) : (
                <ul className="levels">
                  {c.levels.map((l) => {
                    const chosen = given?.level === l.id;
                    return (
                      <li key={l.id ?? l.description} className={chosen ? "level chosen" : "level"}>
                        {rubric.kind === "scored" && <span className="points">{plainMark(l.points)}</span>}
                        <span>{l.description}</span>
                        {chosen && <span className="sr-only"> (chosen)</span>}
                      </li>
                    );
                  })}
                </ul>
              )}
              {given?.comment && <p className="small">Comment: {given.comment}</p>}
            </li>
          );
        })}
      </ul>
    </details>
  );
}
