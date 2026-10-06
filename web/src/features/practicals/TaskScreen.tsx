/**
 * One practical task for its teaching staff (items 3.12 and 3.13): the checklist's criteria (pass or fail,
 * or scored; critical or not) and what each gives evidence for in the competency frameworks the site
 * follows; the class list with each student's attempts; and release, one observation or all.
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import type { Paginated } from "../../api/types";
import { unitLabel, type Criterion, type FrameworkTree, type Observation, type PracticalTask, type SiteFramework, type TaskStudent } from "../../api/types-practicals";
import { ObservationCard } from "./ObservationCard";
import { practicalsPath } from "./routes";
import { windowText } from "./helpers";

interface Props {
  siteId: number;
  taskId: number;
  onNavigate: (to: string) => void;
}

export function TaskScreen({ siteId, taskId, onNavigate }: Props) {
  const [task, setTask] = useState<PracticalTask | null>(null);
  const [students, setStudents] = useState<TaskStudent[]>([]);
  const [frameworks, setFrameworks] = useState<FrameworkTree[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [openStudent, setOpenStudent] = useState<number | null>(null);

  const load = useCallback(() => {
    get<PracticalTask>(`/practical-tasks/${taskId}/`)
      .then((t) => {
        setTask(t);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not open the task.")));
    get<TaskStudent[]>(`/practical-tasks/${taskId}/students/`)
      .then(setStudents)
      .catch(() => setStudents([]));
  }, [taskId]);

  useEffect(load, [load]);

  useEffect(() => {
    get<Paginated<SiteFramework>>(`/site-frameworks/?site=${siteId}`)
      .then((r) => Promise.all(r.results.map((f) => get<FrameworkTree>(`/competency-frameworks/${f.framework}/`))))
      .then(setFrameworks)
      .catch(() => setFrameworks([]));
  }, [siteId]);

  async function act(work: () => Promise<unknown>, done: string, failed: string) {
    try {
      await work();
      setNotice(done);
      setError(null);
      load();
    } catch (err) {
      setError(errorMessage(err, failed));
    }
  }

  if (error && !task)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!task) return <p className="loading">Opening the task…</p>;
  const unreleased = students.filter((s) => s.latest && !s.latest.is_released).length;

  return (
    <>
      <p>
        <button type="button" className="link accent" onClick={() => onNavigate(practicalsPath(siteId))}>
          ← All practical tasks
        </button>
      </p>
      <div className="panel-head wrap-head">
        <div>
          <h2>
            {task.title} {!task.is_published && <span className="pill">Draft</span>}
          </h2>
          <p className="muted small">
            {unitLabel(task.unit_type)}
            {task.location && `, ${task.location}`} · {windowText(task)} · {task.max_attempts} attempts ·{" "}
            {task.counts_in_coursework ? `weight ${task.weight}` : "does not count in coursework"}
          </p>
        </div>
        <div className="actions">
          <button
            className="secondary"
            onClick={() =>
              act(
                () => patch(`/practical-tasks/${task.id}/`, { is_published: !task.is_published }),
                task.is_published ? "The task is a draft again." : "The task is published.",
                "Could not change the task.",
              )
            }
          >
            {task.is_published ? "Unpublish" : "Publish"}
          </button>
          {task.is_published && task.criteria.length > 0 && (
            <button onClick={() => onNavigate(practicalsPath(siteId, task.id, "observe"))}>Mark in the field</button>
          )}
        </div>
      </div>
      {task.instructions && <p className="pre">{task.instructions}</p>}
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      <h3>Checklist</h3>
      {task.criteria.length === 0 && <p className="muted">No criteria yet. Add the first below.</p>}
      <ol className="plain criteria-list">
        {task.criteria.map((c) => (
          <CriterionRow key={c.id} criterion={c} frameworks={frameworks} onSaved={load} onError={setError} />
        ))}
      </ol>
      <NewCriterion task={task} onSaved={load} onError={setError} />

      <div className="panel-head wrap-head" style={{ marginTop: 20 }}>
        <h3>Class list</h3>
        <button
          disabled={unreleased === 0}
          onClick={() =>
            act(
              () => post<{ released: number }>(`/practical-tasks/${task.id}/release/`),
              "Every observation of this task is released to its student.",
              "Could not release.",
            )
          }
        >
          Release all ({unreleased})
        </button>
      </div>
      {students.length === 0 && <p className="muted">No students on this course.</p>}
      <ul className="plain">
        {students.map((s) => (
          <li key={s.person_id} className="module class-row">
            <div className="panel-head wrap-head">
              <div>
                <strong>{s.name}</strong> <span className="muted">{s.student_no}</span>
                <p className="muted small" style={{ margin: 0 }}>
                  {s.attempts === 0
                    ? "Not observed yet"
                    : `${s.attempts} of ${task.max_attempts} attempts · latest ${s.latest?.score}${s.latest?.critical_passed ? "" : ", critical not met"} · ${
                        s.latest?.is_released ? "released" : "not released"
                      }`}
                </p>
              </div>
              <div className="actions">
                {s.attempts > 0 && (
                  <button className="secondary small-button" onClick={() => setOpenStudent(openStudent === s.person_id ? null : s.person_id)}>
                    {openStudent === s.person_id ? "Close" : `Attempts of ${s.name}`}
                  </button>
                )}
                {s.latest && !s.latest.is_released && (
                  <button
                    className="small-button"
                    onClick={() =>
                      act(() => post(`/observations/${s.latest!.id}/release/`), `Released to ${s.name}.`, "Could not release.")
                    }
                  >
                    Release to {s.name}
                  </button>
                )}
                {task.is_published && s.attempts_left > 0 && task.criteria.length > 0 && (
                  <button
                    className="secondary small-button"
                    onClick={() => onNavigate(practicalsPath(siteId, task.id, "observe", s.person_id))}
                    aria-label={`Observe ${s.name}`}
                  >
                    Observe
                  </button>
                )}
              </div>
            </div>
            {openStudent === s.person_id && <Attempts taskId={task.id} personId={s.person_id} />}
          </li>
        ))}
      </ul>
    </>
  );
}

function Attempts({ taskId, personId }: { taskId: number; personId: number }) {
  const [rows, setRows] = useState<Observation[] | null>(null);
  useEffect(() => {
    get<Paginated<Observation>>(`/observations/?task=${taskId}&student=${personId}`)
      .then((r) => setRows(r.results))
      .catch(() => setRows([]));
  }, [taskId, personId]);
  if (rows === null) return <p className="loading">Loading…</p>;
  return (
    <>
      {rows.map((o) => (
        <ObservationCard key={o.id} observation={o} />
      ))}
    </>
  );
}

/** Performance criteria, unit by unit, of the frameworks the site follows, to tick. */
function MapPicker({ frameworks, chosen, onChange }: { frameworks: FrameworkTree[]; chosen: number[]; onChange: (ids: number[]) => void }) {
  if (frameworks.length === 0) return <p className="muted small">The site follows no competency framework, so there is nothing to map to.</p>;
  const toggle = (id: number) => onChange(chosen.includes(id) ? chosen.filter((x) => x !== id) : [...chosen, id]);
  return (
    <>
      {frameworks.flatMap((f) =>
        f.units.map((u) => (
          <fieldset key={u.id} className="map-unit">
            <legend>
              {u.code} {u.title} ({f.code})
            </legend>
            {u.elements.flatMap((e) =>
              e.criteria.map((pc) => (
                <label key={pc.id} className="inline check-row">
                  <input type="checkbox" checked={chosen.includes(pc.id)} onChange={() => toggle(pc.id)} />
                  <span>
                    {pc.code} {pc.text}
                  </span>
                </label>
              )),
            )}
          </fieldset>
        )),
      )}
    </>
  );
}

