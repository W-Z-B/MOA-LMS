import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { Forum, ForumType, PostReport } from "../../api/types-talk";
import { dmyTime, plural } from "../../app/format";
import { FORUM_TYPE, rows } from "./shared";
import "../talk.css";

/** The forums of a list, each a link to its threads: #/forums/3. */
export function ForumList({ forums, empty }: { forums: Forum[]; empty: string }) {
  if (forums.length === 0) return <p className="muted">{empty}</p>;
  return (
    <ul className="talk-list" aria-label="Forums">
      {forums.map((forum) => (
        <li key={forum.id}>
          <a className="talk-row" href={`#/forums/${forum.id}`}>
            <span className="talk-row-main">
              <span className="talk-title">{forum.title}</span>
              <span className="muted small">
                {FORUM_TYPE[forum.forum_type].label} · {plural(forum.threads, "discussion", "discussions")}
                {forum.subscribed ? " · You get notices" : ""}
              </span>
            </span>
            {!forum.is_published && <span className="pill">Draft</span>}
          </a>
        </li>
      ))}
    </ul>
  );
}

/**
 * Reports waiting for a moderator (item 4.09): each opens the post in its thread, and is decided there or
 * here: remove the post (the note is the reason everyone sees) or keep it and show it again.
 */
export function ReportsQueue({ siteId }: { siteId?: number }) {
  const [reports, setReports] = useState<PostReport[] | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<PostReport> | PostReport[]>("/post-reports/?status=open")
      .then((answer) => setReports(rows(answer).filter((r) => siteId === undefined || r.site === siteId)))
      .catch((err) => setError(errorMessage(err, "Could not load the reports.")));
  }, [siteId]);

  useEffect(load, [load]);

  async function decide(report: PostReport, decision: "remove" | "keep") {
    const note = (notes[report.id] ?? "").trim();
    if (decision === "remove" && !note) {
      setError("Say why the post is removed: the reason is shown in its place.");
      return;
    }
    try {
      await post(`/post-reports/${report.id}/review/`, { decision, note });
      setError(null);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not decide the report."));
    }
  }

  if (reports === null || (reports.length === 0 && !error)) return null;
  return (
    <section className="module" aria-labelledby="reports-title">
      <h3 id="reports-title">Reports waiting for review</h3>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <ul className="plain">
        {reports.map((report) => (
          <li key={report.id} className="report">
            <p className="talk-quote">“{report.reason}”</p>
            <p className="muted small">
              Reported {dmyTime(report.created_at)} ·{" "}
              <a href={`#/forums/${report.forum}/threads/${report.thread}`}>Open the post</a>
            </p>
            <label>
              Reason or note
              <input
                value={notes[report.id] ?? ""}
                maxLength={300}
                onChange={(e) => setNotes((prev) => ({ ...prev, [report.id]: e.target.value }))}
              />
            </label>
            <div className="actions">
              <button className="danger" onClick={() => decide(report, "remove")}>
                Remove the post
              </button>
              <button className="secondary" onClick={() => decide(report, "keep")}>
                Keep the post
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

interface Draft {
  title: string;
  forum_type: ForumType;
  description: string;
  max_mark: string;
  weight: string;
}

const BLANK: Draft = { title: "", forum_type: "general", description: "", max_mark: "10", weight: "0" };

/** Teaching staff add a forum: general, question and answer, or graded with a participation mark. */
function NewForum({ siteId, onMade }: { siteId: number; onMade: () => void }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!draft)
    return (
      <button className="secondary" onClick={() => setDraft(BLANK)}>
        New forum
      </button>
    );

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!draft) return;
    const graded = draft.forum_type === "graded";
    try {
      await post("/forums/", {
        site: siteId,
        title: draft.title,
        forum_type: draft.forum_type,
        description: draft.description,
        body_format: "text",
        ...(graded ? { max_mark: draft.max_mark, weight: draft.weight } : {}),
      });
      setDraft(null);
      setError(null);
      onMade();
    } catch (err) {
      setError(errorMessage(err, "Could not add the forum."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={save}>
      <h3>New forum</h3>
      <label>
        Title
        <input required maxLength={160} value={draft.title} onChange={(e) => setDraft((prev) => prev && ({ ...prev, title: e.target.value }))} />
      </label>
      <label>
        Kind of forum
        <select value={draft.forum_type} onChange={(e) => setDraft((prev) => prev && ({ ...prev, forum_type: e.target.value as ForumType }))}>
          {(Object.keys(FORUM_TYPE) as ForumType[]).map((kind) => (
            <option key={kind} value={kind}>
              {FORUM_TYPE[kind].label}
            </option>
          ))}
        </select>
      </label>
      <p className="muted small">{FORUM_TYPE[draft.forum_type].explain}</p>
      <label>
        What it is for (optional)
        <textarea rows={3} value={draft.description} onChange={(e) => setDraft((prev) => prev && ({ ...prev, description: e.target.value }))} />
      </label>
      {draft.forum_type === "graded" && (
        <div className="grid2">
          <label>
            Participation mark out of
            <input type="number" min="1" step="0.5" value={draft.max_mark} onChange={(e) => setDraft((prev) => prev && ({ ...prev, max_mark: e.target.value }))} />
          </label>
          <label>
            Weight in coursework
            <input type="number" min="0" step="0.5" value={draft.weight} onChange={(e) => setDraft((prev) => prev && ({ ...prev, weight: e.target.value }))} />
          </label>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="button" className="secondary" onClick={() => setDraft(null)}>
          Cancel
        </button>
        <button type="submit">Add forum</button>
      </div>
    </form>
  );
}

/** A course site's Discussion tab (items 4.08 to 4.10): its forums, a new forum and the reports to review. */
export function DiscussionTab({ siteId, teaching }: { siteId: number; teaching: boolean }) {
  const [forums, setForums] = useState<Forum[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Forum[]>(`/forums/?site=${siteId}`)
      .then((f) => {
        setForums(f);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load the forums.")));
  }, [siteId]);

  useEffect(load, [load]);

  return (
    <>
      {teaching && <ReportsQueue siteId={siteId} />}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {forums === null && !error ? (
        <p className="loading">Loading forums…</p>
      ) : (
        <ForumList forums={forums ?? []} empty={teaching ? "No forums yet. Add one for the class." : "No forums on this course yet."} />
      )}
      {teaching && (
        <div className="talk-foot">
          <NewForum siteId={siteId} onMade={load} />
        </div>
      )}
    </>
  );
}
