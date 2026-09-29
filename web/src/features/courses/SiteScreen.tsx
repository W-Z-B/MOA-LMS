import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import { canTeach, type Assignment, type Gradebook, type Paginated, type SiteContents, type Submission } from "../../api/types";

interface Props {
  siteId: number;
  onNavigate: (to: string) => void;
}

type Tab = "content" | "assignments" | "gradebook" | "announcements";

/** One course site: content, assignments, gradebook and announcements. Teaching staff get the authoring forms. */
export function SiteScreen({ siteId, onNavigate }: Props) {
  const [tab, setTab] = useState<Tab>("content");
  const [data, setData] = useState<SiteContents | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<SiteContents>(`/sites/${siteId}/contents/`)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not open this course.")));
  }, [siteId]);

  useEffect(load, [load]);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="loading">Opening course…</p>;
  const teaching = canTeach(data.site.my_role);

  async function togglePublished() {
    if (!data) return;
    try {
      await patch(`/sites/${siteId}/`, { is_published: !data.site.is_published });
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not change the site."));
    }
  }

  return (
    <>
      <p>
        <button className="link" style={{ color: "var(--accent)" }} onClick={() => onNavigate("/")}>
          My courses
        </button>
      </p>
      <div className="panel-head">
        <div>
          <h1>{data.site.title}</h1>
          <p className="muted">
            {data.site.code} · {data.site.members} members · coursework {data.site.coursework_weight}% of the final mark
          </p>
        </div>
        {teaching && (
          <button className="secondary" onClick={togglePublished}>
            {data.site.is_published ? "Unpublish" : "Publish to students"}
          </button>
        )}
      </div>
      <div className="tabs" role="tablist">
        {(["content", "assignments", "gradebook", "announcements"] as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab active" : "tab"} onClick={() => setTab(t)}>
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      {tab === "content" && <ContentTab data={data} teaching={teaching} onChanged={load} />}
      {tab === "assignments" && <AssignmentsTab siteId={siteId} teaching={teaching} />}
      {tab === "gradebook" && <GradebookTab siteId={siteId} />}
      {tab === "announcements" && <AnnouncementsTab data={data} teaching={teaching} onChanged={load} />}
    </>
  );
}

function ContentTab({ data, teaching, onChanged }: { data: SiteContents; teaching: boolean; onChanged: () => void }) {
  const [moduleTitle, setModuleTitle] = useState("");
  const [item, setItem] = useState<{ module: number; title: string; body: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function addModule(e: FormEvent) {
    e.preventDefault();
    try {
      await post("/modules/", { site: data.site.id, title: moduleTitle, position: data.modules.length + 1 });
      setModuleTitle("");
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not add the module."));
    }
  }

  async function addItem(e: FormEvent) {
    e.preventDefault();
    if (!item) return;
    try {
      await post("/content/", { module: item.module, kind: "page", title: item.title, body: item.body });
      setItem(null);
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not add the page."));
    }
  }

  return (
    <>
      {error && <p className="error">{error}</p>}
      {data.modules.length === 0 && <p className="muted">No content yet.</p>}
      {data.modules.map((m) => (
        <section className="module" key={m.id}>
          <h3>{m.title}</h3>
          <ul className="plain">
            {m.items.map((i) => (
              <li key={i.id}>
                <strong>{i.title}</strong> {!i.is_published && <span className="pill">Draft</span>}
                {i.kind === "page" && <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap" }}>{i.body}</p>}
                {i.kind === "file" && i.download_url && (
                  <p style={{ margin: "4px 0 0" }}>
                    <a href={i.download_url}>{i.filename}</a>
                  </p>
                )}
                {i.kind === "link" && (
                  <p style={{ margin: "4px 0 0" }}>
                    <a href={i.url} target="_blank" rel="noreferrer">
                      {i.url}
                    </a>
                  </p>
                )}
              </li>
            ))}
          </ul>
          {teaching &&
            (item?.module === m.id ? (
              <form className="stack sub-form" onSubmit={addItem}>
                <label>
                  Page title
                  <input id={`item-title-${m.id}`} value={item.title} onChange={(e) => setItem({ ...item, title: e.target.value })} required />
                </label>
                <label>
                  Text
                  <textarea id={`item-body-${m.id}`} value={item.body} onChange={(e) => setItem({ ...item, body: e.target.value })} />
                </label>
                <div className="actions">
                  <button type="button" className="secondary" onClick={() => setItem(null)}>
                    Cancel
                  </button>
                  <button type="submit">Add page</button>
                </div>
              </form>
            ) : (
              <p style={{ margin: "10px 0 0" }}>
                <button className="secondary" onClick={() => setItem({ module: m.id, title: "", body: "" })}>
                  Add a page
                </button>
              </p>
            ))}
        </section>
      ))}
      {teaching && (
        <form className="form-row" onSubmit={addModule}>
          <label className="grow">
            New module
            <input id="module-title" value={moduleTitle} onChange={(e) => setModuleTitle(e.target.value)} placeholder="Week 1: Soils" required />
          </label>
          <div className="actions">
            <button type="submit">Add module</button>
          </div>
        </form>
      )}
    </>
  );
}

function AssignmentsTab({ siteId, teaching }: { siteId: number; teaching: boolean }) {
  const [rows, setRows] = useState<Assignment[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState({ title: "", instructions: "", due_at: "", max_mark: "100", weight: "1" });

  const load = useCallback(() => {
    get<Paginated<Assignment>>(`/assignments/?site=${siteId}`)
      .then((r) => {
        setRows(r.results);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load assignments.")));
  }, [siteId]);

  useEffect(load, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    try {
      await post("/assignments/", { ...draft, site: siteId, due_at: new Date(draft.due_at).toISOString(), is_published: true });
      setDraft({ title: "", instructions: "", due_at: "", max_mark: "100", weight: "1" });
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not create the assignment."));
    }
  }

  return (
    <>
      {error && <p className="error">{error}</p>}
      {rows.length === 0 && <p className="muted">No assignments yet.</p>}
      {rows.map((a) => (
        <section className="module" key={a.id}>
          <div className="panel-head">
            <div>
              <h3>{a.title}</h3>
              <p className="muted small">
                Due {new Date(a.due_at).toLocaleString("en-GB")} · out of {a.max_mark} · weight {a.weight}
                {a.submissions_count !== null ? ` · ${a.submissions_count} submitted` : ""}
              </p>
            </div>
            <button className="secondary" onClick={() => setOpen(open === a.id ? null : a.id)}>
              {open === a.id ? "Close" : teaching ? "Submissions" : "Open"}
            </button>
          </div>
          {a.instructions && <p style={{ whiteSpace: "pre-wrap" }}>{a.instructions}</p>}
          {open === a.id && (teaching ? <Marking assignment={a} onChanged={load} /> : <Submit assignment={a} onChanged={load} />)}
        </section>
      ))}
      {teaching && (
        <form className="stack sub-form" onSubmit={create}>
          <h3>New assignment</h3>
          <div className="grid2">
            <label>
              Title
              <input id="asg-title" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} required />
            </label>
            <label>
              Due
              <input id="asg-due" type="datetime-local" value={draft.due_at} onChange={(e) => setDraft({ ...draft, due_at: e.target.value })} required />
            </label>
            <label>
              Maximum mark
              <input id="asg-max" type="number" min={1} value={draft.max_mark} onChange={(e) => setDraft({ ...draft, max_mark: e.target.value })} required />
            </label>
            <label>
              Weight
              <input id="asg-weight" type="number" min={0.1} step="0.1" value={draft.weight} onChange={(e) => setDraft({ ...draft, weight: e.target.value })} required />
            </label>
            <label className="span2">
              Instructions
              <textarea id="asg-instructions" value={draft.instructions} onChange={(e) => setDraft({ ...draft, instructions: e.target.value })} />
            </label>
          </div>
          <div className="actions">
            <button type="submit">Create and publish</button>
          </div>
        </form>
      )}
    </>
  );
}

function Submit({ assignment, onChanged }: { assignment: Assignment; onChanged: () => void }) {
  const mine = assignment.my_submission;
  const [text, setText] = useState(mine?.text ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = new FormData();
    if (text) body.set("text", text);
    if (file) body.set("file", file);
    try {
      await post(`/assignments/${assignment.id}/submit/`, body);
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not submit."));
    }
  }

  if (mine?.mark) {
    return (
      <p className="notice">
        Marked: <strong>{mine.mark.mark}</strong> out of {assignment.max_mark}. {mine.mark.feedback}
      </p>
    );
  }
  return (
    <form className="stack sub-form" onSubmit={submit}>
      {mine && (
        <p className="muted">
          Submitted {new Date(mine.submitted_at).toLocaleString("en-GB")}
          {mine.is_late ? " (late)" : ""}. You can replace it until it is marked.
        </p>
      )}
      <label>
        Your answer
        <textarea id={`answer-${assignment.id}`} value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <label>
        Or attach a file
        <input id={`file-${assignment.id}`} type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit" disabled={!text && !file}>
          Submit
        </button>
      </div>
    </form>
  );
}

function Marking({ assignment, onChanged }: { assignment: Assignment; onChanged: () => void }) {
  const [rows, setRows] = useState<Submission[]>([]);
  const [marks, setMarks] = useState<Record<number, { mark: string; feedback: string }>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Submission[]>(`/assignments/${assignment.id}/submissions/`)
      .then((r) => {
        setRows(r);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load submissions.")));
  }, [assignment.id]);

  useEffect(load, [load]);

  async function save(row: Submission, release: boolean) {
    const entry = marks[row.id] ?? { mark: row.mark?.mark ?? "", feedback: row.mark?.feedback ?? "" };
    try {
      await post(`/submissions/${row.id}/mark/`, { mark: entry.mark, feedback: entry.feedback, is_released: release });
      load();
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not save the mark."));
    }
  }

  if (rows.length === 0) return <p className="muted">Nothing submitted yet.</p>;
  return (
    <>
      {error && <p className="error">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Student</th>
            <th>Work</th>
            <th className="num">Mark / {assignment.max_mark}</th>
            <th>Feedback</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const entry = marks[row.id] ?? { mark: row.mark?.mark ?? "", feedback: row.mark?.feedback ?? "" };
            return (
              <tr key={row.id}>
                <td>
                  {row.student_no} {row.student_name} {row.is_late && <span className="pill">Late</span>}
                </td>
                <td>
                  {row.text && <span style={{ whiteSpace: "pre-wrap" }}>{row.text}</span>}{" "}
                  {row.download_url && <a href={row.download_url}>{row.filename}</a>}
                </td>
                <td className="num">
                  <input
                    type="number"
                    min={0}
                    max={Number(assignment.max_mark)}
                    step="0.5"
                    aria-label={`Mark for ${row.student_no}`}
                    value={entry.mark}
                    onChange={(e) => setMarks({ ...marks, [row.id]: { ...entry, mark: e.target.value } })}
                  />
                </td>
                <td>
                  <input
                    aria-label={`Feedback for ${row.student_no}`}
                    value={entry.feedback}
                    onChange={(e) => setMarks({ ...marks, [row.id]: { ...entry, feedback: e.target.value } })}
                  />
                </td>
                <td className="actions">
                  <button className="secondary" onClick={() => save(row, false)} disabled={!entry.mark}>
                    Save
                  </button>
                  <button onClick={() => save(row, true)} disabled={!entry.mark}>
                    {row.mark?.is_released ? "Update" : "Release"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

function GradebookTab({ siteId }: { siteId: number }) {
  const [book, setBook] = useState<Gradebook | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Gradebook>(`/sites/${siteId}/gradebook/`)
      .then((b) => {
        setBook(b);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load the gradebook.")));
  }, [siteId]);

  if (error) return <p className="error">{error}</p>;
  if (!book) return <p className="loading">Loading…</p>;
  if (book.rows.length === 0) return <p className="muted">No students in this course.</p>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead>
          <tr>
            <th>Student</th>
            {book.assignments.map((a) => (
              <th key={a.id} className="num">
                {a.title} / {a.max_mark}
              </th>
            ))}
            <th className="num">Coursework %</th>
          </tr>
        </thead>
        <tbody>
          {book.rows.map((row) => (
            <tr key={row.person_id}>
              <td>
                {row.student_no} {row.name}
              </td>
              {book.assignments.map((a) => {
                const cell = row.marks[String(a.id)];
                return (
                  <td key={a.id} className="num">
                    {cell?.mark ?? (cell?.submitted ? "submitted" : "")}
                  </td>
                );
              })}
              <td className="num">
                <strong>{row.coursework_percent ?? ""}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        Coursework totals are returned to the SRMS, where the examination mark is added and the result is approved and published.
      </p>
    </div>
  );
}

function AnnouncementsTab({ data, teaching, onChanged }: { data: SiteContents; teaching: boolean; onChanged: () => void }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function publish(e: FormEvent) {
    e.preventDefault();
    try {
      await post("/announcements/", { site: data.site.id, title, body });
      setTitle("");
      setBody("");
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not post the announcement."));
    }
  }

  return (
    <>
      {teaching && (
        <form className="stack sub-form" onSubmit={publish} style={{ borderTop: 0, marginTop: 0, paddingTop: 0 }}>
          <label>
            Title
            <input id="ann-title" value={title} onChange={(e) => setTitle(e.target.value)} required />
          </label>
          <label>
            Message
            <textarea id="ann-body" value={body} onChange={(e) => setBody(e.target.value)} required />
          </label>
          {error && <p className="error">{error}</p>}
          <div className="actions">
            <button type="submit">Post and notify students</button>
          </div>
        </form>
      )}
      {data.announcements.length === 0 && <p className="muted">No announcements.</p>}
      {data.announcements.map((a) => (
        <section className="module" key={a.id}>
          <h3>{a.title}</h3>
          <p className="muted small">
            {a.author_name ?? "Course team"} · {new Date(a.created_at).toLocaleString("en-GB")}
          </p>
          <p style={{ whiteSpace: "pre-wrap" }}>{a.body}</p>
        </section>
      ))}
    </>
  );
}