function pcCodes(ids: number[], frameworks: FrameworkTree[]) {
  const all = frameworks.flatMap((f) => f.units.flatMap((u) => u.elements.flatMap((e) => e.criteria)));
  return ids.map((id) => all.find((pc) => pc.id === id)?.code ?? `#${id}`).join(", ");
}

function CriterionRow({
  criterion: c,
  frameworks,
  onSaved,
  onError,
}: {
  criterion: Criterion;
  frameworks: FrameworkTree[];
  onSaved: () => void;
  onError: (message: string) => void;
}) {
  const [mapping, setMapping] = useState<number[] | null>(null);

  async function saveMapping() {
    try {
      await patch(`/practical-criteria/${c.id}/`, { performance_criteria: mapping });
      setMapping(null);
      onSaved();
    } catch (err) {
      onError(errorMessage(err, "Could not save the mapping."));
    }
  }

  return (
    <li className="module">
      <div className="panel-head wrap-head">
        <div>
          <strong>
            {c.position}. {c.text}
          </strong>{" "}
          {c.is_critical && <span className="pill critical">Critical</span>}
          <p className="muted small" style={{ margin: 0 }}>
            {c.kind === "scored" ? `Scored 0 to ${c.max_score}, ${c.pass_score} to pass` : "Met or not met"}
            {c.performance_criteria.length > 0 && ` · evidence for ${pcCodes(c.performance_criteria, frameworks)}`}
          </p>
        </div>
        {mapping === null && frameworks.length > 0 && (
          <button className="secondary small-button" onClick={() => setMapping(c.performance_criteria)} aria-label={`Map "${c.text}" to performance criteria`}>
            Map to competency
          </button>
        )}
      </div>
      {mapping !== null && (
        <div className="stack sub-form">
          <MapPicker frameworks={frameworks} chosen={mapping} onChange={setMapping} />
          <div className="actions">
            <button className="secondary" onClick={() => setMapping(null)}>
              Cancel
            </button>
            <button onClick={saveMapping}>Save mapping</button>
          </div>
        </div>
      )}
    </li>
  );
}

