import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post, remove } from "../../api/client";
import type { Paginated, SearchHit } from "../../api/types";
import type { Accommodation } from "../../api/types-marking";

type Draft = Omit<Accommodation, "id" | "person" | "student_no">;
const BLANK: Draft = { extra_time_percent: 0, extra_days: 0, other_format: "", reason: "", is_active: true };

/**
 * Accommodations held once for each student (item 3.23), kept by course administrators: extra time added to
 * every quiz time limit and extra days to every due date, applied automatically, and any other format needed.
 * Lecturers see only that an accommodation applies, never the reason.
 */
export function AccommodationsScreen() {
  const [rows, setRows] = useState<Accommodation[] | null>(null);
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<Accommodation>>("/accommodations/")
      .then((r) => {
        setRows(r.results);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load the accommodations.")));
  }, []);

  useEffect(load, [load]);

  async function drop(row: Accommodation) {
    if (!window.confirm(`Remove the accommodation for ${row.student_no}?`)) return;
    try {
      await remove(`/accommodations/${row.id}/`);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not remove it."));
    }
  }

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>Accommodations</h1>
          <p className="muted">Held once for each student and applied to every quiz and due date. Lecturers see only that one applies.</p>
        </div>
        {editing === null && <button onClick={() => setEditing("new")}>Add an accommodation</button>}
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {editing === "new" && (
        <AccommodationForm
          onCancel={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
      {rows?.length === 0 && <p className="muted">No accommodations are held.</p>}
      {rows?.map((row) => (
        <section className="module" key={row.id} aria-label={`Accommodation for ${row.student_no}`}>
          {editing === row.id ? (
            <AccommodationForm
              existing={row}
              onCancel={() => setEditing(null)}
              onSaved={() => {
                setEditing(null);
                load();
              }}
            />
          ) : (
            <div className="spread">
              <div className="stacked">
                <h3>
                  {row.student_no} {!row.is_active && <span className="chip chip-draft">Not in force</span>}
                </h3>
                <p className="small">
                  {[
                    row.extra_time_percent ? `${row.extra_time_percent}% more time in quizzes` : "",
                    row.extra_days ? `${row.extra_days} more day${row.extra_days === 1 ? "" : "s"} for every assignment` : "",
                    row.other_format,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "Nothing set"}
                </p>
                {row.reason && <p className="muted small">Reason (course administrators only): {row.reason}</p>}
              </div>
              <div className="actions">
                <button className="secondary" onClick={() => setEditing(row.id)}>
                  Change
                </button>
                <button className="secondary danger-text" onClick={() => drop(row)}>
                  Remove
                </button>
              </div>
            </div>
          )}
        </section>
      ))}
    </>
  );
}

function AccommodationForm({ existing, onSaved, onCancel }: { existing?: Accommodation; onSaved: () => void; onCancel: () => void }) {
  const [draft, setDraft] = useState<Draft>(existing ?? BLANK);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [person, setPerson] = useState<SearchHit | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (existing || query.trim().length < 2) return;
    const timer = setTimeout(() => {
      get<{ people: SearchHit[] }>(`/search/?q=${encodeURIComponent(query.trim())}`)
        .then((r) => setHits(r.people.filter((p) => p.sub.includes("Student"))))
        .catch(() => setHits([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [query, existing]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (existing) await patch(`/accommodations/${existing.id}/`, draft);
      else {
        if (!person) {
          setError("Choose the student first.");
          return;
        }
        await post("/accommodations/", { ...draft, person: person.id });
      }
      onSaved();
    } catch (err) {
      setError(errorMessage(err, "Could not save the accommodation."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={save} aria-label={existing ? `Change the accommodation for ${existing.student_no}` : "New accommodation"}>
      {!existing && (
        <>
          <label>
            Student (name or student number)
            <input value={query} onChange={(e) => setQuery(e.target.value)} autoComplete="off" />
          </label>
          {person ? (
            <p>
              For <strong>{person.title}</strong> ({person.sub}){" "}
              <button type="button" className="link" onClick={() => setPerson(null)}>
                Choose another
              </button>
            </p>
          ) : (
            query.trim().length >= 2 &&
            hits.length > 0 && (
              <ul className="plain" aria-label="Students found">
                {hits.map((h) => (
                  <li key={h.id}>
                    <button type="button" className="secondary" onClick={() => setPerson(h)}>
                      {h.title} · {h.sub}
                    </button>
                  </li>
                ))}
              </ul>
            )
          )}
        </>
      )}
      <div className="grid2">
        <label>
          More time in quizzes (%)
          <input type="number" min={0} max={300} value={draft.extra_time_percent} onChange={(e) => setDraft((prev) => ({ ...prev, extra_time_percent: Number(e.target.value) }))} />
        </label>
        <label>
          More days for each assignment
          <input type="number" min={0} max={60} value={draft.extra_days} onChange={(e) => setDraft((prev) => ({ ...prev, extra_days: Number(e.target.value) }))} />
        </label>
        <label className="span2">
          Another format needed (optional)
          <input value={draft.other_format} maxLength={300} onChange={(e) => setDraft((prev) => ({ ...prev, other_format: e.target.value }))} placeholder="Large print; papers read aloud" />
        </label>
        <label className="span2">
          Reason (course administrators only; never shown to lecturers)
          <textarea value={draft.reason} onChange={(e) => setDraft((prev) => ({ ...prev, reason: e.target.value }))} />
        </label>
        <label className="inline span2">
          <input type="checkbox" checked={draft.is_active} onChange={(e) => setDraft((prev) => ({ ...prev, is_active: e.target.checked }))} />
          In force
        </label>
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
        <button type="submit">Save</button>
      </div>
    </form>
  );
}
