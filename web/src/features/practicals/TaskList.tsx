/** Teaching staff's Practicals tab (item 3.12): the site's practical tasks, a new task, and the field
 * instructors and assessors named on the site. */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post, remove } from "../../api/client";
import type { Paginated, SearchHits } from "../../api/types";
import { UNIT_TYPES, unitLabel, type Assessor, type PracticalTask, type UnitType } from "../../api/types-practicals";
import { windowText } from "./helpers";
import { practicalsPath } from "./routes";

interface Props {
  siteId: number;
  onNavigate: (to: string) => void;
}

const blank = {
  title: "",
  instructions: "",
  unit_type: "crop_plot" as UnitType,
  location: "",
  weight: "0",
  opens_at: "",
  closes_at: "",
  max_attempts: "3",
  is_published: false,
};

const iso = (local: string) => (local ? new Date(local).toISOString() : null);

export function TaskList({ siteId, onNavigate }: Props) {
  const [tasks, setTasks] = useState<PracticalTask[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState(blank);

  const load = useCallback(() => {
    get<Paginated<PracticalTask>>(`/practical-tasks/?site=${siteId}`)
      .then((r) => {
        setTasks(r.results);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load the practical tasks.")));
  }, [siteId]);

  useEffect(load, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    try {
      const task = await post<PracticalTask>("/practical-tasks/", {
        ...draft,
        site: siteId,
        opens_at: iso(draft.opens_at),
        closes_at: iso(draft.closes_at),
      });
      setDraft(blank);
      setCreating(false);
      onNavigate(practicalsPath(siteId, task.id));
    } catch (err) {
      setError(errorMessage(err, "Could not create the task."));
    }
  }

  return (
    <>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {tasks === null && !error && <p className="loading">Loading…</p>}
      {tasks?.length === 0 && <p className="muted">No practical tasks yet.</p>}
      {tasks?.map((t) => (
        <section className="module" key={t.id}>
          <div className="panel-head">
            <div>
              <h3>
                {t.title} {!t.is_published && <span className="pill">Draft</span>}
              </h3>
              <p className="muted small">
                {unitLabel(t.unit_type)}
                {t.location && `, ${t.location}`} · {t.criteria.length} criteria · {windowText(t)} · {t.max_attempts} attempts ·{" "}
                {t.counts_in_coursework ? `weight ${t.weight}` : "does not count in coursework"}
              </p>
            </div>
            <div className="actions">
              <button className="secondary" onClick={() => onNavigate(practicalsPath(siteId, t.id))} aria-label={`Open ${t.title}`}>
                Open
              </button>
              {t.is_published && t.criteria.length > 0 && (
                <button onClick={() => onNavigate(practicalsPath(siteId, t.id, "observe"))} aria-label={`Mark ${t.title} in the field`}>
                  Mark in the field
                </button>
              )}
            </div>
          </div>
        </section>
      ))}
      {creating ? (
        <form className="stack sub-form" onSubmit={create}>
          <h3>New practical task</h3>
          <div className="grid2">
            <label className="span2">
              Title
              <input value={draft.title} onChange={(e) => setDraft((prev) => ({ ...prev, title: e.target.value }))} required maxLength={160} />
            </label>
            <label>
              Where it is done
              <select value={draft.unit_type} onChange={(e) => setDraft((prev) => ({ ...prev, unit_type: e.target.value as UnitType }))}>
                {UNIT_TYPES.map((u) => (
                  <option key={u.value} value={u.value}>
                    {u.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Location
              <input value={draft.location} onChange={(e) => setDraft((prev) => ({ ...prev, location: e.target.value }))} placeholder="Plot 7" maxLength={160} />
            </label>
            <label>
              Weight in coursework (0 if it does not count)
              <input type="number" min={0} step="0.5" value={draft.weight} onChange={(e) => setDraft((prev) => ({ ...prev, weight: e.target.value }))} required />
            </label>
            <label>
              Attempts allowed
              <input type="number" min={1} max={10} value={draft.max_attempts} onChange={(e) => setDraft((prev) => ({ ...prev, max_attempts: e.target.value }))} required />
            </label>
            <label>
              Opens
              <input type="datetime-local" value={draft.opens_at} onChange={(e) => setDraft((prev) => ({ ...prev, opens_at: e.target.value }))} />
            </label>
            <label>
              Closes
              <input type="datetime-local" value={draft.closes_at} onChange={(e) => setDraft((prev) => ({ ...prev, closes_at: e.target.value }))} />
            </label>
            <label className="span2">
              Instructions
              <textarea value={draft.instructions} onChange={(e) => setDraft((prev) => ({ ...prev, instructions: e.target.value }))} />
            </label>
          </div>
          <p className="muted small">Add the checklist's criteria next. Publish the task when the checklist is ready.</p>
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button type="submit">Create task</button>
          </div>
        </form>
      ) : (
        <p>
          <button className="secondary" onClick={() => setCreating(true)}>
            New practical task
          </button>
        </p>
      )}
      <Assessors siteId={siteId} />
    </>
  );
}

/** Field instructors and assessors: they may observe on this site's tasks without teaching on it. */
function Assessors({ siteId }: { siteId: number }) {
  const [rows, setRows] = useState<Assessor[]>([]);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHits["people"] | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<Assessor>>(`/practical-assessors/?site=${siteId}`)
      .then((r) => setRows(r.results))
      .catch((err) => setError(errorMessage(err, "Could not load the assessors.")));
  }, [siteId]);

  useEffect(load, [load]);

  async function find(e: FormEvent) {
    e.preventDefault();
    try {
      const found = await get<SearchHits>(`/search/?q=${encodeURIComponent(query)}`);
      setHits(found.people.filter((p) => p.sub.includes("Staff")));
    } catch (err) {
      setError(errorMessage(err, "Could not search."));
    }
  }

  async function name(person: number) {
    try {
      await post("/practical-assessors/", { site: siteId, person, note });
      setHits(null);
      setQuery("");
      setNote("");
      setError(null);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not name the assessor."));
    }
  }

  async function drop(row: Assessor) {
    try {
      await remove(`/practical-assessors/${row.id}/`);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not remove the assessor."));
    }
  }

  return (
    <section className="module" aria-labelledby="assessors-heading">
      <h3 id="assessors-heading">Named assessors</h3>
      <p className="muted small">Field instructors and farm staff who may observe students on this course's tasks. Release stays with the teaching staff.</p>
      {rows.length === 0 && <p className="muted">None named.</p>}
      <ul className="plain">
        {rows.map((a) => (
          <li key={a.id} className="spread">
            <span>
              {a.person_name} ({a.employee_no}){a.note && ` · ${a.note}`}
            </span>
            <button className="secondary small-button" onClick={() => drop(a)} aria-label={`Remove ${a.person_name}`}>
              Remove
            </button>
          </li>
        ))}
      </ul>
      <form className="form-row" onSubmit={find} style={{ marginTop: 12 }}>
        <label className="grow">
          Find a member of staff
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Name or employee number" required minLength={2} />
        </label>
        <label className="grow">
          Their role here (optional)
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Farm manager, poultry unit" maxLength={160} />
        </label>
        <div className="actions">
          <button type="submit" className="secondary">
            Find
          </button>
        </div>
      </form>
      {hits !== null && (
        <ul className="plain">
          {hits.length === 0 && <li className="muted">No member of staff found. You can find staff who are on the courses you teach.</li>}
          {hits.map((h) => (
            <li key={h.id} className="spread">
              <span>
                {h.title} <span className="muted">({h.sub})</span>
              </span>
              <button className="small-button" onClick={() => name(h.id)} aria-label={`Name ${h.title} as an assessor`}>
                Name as assessor
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