function NewCriterion({ task, onSaved, onError }: { task: PracticalTask; onSaved: () => void; onError: (message: string) => void }) {
  const blank = { text: "", kind: "pass_fail" as Criterion["kind"], max_score: "5", pass_score: "3", is_critical: false };
  const [draft, setDraft] = useState(blank);

  async function add(e: FormEvent) {
    e.preventDefault();
    try {
      await post("/practical-criteria/", {
        task: task.id,
        position: task.criteria.length + 1,
        text: draft.text,
        kind: draft.kind,
        is_critical: draft.is_critical,
        ...(draft.kind === "scored" ? { max_score: Number(draft.max_score), pass_score: Number(draft.pass_score) } : {}),
      });
      setDraft(blank);
      onSaved();
    } catch (err) {
      onError(errorMessage(err, "Could not add the criterion."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={add}>
      <h3>Add a criterion</h3>
      <label>
        What the assessor looks for
        <input value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} placeholder="Bed formed to 1.2 m wide" required maxLength={300} />
      </label>
      <div className="grid2">
        <label>
          How it is marked
          <select value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value as Criterion["kind"] })}>
            <option value="pass_fail">Met or not met</option>
            <option value="scored">A score</option>
          </select>
        </label>
        {draft.kind === "scored" && (
          <>
            <label>
              Highest score
              <input type="number" min={1} max={100} value={draft.max_score} onChange={(e) => setDraft({ ...draft, max_score: e.target.value })} required />
            </label>
            <label>
              Score to pass
              <input type="number" min={1} max={Number(draft.max_score) || 1} value={draft.pass_score} onChange={(e) => setDraft({ ...draft, pass_score: e.target.value })} required />
            </label>
          </>
        )}
      </div>
      <label className="inline check-row">
        <input type="checkbox" checked={draft.is_critical} onChange={(e) => setDraft({ ...draft, is_critical: e.target.checked })} />
        <span>Critical: it must be met for the task to be passed</span>
      </label>
      {task.is_published && (
        <p className="muted small">Students already marked keep their results; a criterion they were marked against cannot be reworded.</p>
      )}
      <div className="actions">
        <button type="submit">Add criterion</button>
      </div>
    </form>
  );
}
