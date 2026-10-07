import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import type { Forum, Post, ThreadDetail } from "../../api/types-talk";
import { useCrumb } from "../../app/frame";
import { clock } from "./shared";
import { dmyTime } from "../../app/format";
import { Composer } from "./Composer";
import { ConductGate } from "./Conduct";
import { isConductRefusal } from "./conductStatement";
import { SubscribeButton } from "./ForumScreen";
import { toHtml, toText } from "./markup";
import "../talk.css";

interface Props {
  forumId: number;
  threadId: number;
}

type Open = { kind: "edit" | "remove" | "report"; post: number } | null;

/** Thirty minutes after posting (FORUM_EDIT_MINUTES): until then the author may change or remove a post. */
const EDIT_MINUTES = 30;

/** A discussion (#/forums/3/threads/7): the opening post, replies under what they answer, and moderation. */
export function ThreadScreen({ forumId, threadId }: Props) {
  const [data, setData] = useState<ThreadDetail | null>(null);
  const [forum, setForum] = useState<Forum | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [open, setOpen] = useState<Open>(null);
  const [text, setText] = useState("");
  const [reason, setReason] = useState("");
  const [replyTo, setReplyTo] = useState<Post | null>(null);
  const [reply, setReply] = useState("");
  const [recheck, setRecheck] = useState(0);
  const [busy, setBusy] = useState(false);
  const composer = useRef<HTMLDivElement>(null);
  useCrumb(data?.thread.title);

  const load = useCallback(() => {
    get<ThreadDetail>(`/threads/${threadId}/`)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not open this discussion.")));
  }, [threadId]);

  useEffect(load, [load]);
  useEffect(() => {
    get<Forum>(`/forums/${forumId}/`)
      .then(setForum)
      .catch(() => setForum(null));
  }, [forumId]);

  if (error && !data)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!data) return <p className="loading">Opening discussion…</p>;
  const { thread, moderator } = data;
  const question = forum?.forum_type === "question";
  const opening = data.posts.find((p) => p.parent === null);
  const children = (id: number) => data.posts.filter((p) => p.parent === id);
  const mayReply = !thread.is_locked || moderator;

  async function act(run: () => Promise<unknown>, done: string, fallback: string) {
    setBusy(true);
    try {
      await run();
      setOpen(null);
      setText("");
      setReason("");
      setNotice(done);
      setError(null);
      load();
    } catch (err) {
      setError(errorMessage(err, fallback));
    } finally {
      setBusy(false);
    }
  }

  async function sendReply(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await post(`/threads/${threadId}/replies/`, {
        body: toHtml(reply),
        body_format: "html",
        ...(replyTo && replyTo.id !== opening?.id ? { parent: replyTo.id } : {}),
      });
      setReply("");
      setReplyTo(null);
      setNotice(question && data?.replies_hidden ? "Your answer is posted. Others' answers are shown now." : "Your reply is posted.");
      setError(null);
      load();
    } catch (err) {
      if (isConductRefusal(err)) setRecheck((n) => n + 1);
      setError(errorMessage(err, "Could not post the reply."));
    } finally {
      setBusy(false);
    }
  }

  function startReply(to: Post) {
    setReplyTo(to);
    requestAnimationFrame(() => {
      composer.current?.scrollIntoView?.({ block: "center" });
      composer.current?.querySelector("textarea")?.focus();
    });
  }

  const FLAGGED = { pin: ["The discussion is pinned to the top.", "The discussion is unpinned."], lock: ["The discussion is locked.", "The discussion is unlocked."] };
  const flag = (field: "pin" | "lock", value: boolean) =>
    act(() => post(`/threads/${threadId}/${field}/`, { value }), FLAGGED[field][value ? 0 : 1], "Could not change the discussion.");

  // A plain function, not a component: the forms inside keep their focus as the page renders again.
  function postView(item: Post, depth: number) {
    const mine = item.can_edit;
    const editing = open?.post === item.id && open.kind === "edit";
    const removing = open?.post === item.id && open.kind === "remove";
    const reporting = open?.post === item.id && open.kind === "report";
    return (
      <li key={item.id} className={`post depth-${Math.min(depth, 3)}`}>
        <article aria-label={`Post by ${item.author_name ?? "someone"}`}>
          <p className="post-meta">
            <strong>{item.author_name ?? "Someone"}</strong>{" "}
            <span className="muted small">
              {dmyTime(item.created_at)}
              {item.edited_at ? " · changed" : ""}
            </span>{" "}
            {item.hidden && !item.removed && <span className="pill">Hidden while a report is reviewed</span>}
          </p>
          {item.removed ? (
            <p className="muted post-removed">
              This post was removed{item.removed_reason ? `: ${item.removed_reason}` : "."}
            </p>
          ) : editing ? (
            <form
              className="stack"
              onSubmit={(e) => {
                e.preventDefault();
                act(() => patch(`/posts/${item.id}/`, { body: toHtml(text), body_format: "html" }), "Your post is changed.", "Could not change the post.");
              }}
            >
              <Composer label="Change your post" value={text} onChange={setText} autoFocus />
              <div className="actions">
                <button type="button" className="secondary" onClick={() => setOpen(null)}>
                  Cancel
                </button>
                <button type="submit" disabled={busy || !text.trim()}>
                  Save
                </button>
              </div>
            </form>
          ) : item.body ? (
            // Cleaned on the server against an allow-list (courses.richtext).
            <div className="page-body post-body" dangerouslySetInnerHTML={{ __html: item.body }} />
          ) : (
            <p className="muted">This post is hidden while a moderator reviews a report.</p>
          )}
          {mine && !editing && (
            <p className="muted small">You can change or remove your post until {clock(new Date(new Date(item.created_at).getTime() + EDIT_MINUTES * 60_000).toISOString())}.</p>
          )}
          {!item.removed && !editing && (
            <div className="actions post-actions">
              {mayReply && (!data!.replies_hidden || item.id === opening?.id) && (
                <button className="link accent" onClick={() => startReply(item)}>
                  Reply
                </button>
              )}
              {mine && (
                <button
                  className="link accent"
                  onClick={() => {
                    setText(toText(item.body));
                    setOpen({ kind: "edit", post: item.id });
                  }}
                >
                  Change
                </button>
              )}
              {(mine || moderator) && (
                <button className="link accent" onClick={() => setOpen({ kind: "remove", post: item.id })}>
                  Remove
                </button>
              )}
              {!mine && (
                <button className="link accent" onClick={() => setOpen({ kind: "report", post: item.id })}>
                  Report
                </button>
              )}
            </div>
          )}
          {removing && (
            <form
              className="stack sub-form"
              onSubmit={(e) => {
                e.preventDefault();
                act(() => post(`/posts/${item.id}/remove/`, { reason }), "The post is removed.", "Could not remove the post.");
              }}
            >
              {mine && !moderator ? (
                <p>Remove your post? It is shown as removed.</p>
              ) : (
                <label>
                  Why is it removed? Everyone sees the reason in its place.
                  <input required={!mine} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
                </label>
              )}
              <div className="actions">
                <button type="button" className="secondary" onClick={() => setOpen(null)}>
                  Cancel
                </button>
                <button type="submit" className="danger" disabled={busy}>
                  Remove post
                </button>
              </div>
            </form>
          )}
          {reporting && (
            <form
              className="stack sub-form"
              onSubmit={(e) => {
                e.preventDefault();
                act(
                  () => post(`/posts/${item.id}/report/`, { reason }),
                  moderator ? "Reported. The post is hidden from students until the report is decided." : "Reported. A moderator will review it.",
                  "Could not report the post.",
                );
              }}
            >
              <label>
                Which rule does it break?
                <textarea required rows={2} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} />
              </label>
              <div className="actions">
                <button type="button" className="secondary" onClick={() => setOpen(null)}>
                  Cancel
                </button>
                <button type="submit" disabled={busy || !reason.trim()}>
                  Send report
                </button>
              </div>
            </form>
          )}
        </article>
        {children(item.id).length > 0 && (
          <ul className="posts">
            {children(item.id).map((child) => postView(child, depth + 1))}
          </ul>
        )}
      </li>
    );
  }

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          {forum && (
            <a className="eyebrow" href={`#/forums/${forum.id}`}>
              {forum.title}
            </a>
          )}
          <h1>{thread.title}</h1>
          <p className="muted">
            {thread.is_pinned && <span className="pill">Pinned</span>} {thread.is_locked && <span className="pill">Locked</span>}
          </p>
        </div>
        <div className="actions">
          <SubscribeButton subscribed={data.subscribed} path={`/threads/${threadId}`} onChange={(on) => setData((prev) => prev && ({ ...prev, subscribed: on }))} />
          {moderator && (
            <>
              <button className="secondary" onClick={() => flag("pin", !thread.is_pinned)}>
                {thread.is_pinned ? "Unpin" : "Pin to the top"}
              </button>
              <button className="secondary" onClick={() => flag("lock", !thread.is_locked)}>
                {thread.is_locked ? "Unlock" : "Lock"}
              </button>
            </>
          )}
        </div>
      </div>
      {data.replies_hidden && (
        <p className="notice">This is a question-and-answer forum: post your answer to see what others have written.</p>
      )}
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
      {opening && (
        <ul className="posts root">
          {postView(opening, 0)}
        </ul>
      )}
      <div className="talk-foot" ref={composer}>
        {!mayReply ? (
          <p className="notice">This discussion is locked: no new replies.</p>
        ) : (
          <ConductGate doing="post" recheckKey={recheck}>
            <form className="stack" onSubmit={sendReply}>
              {replyTo && replyTo.id !== opening?.id && (
                <p className="muted small">
                  Replying to {replyTo.author_name ?? "a post"}.{" "}
                  <button type="button" className="link accent" onClick={() => setReplyTo(null)}>
                    Reply to the discussion instead
                  </button>
                </p>
              )}
              <Composer label={question ? "Your answer" : "Your reply"} value={reply} onChange={setReply} rows={4} />
              <div className="actions">
                <button type="submit" disabled={busy || !reply.trim()}>
                  {question ? "Post your answer" : "Post reply"}
                </button>
              </div>
            </form>
          </ConductGate>
        )}
      </div>
    </>
  );
}
