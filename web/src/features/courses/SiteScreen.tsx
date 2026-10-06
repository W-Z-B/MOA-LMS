import { Suspense, lazy, useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import { canTeach, type Assignment, type Gradebook, type Licence, type Paginated, type SiteContents, type Submission } from "../../api/types";
import { dmyTime } from "../../app/format";
import { useCrumb } from "../../app/frame";
import { submitAssignmentText } from "../../app/offlineQueue";
import { SITE_TABS, type SiteTab } from "../../app/router";
import { SendState } from "../../app/SendState";

// Practicals and the logbook are loaded only when their tab is opened, so they add nothing to the shell.
const PracticalsTab = lazy(() => import("../practicals/PracticalsTab").then((m) => ({ default: m.PracticalsTab })));
const LogbookTab = lazy(() => import("../practicals/LogbookTab").then((m) => ({ default: m.LogbookTab })));

interface Props {
  siteId: number;
  /** The tab named in the address (item 2.10), so each can be shared: #/sites/4/assignments. */
  tab: SiteTab;
  onTab: (tab: SiteTab) => void;
}

const TAB_LABEL: Record<SiteTab, string> = {
  content: "Content",
  assignments: "Assignments",
  gradebook: "Gradebook",
  announcements: "Announcements",
  practicals: "Practicals",
  logbook: "Logbook",
};

/**
 * One course site: content, assignments, gradebook and announcements. Teaching staff get the authoring forms.
 * Its name is the last breadcrumb (Home / My courses / the site), and each tab has an address of its own.
 */
export function SiteScreen({ siteId, tab, onTab }: Props) {
  const [data, setData] = useState<SiteContents | null>(null);
  const [error, setError] = useState<string | null>(null);
  useCrumb(data?.site.title);

  const load = useCallback(() => {
    get<SiteContents>(`/sites/${siteId}/contents/`)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not open this course.")));
  }, [siteId]);

  useEffect(load, [load]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
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
      <div className="page-head site-head">
        <div className="stacked">
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
        {SITE_TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab active" : "tab"} onClick={() => onTab(t)}>
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>
      {tab === "content" && <ContentTab data={data} teaching={teaching} onChanged={load} />}
      {tab === "assignments" && <AssignmentsTab siteId={siteId} teaching={teaching} />}
      {tab === "gradebook" && <GradebookTab siteId={siteId} />}
      {tab === "announcements" && <AnnouncementsTab data={data} teaching={teaching} onChanged={load} />}
      <Suspense fallback={<p className="loading">Loading…</p>}>
        {tab === "practicals" && <PracticalsTab siteId={siteId} teaching={teaching} />}
        {tab === "logbook" && <LogbookTab siteId={siteId} teaching={teaching} />}
      </Suspense>
    </>
  );
}

type ItemKind = "page" | "file" | "link";

interface ItemDraft {
  module: number;
  kind: ItemKind;
  title: string;
  body: string;
  url: string;
  file: File | null;
  licence: Licence | "";
  open_licence: string;
  source: string;
}

const LICENCES: { value: Licence; label: string }[] = [
  { value: "gsa_own", label: "GSA's own material" },
  { value: "open_licence", label: "Under an open licence" },
  { value: "fair_dealing", label: "Used under fair dealing (research or private study)" },
  { value: "permission_held", label: "Used with the owner's permission" },
];

const OPEN_LICENCES = [
  { value: "cc_by", label: "CC BY" },
  { value: "cc_by_sa", label: "CC BY-SA" },
  { value: "cc_by_nc", label: "CC BY-NC" },
  { value: "cc0", label: "CC0" },
  { value: "other", label: "Another open licence" },
];

const ADD_LABEL: Record<ItemKind, string> = { page: "Add page", file: "Upload file", link: "Add link" };

function blankDraft(module: number, kind: ItemKind): ItemDraft {
  // Pages are GSA's own unless said otherwise; for a file or a link the lecturer must say whose it is.
  return { module, kind, title: "", body: "", url: "", file: null, licence: kind === "page" ? "gsa_own" : "", open_licence: "", source: "" };
}

function ContentTab({ data, teaching, onChanged }: { data: SiteContents; teaching: boolean; onChanged: () => void }) {
  const [moduleTitle, setModuleTitle] = useState("");
  const [item, setItem] = useState<ItemDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function addModule(e: FormEvent) {
    e.preventDefault();
    try {
      await post("/modules/", { site: data.site.id, title: moduleTitle });
      setModuleTitle("");
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not add the module."));
    }
  }

  async function addItem(e: FormEvent) {
    e.preventDefault();
    if (!item) return;
    const common = {
      module: item.module,
      kind: item.kind,
      title: item.title,
      licence: item.licence,
      open_licence: item.licence === "open_licence" ? item.open_licence : "",
      source: item.source,
    };
    setSaving(true);
    try {
      if (item.kind === "file") {
        const form = new FormData();
        Object.entries(common).forEach(([key, value]) => form.set(key, String(value)));
        if (item.file) form.set("file", item.file);
        await post("/content/", form);
      } else if (item.kind === "link") {
        await post("/content/", { ...common, url: item.url });
      } else {
        await post("/content/", { ...common, body: item.body, body_format: "text" });
      }
      setItem(null);
      setError(null);
      onChanged();
    } catch (err) {
      setError(errorMessage(err, `Could not add the ${item.kind}.`));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {data.modules.length === 0 && <p className="muted">No content yet.</p>}
      {data.modules.map((m) => (
        <section className="module" key={m.id}>
          <h3>{m.title}</h3>
          <ul className="plain">
            {m.items.map((i) => (
              <li key={i.id}>
                <strong>{i.title}</strong> {!i.is_published && <span className="pill">Draft</span>}
                {i.under_review && <span className="pill">Under review</span>}
                {teaching && i.conditions && (
                  <p className="muted small" style={{ margin: "2px 0 0" }}>
                    {i.conditions}
                  </p>
                )}
                {/* Page bodies are HTML cleaned on the server against an allow-list (courses.richtext). */}
                {i.kind === "page" && <div className="page-body" style={{ margin: "4px 0 0" }} dangerouslySetInnerHTML={{ __html: i.body }} />}
                {i.kind === "file" && i.download_url && (
                  <p style={{ margin: "4px 0 0" }}>
                    <a href={i.download_url}>{i.filename}</a>
                  </p>
                )}
                {i.kind === "link" && (
                  <p style={{ margin: "4px 0 0", overflowWrap: "anywhere" }}>
                    <a href={i.url} target="_blank" rel="noopener noreferrer">
                      {i.url}
                    </a>
                  </p>
                )}
                {i.source && (
                  <p className="muted small" style={{ margin: "2px 0 0" }}>
                    Source: {i.source}
                  </p>
                )}
              </li>
            ))}
          </ul>
          {teaching &&
            (item?.module === m.id ? (
              <form className="stack sub-form" onSubmit={addItem}>
                <label>
                  Title
                  <input id={`item-title-${m.id}`} value={item.title} onChange={(e) => setItem({ ...item, title: e.target.value })} required />
                </label>
                {item.kind === "page" && (
                  <label>
                    Text
                    <textarea id={`item-body-${m.id}`} value={item.body} onChange={(e) => setItem({ ...item, body: e.target.value })} />
                  </label>
                )}
                {item.kind === "file" && (
                  <label>
                    File (PDF, photograph, Word, Excel or PowerPoint)
                    <input
                      id={`item-file-${m.id}`}
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png,.webp,.heic,.heif,.docx,.xlsx,.pptx"
                      onChange={(e) => setItem({ ...item, file: e.target.files?.[0] ?? null })}
                      required
                    />
                  </label>
                )}
                {item.kind === "link" && (
                  <label>
                    Web address
                    <input
                      id={`item-url-${m.id}`}
                      type="url"
                      inputMode="url"
                      placeholder="https://"
                      value={item.url}
                      onChange={(e) => setItem({ ...item, url: e.target.value })}
                      required
                    />
                  </label>
                )}
                <label>
                  Whose material is this?
                  <select id={`item-licence-${m.id}`} value={item.licence} onChange={(e) => setItem({ ...item, licence: e.target.value as Licence })} required>
                    <option value="" disabled>
                      Choose…
                    </option>
                    {LICENCES.map((l) => (
                      <option key={l.value} value={l.value}>
                        {l.label}
                      </option>
                    ))}
                  </select>
                </label>
                {item.licence === "open_licence" && (
                  <label>
                    Which open licence
                    <select id={`item-open-${m.id}`} value={item.open_licence} onChange={(e) => setItem({ ...item, open_licence: e.target.value })} required>
                      <option value="" disabled>
                        Choose…
                      </option>
                      {OPEN_LICENCES.map((l) => (
                        <option key={l.value} value={l.value}>
                          {l.label}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {item.licence !== "" && item.licence !== "gsa_own" && (
                  <label>
                    Source and credit
                    <input
                      id={`item-source-${m.id}`}
                      value={item.source}
                      placeholder="Author, title, where it comes from"
                      onChange={(e) => setItem({ ...item, source: e.target.value })}
                      required
                    />
                  </label>
                )}
                <div className="actions">
                  <button type="button" className="secondary" onClick={() => setItem(null)}>
                    Cancel
                  </button>
                  <button type="submit" disabled={saving}>
                    {saving ? "Saving…" : ADD_LABEL[item.kind]}
                  </button>
                </div>
              </form>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
                <button className="secondary" onClick={() => setItem(blankDraft(m.id, "page"))}>
                  Add a page
                </button>
                <button className="secondary" onClick={() => setItem(blankDraft(m.id, "file"))}>
                  Upload a file
                </button>
                <button className="secondary" onClick={() => setItem(blankDraft(m.id, "link"))}>
                  Add a link
                </button>
              </div>
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
  const [queued, setQueued] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (file) {
        // A file cannot be kept on the device: work with one attached needs a connection.
        const body = new FormData();
        if (text) body.set("text", text);
        body.set("file", file);
        await post(`/assignments/${assignment.id}/submit/`, body);
        onChanged();
        return;
      }
      // A typed answer is safe to send again (it replaces work not yet marked), so without a connection it
      // waits on this device and is sent when the connection returns (item 4.02).
      const sent = await submitAssignmentText(assignment.id, assignment.title, text);
      if (sent.queued) setQueued(sent.item.id);
      else onChanged();
    } catch (err) {
      setError(
        err instanceof TypeError ? "No connection. Attach the file again when you are back online." : errorMessage(err, "Could not submit."),
      );
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
        <SendState id={queued} />
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
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {/* Focusable and named, so a keyboard user can scroll a table wider than a phone. */}
      <div className="scroll-x" tabIndex={0} role="region" aria-label={`Submissions for ${assignment.title}`}>
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
                    {/* Sent later from a phone without signal: the server's time decides lateness, and the device's
                        is shown so a lecturer can excuse it with an extension (item 4.02). */}
                    <span className="muted small" style={{ display: "block" }}>
                      Received {dmyTime(row.submitted_at)}
                      {row.client_submitted_at && ` · handed in on the device ${dmyTime(row.client_submitted_at)}`}
                    </span>
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
      </div>
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
    // Focusable and named, so a keyboard user can scroll a gradebook wider than the screen.
    <div className="scroll-x" tabIndex={0} role="region" aria-label="Gradebook">
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
