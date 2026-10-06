import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import { canTeach, type Assignment, type Gradebook, type Paginated, type SiteContents, type Submission } from "../../api/types";
import { dmyTime } from "../../app/format";
import { useCrumb } from "../../app/frame";
import { submitAssignmentText } from "../../app/offlineQueue";
import { SITE_TABS, type SiteTab } from "../../app/router";
import { SendState } from "../../app/SendState";
import { ClassesTab } from "../attendance/ClassesTab";
import { DiscussionTab } from "../forums/DiscussionTab";
import { GroupsTab } from "../groups/GroupsTab";
import { ContentTab } from "../content/ContentTab";

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
  discussion: "Discussion",
  classes: "Classes",
  groups: "Groups",
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
      {tab === "discussion" && <DiscussionTab siteId={siteId} teaching={teaching} />}
      {tab === "classes" && <ClassesTab siteId={siteId} teaching={teaching} />}
      {tab === "groups" && <GroupsTab siteId={siteId} teaching={teaching} />}
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
