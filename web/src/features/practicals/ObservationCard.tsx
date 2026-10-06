import type { ReactNode } from "react";
import type { Observation } from "../../api/types-practicals";
import { dmyTime } from "../../app/format";
import { Gallery } from "./FieldWidgets";

/** One observed attempt: every criterion's result, the comments and the photos. Read by the student once
 * released, and by teaching staff before and after. */
export function ObservationCard({ observation: o, children }: { observation: Observation; children?: ReactNode }) {
  return (
    <article className="module observation" aria-label={`${o.task_title}, attempt ${o.attempt}`}>
      <div className="panel-head">
        <div>
          <h3>
            {o.task_title}: attempt {o.attempt}
          </h3>
          <p className="muted small">
            {o.student_name} · observed {dmyTime(o.observed_at)} by {o.assessor_name}
            {o.location_text && ` · ${o.location_text}`}
          </p>
        </div>
        <p className="strong">
          {o.score.earned} of {o.score.possible}
        </p>
      </div>
      <p className={o.critical_passed ? "notice good" : "notice bad"}>
        {o.critical_passed ? "Every critical criterion met." : "A critical criterion was not met."}
        {!o.is_released && " Not yet released to the student."}
      </p>
      <ul className="plain results">
        {o.results.map((r) => (
          <li key={r.criterion} className={r.passed ? "result met" : "result not-met"}>
            <span className="result-mark" aria-hidden="true">
              {r.passed ? "✓" : "✗"}
            </span>
            <span>
              <span className="sr-only">{r.passed ? "Met: " : "Not met: "}</span>
              {r.text}
              {r.is_critical && <span className="pill critical">Critical</span>}
              {r.kind === "scored" && (
                <span className="muted">
                  {" "}
                  · {r.score} of {r.max_score}
                </span>
              )}
              {r.comment && <span className="result-comment">{r.comment}</span>}
            </span>
          </li>
        ))}
      </ul>
      {o.comments && <p className="pre">{o.comments}</p>}
      <Gallery photos={o.photos} label={`Photos of attempt ${o.attempt}`} />
      {children}
    </article>
  );
}
