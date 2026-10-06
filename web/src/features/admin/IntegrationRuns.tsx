import { useState } from "react";
import type { Paginated } from "../../api/types";
import type { IntegrationRun } from "../../api/types-staff";
import { dmyTime, plural } from "../../app/format";
import { rows, useData } from "./data";
import { Said, Section } from "./kit";

const KINDS: [string, string][] = [
  ["", "Every kind"],
  ["training_push", "Training completions to the HRMS"],
  ["marks_push", "Coursework totals to the SRMS"],
  ["staff_sync", "Staff records from the HRMS"],
  ["requirement_sync", "Required training from the HRMS"],
];

/** Integration runs (item 1.23): each push to and pull from the HRMS and the SRMS, newest first, with every row refused. */
export function IntegrationRuns() {
  const [kind, setKind] = useState("");
  const [failedOnly, setFailedOnly] = useState(false);
  const query = new URLSearchParams([...(kind ? [["kind", kind]] : []), ...(failedOnly ? [["failed", "true"]] : [])]).toString();
  const { data, error } = useData<Paginated<IntegrationRun>>(`/integration-runs/${query ? `?${query}` : ""}`, "Could not load the runs.");
  const runs = data ? rows(data) : null;

  return (
    <Section title="Runs" intro="A row the other system refused is named here; the rest of the run carries on, and what was not sent goes on the next run.">
      <div className="filters">
        <label>
          Kind
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label className="inline">
          <input type="checkbox" checked={failedOnly} onChange={(e) => setFailedOnly(e.target.checked)} /> Only runs with failures
        </label>
      </div>
      <Said error={error} />
      {runs === null && !error && <p className="loading">Loading…</p>}
      {runs !== null && runs.length === 0 && <p className="muted">No runs match.</p>}
      {runs !== null && runs.length > 0 && (
        <ul className="rows flush" aria-label="Integration runs">
          {runs.map((run) => {
            const trouble = run.failed > 0 || run.stopped;
            return (
              <li key={run.id}>
                <details className="run">
                  <summary>
                    <span className="strong">{run.kind_name}</span>
                    <span className="small muted">
                      {dmyTime(run.started_at)} · {run.trigger}
                    </span>
                    <span className={trouble ? "chip chip-overdue" : "chip chip-done"}>
                      {run.stopped ? "Stopped" : `${run.ok} sent, ${run.failed} refused`}
                    </span>
                  </summary>
                  {run.stopped && <p className="error">Stopped: {run.stopped}</p>}
                  {!run.finished_at && <p className="muted">Still running, or it ended without finishing.</p>}
                  {run.errors.length === 0 ? (
                    <p className="muted">Nothing was refused.</p>
                  ) : (
                    <ul className="rows flush" aria-label={`Refused in run ${run.id}`}>
                      {run.errors.map((row, at) => (
                        <li key={at}>
                          <strong>{row.ref}</strong> <span className="muted small">{row.code}</span>
                          <br />
                          {row.detail}
                        </li>
                      ))}
                    </ul>
                  )}
                  {run.failed > run.errors.length && <p className="muted small">The first {plural(run.errors.length, "row is", "rows are")} listed.</p>}
                </details>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}
