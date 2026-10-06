import { useCallback, useEffect, useState } from "react";
import { errorMessage, get, post, remove } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { Rubric } from "../../api/types-marking";
import { useCrumb } from "../../app/frame";
import { RubricView } from "../assignments/Feedback";
import { RubricEditor } from "./RubricEditor";

/**
 * Rubrics and marking guides (items 3.09, 3.10). With a site: the course's own, kept by its teaching staff,
 * and the GSA library to copy from. Without one: the GSA library, kept by course administrators. A rubric
 * marks were given with cannot change: it is copied instead, so the evidence of past marking stays true.
 */
export function RubricsScreen({ siteId }: { siteId: number | null }) {
  const [rubrics, setRubrics] = useState<Rubric[] | null>(null);
  const [library, setLibrary] = useState<Rubric[]>([]);
  const [editing, setEditing] = useState<Rubric | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const title = siteId === null ? "GSA rubric library" : "Rubrics and marking guides";
  useCrumb(siteId === null ? null : title);

  const load = useCallback(() => {
    get<Paginated<Rubric>>(siteId === null ? "/rubrics/?library=1" : `/rubrics/?site=${siteId}`)
      .then((r) => {
        setRubrics(r.results);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load the rubrics.")));
    if (siteId !== null)
      get<Paginated<Rubric>>("/rubrics/?library=1")
        .then((r) => setLibrary(r.results))
        .catch(() => setLibrary([]));
  }, [siteId]);

  useEffect(load, [load]);

  async function copy(rubric: Rubric, to: number) {
    try {
      const copied = await post<Rubric>(`/rubrics/${rubric.id}/copy/`, { site: to });
      setNotice(`Copied “${copied.title}” to this course.`);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not copy the rubric."));
    }
  }

  async function drop(rubric: Rubric) {
    if (!window.confirm(`Delete “${rubric.title}”?`)) return;
    try {
      await remove(`/rubrics/${rubric.id}/`);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not delete the rubric. An assignment may still use it."));
    }
  }

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>{title}</h1>
          <p className="muted">
            {siteId === null
              ? "Rubrics every course may copy. A copy belongs to the course; changing the library changes no course."
              : "This course's rubrics, chosen for an assignment when it is set or changed."}
          </p>
        </div>
        <div className="actions">
          {siteId !== null && (
            <a className="button" href={`#/sites/${siteId}/assignments`}>
              Back to assignments
            </a>
          )}
          {editing === null && <button onClick={() => setEditing("new")}>New rubric</button>}
        </div>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}
      {editing === "new" && (
        <RubricEditor
          siteId={siteId}
          onCancel={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
      {rubrics?.length === 0 && <p className="muted">No rubrics yet.</p>}
      {rubrics?.map((r) => (
        <section className="module" key={r.id} aria-label={r.title}>
          {editing !== null && editing !== "new" && editing.id === r.id ? (
            <RubricEditor
              siteId={siteId}
              rubric={r}
              onCancel={() => setEditing(null)}
              onSaved={() => {
                setEditing(null);
                load();
              }}
            />
          ) : (
            <>
              <RubricView rubric={r} />
              {r.in_use && <p className="muted small">Marks were given with it, so it cannot change. Copy it to make a changed version.</p>}
              <div className="actions" style={{ marginTop: 8 }}>
                <button className="secondary" disabled={r.in_use} onClick={() => setEditing(r)}>
                  Change
                </button>
                {siteId !== null && (
                  <button className="secondary" onClick={() => copy(r, siteId)}>
                    Copy
                  </button>
                )}
                <button className="secondary danger-text" disabled={r.in_use} onClick={() => drop(r)}>
                  Delete
                </button>
              </div>
            </>
          )}
        </section>
      ))}
      {siteId !== null && library.length > 0 && (
        <section aria-label="The GSA library">
          <h2>Copy from the GSA library</h2>
          {library.map((r) => (
            <div className="module" key={r.id}>
              <RubricView rubric={r} />
              <div className="actions" style={{ marginTop: 8 }}>
                <button className="secondary" onClick={() => copy(r, siteId)} aria-label={`Copy ${r.title} to this course`}>
                  Copy to this course
                </button>
              </div>
            </div>
          ))}
        </section>
      )}
    </>
  );
}
