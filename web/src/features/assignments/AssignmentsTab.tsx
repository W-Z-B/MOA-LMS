import { useCallback, useEffect, useState } from "react";
import { errorMessage, get } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { AssignmentDetail } from "../../api/types-marking";
import { dmyTime } from "../../app/format";
import { AssignmentForm } from "./AssignmentForm";
import { Extensions } from "./Extensions";
import { SubmitWork } from "./SubmitWork";
import { plainMark } from "./words";
import "../marking/marking.css";

interface Props {
  siteId: number;
  teaching: boolean;
}

type Open = { id: number; what: "work" | "change" | "extensions" } | null;

/**
 * A course's assignments (feature 9). Students open one to hand in and to read their mark. Teaching staff set
 * and change them, grant extensions, and open the marking screen; rubrics are kept on a page of their own.
 */
export function AssignmentsTab({ siteId, teaching }: Props) {
  const [rows, setRows] = useState<AssignmentDetail[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState<Open>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<AssignmentDetail>>(`/assignments/?site=${siteId}`)
      .then((r) => {
        setRows(r.results);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load assignments.")))
      .finally(() => setLoaded(true));
  }, [siteId]);

  useEffect(load, [load]);

  const toggle = (id: number, what: "work" | "change" | "extensions") =>
    setOpen(open?.id === id && open.what === what ? null : { id, what });

  return (
    <>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {teaching && (
        <div className="actions tab-actions">
          {!adding && <button onClick={() => setAdding(true)}>New assignment</button>}
          <a className="button" href={`#/sites/${siteId}/rubrics`}>
            Rubrics and marking guides
          </a>
        </div>
      )}
      {adding && (
        <AssignmentForm
          siteId={siteId}
          onCancel={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            load();
          }}
        />
      )}
      {loaded && rows.length === 0 && <p className="muted">No assignments yet.</p>}
      {rows.map((a) => {
        const mine = a.my_submission;
        return (
          <section className="module" key={a.id} aria-labelledby={`asg-h-${a.id}`}>
            <div className="panel-head">
              <div className="stacked">
                <h3 id={`asg-h-${a.id}`}>{a.title}</h3>
                <p className="muted small">
                  Due {dmyTime(a.my_due_at ?? a.due_at)} · out of {plainMark(a.max_mark)} · weight {plainMark(a.weight)}
                  {a.submissions_count !== null ? ` · ${a.submissions_count} handed in` : ""}
                </p>
                <p className="chips">
                  {!a.is_published && <span className="chip chip-draft">Draft</span>}
                  {a.is_group && <span className="chip">Group</span>}
                  {a.anonymous && <span className="chip">Anonymous marking</span>}
                  {a.rubric_detail && <span className="chip">{a.rubric_detail.kind === "guide" ? "Marking guide" : "Rubric"}</span>}
                  {!teaching && mine && !mine.mark && <span className="chip chip-submitted">Handed in</span>}
                  {!teaching && mine?.mark && <span className="chip chip-approved">Marked</span>}
                </p>
              </div>
              <div className="actions">
                {teaching ? (
                  <>
                    <a className="button" href={`#/sites/${siteId}/assignments/${a.id}/marking`}>
                      Mark
                    </a>
                    <button className="secondary" aria-expanded={open?.id === a.id && open.what === "change"} onClick={() => toggle(a.id, "change")}>
                      Change
                    </button>
                    <button className="secondary" aria-expanded={open?.id === a.id && open.what === "extensions"} onClick={() => toggle(a.id, "extensions")}>
                      Extensions
                    </button>
                  </>
                ) : (
                  <button className="secondary" aria-expanded={open?.id === a.id} onClick={() => toggle(a.id, "work")}>
                    {open?.id === a.id ? "Close" : "Open"}
                  </button>
                )}
              </div>
            </div>
            {a.instructions && <p style={{ whiteSpace: "pre-wrap" }}>{a.instructions}</p>}
            {open?.id === a.id && open.what === "work" && <SubmitWork assignment={a} onChanged={load} />}
            {open?.id === a.id && open.what === "change" && (
              <AssignmentForm
                siteId={siteId}
                assignment={a}
                onCancel={() => setOpen(null)}
                onSaved={() => {
                  setOpen(null);
                  load();
                }}
              />
            )}
            {open?.id === a.id && open.what === "extensions" && <Extensions assignment={a} />}
          </section>
        );
      })}
    </>
  );
}
