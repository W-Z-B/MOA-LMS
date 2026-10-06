import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import { canTeach } from "../../api/types";
import type { Forum, ParticipationRow, Thread } from "../../api/types-talk";
import { useCrumb } from "../../app/frame";
import { dmyTime, plural, when } from "../../app/format";
import { Composer } from "./Composer";
import { ConductGate } from "./Conduct";
import { isConductRefusal } from "./conductStatement";
import { toHtml } from "./markup";
import { FORUM_TYPE, useSites } from "./shared";
import "../talk.css";

interface Props {
  forumId: number;
  onNavigate: (to: string) => void;
}

/** Subscribe or stop: notices of every new post (item 4.08). */
export function SubscribeButton({ subscribed, path, onChange }: { subscribed: boolean; path: string; onChange: (on: boolean) => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <button
      className="secondary"
      aria-pressed={subscribed}
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          const answer = await post<{ subscribed: boolean }>(`${path}/${subscribed ? "unsubscribe" : "subscribe"}/`);
          onChange(answer.subscribed);
        } catch {
          /* the button stays as it was */
        } finally {
          setBusy(false);
        }
      }}
    >
      {subscribed ? "Stop notices" : "Get notices of new posts"}
    </button>
  );
}

function StartThread({ forum, onStarted }: { forum: Forum; onStarted: (thread: Thread) => void }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [recheck, setRecheck] = useState(0);
  const [busy, setBusy] = useState(false);
  const question = forum.forum_type === "question";

  if (!open)
    return <button onClick={() => setOpen(true)}>{question ? "Ask a question" : "Start a discussion"}</button>;

  async function start(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const thread = await post<Thread>(`/forums/${forum.id}/threads/`, { title, body: toHtml(text), body_format: "html" });
      onStarted(thread);
    } catch (err) {
      if (isConductRefusal(err)) setRecheck((n) => n + 1);
      setError(errorMessage(err, "Could not start the discussion."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ConductGate doing="post" recheckKey={recheck}>
      <form className="stack sub-form" onSubmit={start}>
        <h3>{question ? "Ask a question" : "Start a discussion"}</h3>
        <label>
          Title
          <input required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <Composer label={question ? "The question" : "Your post"} value={text} onChange={setText} />
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="button" className="secondary" onClick={() => setOpen(false)}>
            Cancel
          </button>
          <button type="submit" disabled={busy || !text.trim()}>
            Post
          </button>
        </div>
      </form>
    </ConductGate>
  );
}

/** Graded discussion (item 4.10): each student's posts, a mark out of the forum's maximum, and release. */
function ParticipationMarks({ forum }: { forum: Forum }) {
  const [marks, setMarks] = useState<ParticipationRow[]>([]);
  const [entries, setEntries] = useState<Record<number, { mark: string; feedback: string }>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<ParticipationRow[]>(`/forums/${forum.id}/marks/`)
      .then((list) => {
        setMarks(list);
        setEntries(Object.fromEntries(list.map((r) => [r.person_id, { mark: r.mark ?? "", feedback: r.feedback }])));
      })
      .catch((err) => setError(errorMessage(err, "Could not load the participation marks.")));
  }, [forum.id]);

  useEffect(load, [load]);

  async function save(row: ParticipationRow) {
    const entry = entries[row.person_id];
    try {
      await post(`/forums/${forum.id}/marks/`, { student: row.person_id, mark: entry.mark, feedback: entry.feedback });
      setError(null);
      setMessage(`Saved ${row.name}'s mark.`);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not save the mark."));
    }
  }

  async function release() {
    try {
      const answer = await post<{ released: number }>(`/forums/${forum.id}/release-marks/`);
      setMessage(`${plural(answer.released, "mark", "marks")} released to students.`);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not release the marks."));
    }
  }

  return (
    <section aria-labelledby="marks-title">
      <h2 id="marks-title">Participation marks</h2>
      <p className="muted small">Out of {forum.max_mark}. Students see a mark once it is released.</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="notice good">
          {message}
        </p>
      )}
      {marks.length === 0 ? (
        <p className="muted">No students on this course.</p>
      ) : (
        <ul className="talk-list marks" aria-label="Students">
          {marks.map((row) => {
            const entry = entries[row.person_id] ?? { mark: "", feedback: "" };
            return (
              <li key={row.person_id} className="mark-row">
                <span className="talk-row-main">
                  <span className="talk-title">
                    {row.name} <span className="muted small">{row.student_no}</span>
                  </span>
                  <span className="muted small">
                    {plural(row.posts, "post", "posts")}
                    {row.mark !== null && (row.is_released ? " · Released" : " · Not released")}
                  </span>
                </span>
                <label>
                  Mark for {row.name}
                  <input
                    type="number"
                    min="0"
                    max={forum.max_mark}
                    step="0.5"
                    value={entry.mark}
                    onChange={(e) => setEntries({ ...entries, [row.person_id]: { ...entry, mark: e.target.value } })}
                  />
                </label>
                <label className="grow">
                  Feedback for {row.name}
                  <input
                    value={entry.feedback}
                    onChange={(e) => setEntries({ ...entries, [row.person_id]: { ...entry, feedback: e.target.value } })}
                  />
                </label>
                <button className="secondary" disabled={!entry.mark} onClick={() => save(row)}>
                  Save
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <div className="actions talk-foot">
        <button onClick={release}>Release marks to students</button>
      </div>
    </section>
  );
}

function MyParticipation({ forum }: { forum: Forum }) {
  const [mine, setMine] = useState<ParticipationRow | null>(null);
  useEffect(() => {
    get<ParticipationRow[]>(`/forums/${forum.id}/marks/`)
      .then((list) => setMine(list[0] ?? null))
      .catch(() => setMine(null));
  }, [forum.id]);
  if (!mine) return null;
  return (
    <p className="notice">
      {mine.mark !== null
        ? `Your participation mark: ${mine.mark} out of ${forum.max_mark}.${mine.feedback ? ` ${mine.feedback}` : ""}`
        : `You have ${plural(mine.posts, "post", "posts")} here. Your participation mark shows once it is released.`}
    </p>
  );
}

/** One forum (#/forums/3): what it is for, its discussions, and for a graded forum the marks. */
export function ForumScreen({ forumId, onNavigate }: Props) {
  const sites = useSites();
  const [forum, setForum] = useState<Forum | null>(null);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [error, setError] = useState<string | null>(null);
  useCrumb(forum?.title);

  const load = useCallback(() => {
    Promise.all([get<Forum>(`/forums/${forumId}/`), get<Thread[]>(`/forums/${forumId}/threads/`)])
      .then(([f, t]) => {
        setForum(f);
        setThreads(t);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not open this forum.")));
  }, [forumId]);

  useEffect(load, [load]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!forum) return <p className="loading">Opening forum…</p>;
  const site = sites.find((s) => s.id === forum.site);
  const teaching = canTeach(site?.my_role ?? null);
  const mayStart = site !== undefined && site.my_role !== "auditor" && (forum.forum_type !== "question" || teaching);

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          {site && (
            <a className="eyebrow" href={`#/sites/${site.id}/discussion`}>
              {site.title}
            </a>
          )}
          <h1>{forum.title}</h1>
          <p className="muted">
            {FORUM_TYPE[forum.forum_type].label}. {FORUM_TYPE[forum.forum_type].explain}
          </p>
        </div>
        <SubscribeButton subscribed={forum.subscribed} path={`/forums/${forum.id}`} onChange={(on) => setForum({ ...forum, subscribed: on })} />
      </div>
      {/* Cleaned on the server against an allow-list (courses.richtext). */}
      {forum.description && <div className="page-body" dangerouslySetInnerHTML={{ __html: forum.description }} />}
      {forum.forum_type === "graded" && !teaching && <MyParticipation forum={forum} />}

      {threads.length === 0 ? (
        <p className="muted">No discussions yet.</p>
      ) : (
        <ul className="talk-list" aria-label="Discussions">
          {threads.map((thread) => (
            <li key={thread.id}>
              <a className="talk-row" href={`#/forums/${forum.id}/threads/${thread.id}`}>
                <span className="talk-row-main">
                  <span className="talk-title">{thread.title}</span>
                  <span className="muted small">
                    {thread.author_name ?? "Someone"} · {plural(thread.replies, "reply", "replies")}
                    {thread.last_post_at ? ` · last post ${when(thread.last_post_at)}` : ` · ${dmyTime(thread.created_at)}`}
                  </span>
                </span>
                {thread.is_pinned && <span className="pill">Pinned</span>}
                {thread.is_locked && <span className="pill">Locked</span>}
              </a>
            </li>
          ))}
        </ul>
      )}
      {mayStart && (
        <div className="talk-foot">
          <StartThread forum={forum} onStarted={(thread) => onNavigate(`/forums/${forum.id}/threads/${thread.id}`)} />
        </div>
      )}
      {forum.forum_type === "graded" && teaching && <ParticipationMarks forum={forum} />}
    </>
  );
}
