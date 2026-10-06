import type { StudentProgress } from "../../api/types-insights";
import { dmy } from "../../app/format";
import { STATE_WORDS } from "../assignments/words";
import { percent, seen, standingText } from "./words";

const KIND_WORDS = { assignment: "Assignment", quiz: "Quiz", practical: "Practical", forum: "Discussion" } as const;

/**
 * One student's progress (item 6.02) and standing on each outcome (item 3.11). The student's own view is worked
 * out from released marks only; teaching staff see every mark given.
 */
export function ProgressDetail({ data, own }: { data: StudentProgress; own: boolean }) {
  const standings = data.outcomes.students[0]?.outcomes ?? {};
  const work = own ? "Your work" : "Work";
  return (
    <div className="progress-detail">
      <dl className="figures">
        <div>
          <dt>Items done</dt>
          <dd>
            {data.items_done} of {data.items_total}
            {data.items_percent != null && (
              <progress max={100} value={Number(data.items_percent)} aria-label="Items done">
                {percent(data.items_percent)}
              </progress>
            )}
          </dd>
        </div>
        <div>
          <dt>Work handed in</dt>
          <dd>{data.work_done}</dd>
        </div>
        <div>
          <dt>Missed</dt>
          <dd>{data.work_missed}</dd>
        </div>
        <div>
          <dt>Still to come</dt>
          <dd>{data.work_to_come}</dd>
        </div>
        <div>
          <dt>{own ? "Coursework so far" : "Coursework total"}</dt>
          <dd>{percent(data.coursework_percent)}</dd>
        </div>
        <div>
          <dt>Last activity on the course</dt>
          <dd>{seen(data.last_seen)}</dd>
        </div>
      </dl>
      {own && <p className="muted small">Marks count here once your lecturer releases them.</p>}

      <h3>{work}</h3>
      {data.work.length === 0 ? (
        <p className="muted">Nothing that counts towards coursework yet.</p>
      ) : (
        <ul className="rows flush" aria-label={work}>
          {data.work.map((item) => (
            <li key={`${item.kind}-${item.id}`} className="bar-row">
              <span className="bar-name">
                {item.title}
                <br />
                <span className="small muted">
                  {KIND_WORDS[item.kind]}
                  {item.due_at ? ` · due ${dmy(item.due_at)}` : ""}
                </span>
              </span>
              <span className={item.state === "zero" ? "chip chip-rejected" : "chip"}>
                {STATE_WORDS[item.state]}
                {item.state === "graded" && item.percent != null ? ` · ${percent(item.percent)}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}

      {data.outcomes.outcomes.length > 0 && (
        <>
          <h3>Learning outcomes</h3>
          <ul className="rows flush" aria-label="Learning outcomes">
            {data.outcomes.outcomes.map((o) => {
              const cell = standings[String(o.id)];
              return (
                <li key={o.id}>
                  <strong>{o.code}</strong> {o.text}
                  <br />
                  <span className="small">{cell ? standingText(cell.standing, cell.percent) : "No evidence yet"}</span>
                  {cell && cell.evidence.length > 0 && (
                    <span className="small muted"> · from {cell.evidence.map((e) => `${e.title} (${Number(e.percent)}%)`).join(", ")}</span>
                  )}
                </li>
              );
            })}
          </ul>
          <p className="muted small">An outcome is met at {data.outcomes.met_percent}% or more of its evidence, as a guide.</p>
        </>
      )}
    </div>
  );
}
