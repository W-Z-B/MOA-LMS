import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import { canTeach, type Paginated } from "../../api/types";
import type { Audience, Conversation, ConversationDetail, Recipient, SiteGroup } from "../../api/types-talk";
import { dmyTime, when } from "../../app/format";
import { useCrumb } from "../../app/frame";
import { isNetworkError, sendOrQueue, usePending, type QueuedWrite } from "../../app/offlineQueue";
import { SendState } from "../../app/SendState";
import { Composer } from "../forums/Composer";
import { ConductGate } from "../forums/Conduct";
import { isConductRefusal } from "../forums/conductStatement";
import { toHtml } from "../forums/markup";
import { rows, useSites } from "../forums/shared";
import "../talk.css";

interface Props {
  conversationId: number | null;
  /** The address's query: ?site=4 opens a new message to that course's teaching staff. */
  query: string;
  onNavigate: (to: string) => void;
}

const AUDIENCE: Record<Audience, string> = {
  direct: "Conversation",
  group: "Notice to a group",
  site: "Notice to the whole course",
};

/** A message to send, through the offline queue with an Idempotency-Key (items 4.02, 4.11). */
function send<T>(path: string, body: Record<string, unknown>, label: string) {
  return sendOrQueue<T>({
    kind: "message",
    method: "POST",
    path,
    body: { ...body, body_format: "html", client_sent_at: new Date().toISOString() },
    label,
  });
}

/** A new conversation: a student to the course's teaching staff; staff to people, a group or the whole course. */
function NewMessage({ initialSite, onSent, onCancel }: { initialSite: number | null; onSent: (c: Conversation | null, queued: QueuedWrite | null) => void; onCancel: () => void }) {
  const sites = useSites().filter((s) => s.my_role && s.my_role !== "auditor");
  const [picked, setPicked] = useState<number | null>(initialSite);
  // Someone on one course only writes on it without choosing.
  const siteId = picked ?? (sites.length === 1 ? sites[0].id : null);
  const [loaded, setLoaded] = useState<{ site: number; recipients: Recipient[]; groups: SiteGroup[] } | null>(null);
  const recipients = loaded?.site === siteId ? loaded.recipients : [];
  const groups = loaded?.site === siteId ? loaded.groups : [];
  const [chosen, setChosen] = useState<number[]>([]);
  const [audience, setAudience] = useState<Audience>("direct");
  const [group, setGroup] = useState("");
  const [subject, setSubject] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [recheck, setRecheck] = useState(0);
  const [busy, setBusy] = useState(false);
  const site = sites.find((s) => s.id === siteId) ?? null;
  const teaching = canTeach(site?.my_role ?? null);

  useEffect(() => {
    if (siteId === null) return;
    const groupsOf = teaching
      ? get<Paginated<SiteGroup> | SiteGroup[]>(`/groups/?site=${siteId}`).then(rows).catch(() => [] as SiteGroup[])
      : Promise.resolve([] as SiteGroup[]);
    Promise.all([get<Recipient[]>(`/conversations/recipients/?site=${siteId}`).catch(() => [] as Recipient[]), groupsOf]).then(
      ([people, sets]) => setLoaded({ site: siteId, recipients: people, groups: sets }),
    );
  }, [teaching, siteId]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (siteId === null) return;
    setBusy(true);
    try {
      const sent = await send<Conversation>(
        "/conversations/",
        {
          site: siteId,
          audience: teaching ? audience : "direct",
          subject,
          body: toHtml(text),
          ...(audience === "direct" || !teaching ? { recipients: chosen } : {}),
          ...(teaching && audience === "group" ? { group: Number(group) } : {}),
        },
        `Message: ${subject}`,
      );
      onSent(sent.queued ? null : sent.result, sent.queued ? sent.item : null);
    } catch (err) {
      if (isConductRefusal(err)) setRecheck((n) => n + 1);
      setError(errorMessage(err, "Could not send the message."));
    } finally {
      setBusy(false);
    }
  }

  const toggle = (id: number) => setChosen(chosen.includes(id) ? chosen.filter((c) => c !== id) : [...chosen, id]);

  return (
    <ConductGate doing="send a message" recheckKey={recheck}>
      <form className="stack module" onSubmit={submit}>
        <h2 className="talk-form-title">New message</h2>
        <label>
          Course
          <select required value={siteId ?? ""} onChange={(e) => {
              setPicked(e.target.value ? Number(e.target.value) : null);
              setChosen([]);
            }}>
            <option value="">Choose a course</option>
            {sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
        </label>
        {site && teaching && (
          <fieldset>
            <legend>Send to</legend>
            {(["direct", "group", "site"] as Audience[]).map((a) => (
              <label key={a} className="inline">
                <input type="radio" name="audience" checked={audience === a} onChange={() => setAudience(a)} />
                {a === "direct" ? "People I choose" : a === "group" ? "A group, as a notice" : "The whole course, as a notice"}
              </label>
            ))}
          </fieldset>
        )}
        {site && teaching && audience === "group" && (
          <label>
            Group
            <select required value={group} onChange={(e) => setGroup(e.target.value)}>
              <option value="">Choose a group</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {site && (audience === "direct" || !teaching) && (
          <fieldset>
            <legend>{teaching ? "To" : "To the teaching staff (none ticked: all of them)"}</legend>
            {recipients.length === 0 && <p className="muted small">Nobody on this course can receive a message yet.</p>}
            <div className="talk-choices">
              {recipients.map((r) => (
                <label key={r.person_id} className="inline">
                  <input type="checkbox" checked={chosen.includes(r.person_id)} onChange={() => toggle(r.person_id)} />
                  {r.name} <span className="muted small">{r.role === "student" ? "Student" : r.role === "assistant" ? "Teaching assistant" : "Lecturer"}</span>
                </label>
              ))}
            </div>
          </fieldset>
        )}
        {teaching && audience !== "direct" && <p className="muted small">Students read a notice but do not reply in it; they write to you instead.</p>}
        <label>
          Subject
          <input required maxLength={200} value={subject} onChange={(e) => setSubject(e.target.value)} />
        </label>
        <Composer label="Message" value={text} onChange={setText} />
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="button" className="secondary" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" disabled={busy || siteId === null || !text.trim()}>
            Send
          </button>
        </div>
      </form>
    </ConductGate>
  );
}

/** Who has read one of my messages: the read receipt (item 4.11). */
function receipt(readBy: string[], others: number): string {
  if (others <= 0) return "";
  if (readBy.length === 0) return "Not read yet";
  if (others === 1) return "Read";
  if (readBy.length <= 3) return `Read by ${readBy.join(", ")}`;
  return `Read by ${readBy.length} of ${others}`;
}

function ConversationView({ id, onNavigate }: { id: number; onNavigate: (to: string) => void }) {
  const [data, setData] = useState<ConversationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [recheck, setRecheck] = useState(0);
  const [lastQueued, setLastQueued] = useState<string | null>(null);
  const path = `/conversations/${id}/messages/`;
  const waiting = usePending().filter((q) => q.path === path);
  const waitingCount = useRef(waiting.length);
  useCrumb(data?.conversation.subject);

  const load = useCallback(() => {
    get<ConversationDetail>(`/conversations/${id}/`)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not open this conversation.")));
  }, [id]);

  useEffect(() => {
    load();
    // Opening it is reading it: the read receipt others see.
    post(`/conversations/${id}/read/`).catch(() => undefined);
  }, [id, load]);

  // A message kept on this device was sent when the connection came back: show it in its place.
  useEffect(() => {
    if (waiting.length < waitingCount.current) load();
    waitingCount.current = waiting.length;
  }, [waiting.length, load]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const sent = await send(path, { body: toHtml(text) }, `Message in ${data?.conversation.subject ?? "a conversation"}`);
      setText("");
      setError(null);
      if (sent.queued) setLastQueued(sent.item.id);
      else load();
    } catch (err) {
      if (isConductRefusal(err)) setRecheck((n) => n + 1);
      setError(errorMessage(err, "Could not send the message."));
    } finally {
      setBusy(false);
    }
  }

  if (error && !data)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!data) return <p className="loading">Opening conversation…</p>;
  const { conversation } = data;
  const others = data.participants.length - 1;
  const names = data.participants.map((p) => p.name).filter(Boolean);

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <span className="eyebrow">
            {conversation.site_code} · {AUDIENCE[conversation.audience]}
          </span>
          <h1>{conversation.subject}</h1>
          <p className="muted small">{names.length <= 6 ? names.join(", ") : `${names.length} people`}</p>
        </div>
      </div>
      <ol className="bubbles" aria-label="Messages">
        {data.messages.map((m) => (
          <li key={m.id} className={m.mine ? "bubble mine" : "bubble"}>
            <p className="bubble-meta">
              <strong>{m.mine ? "You" : (m.sender_name ?? "Someone")}</strong> <span className="muted small">{dmyTime(m.created_at)}</span>
            </p>
            {/* Cleaned on the server against an allow-list (courses.richtext). */}
            <div className="page-body" dangerouslySetInnerHTML={{ __html: m.body }} />
            {m.mine && <p className="muted small bubble-receipt">{receipt(m.read_by, others)}</p>}
          </li>
        ))}
        {waiting.map((q) => (
          <li key={q.id} className="bubble mine waiting">
            <p className="bubble-meta">
              <strong>You</strong>
            </p>
            <div className="page-body" dangerouslySetInnerHTML={{ __html: String((q.body as { body?: string }).body ?? "") }} />
            <SendState id={q.id} />
          </li>
        ))}
      </ol>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!conversation.may_send ? (
        <p className="notice">
          This is a notice from the teaching staff, so it takes no replies.{" "}
          <a
            href={`#/messages?site=${conversation.site}`}
            onClick={(e) => {
              e.preventDefault();
              onNavigate(`/messages?site=${conversation.site}`);
            }}
          >
            Write to the teaching staff
          </a>
        </p>
      ) : (
        <div className="talk-foot">
          <ConductGate doing="send a message" recheckKey={recheck}>
            <form className="stack" onSubmit={submit}>
              <Composer label="Your message" value={text} onChange={setText} rows={3} />
              <div className="actions">
                <button type="submit" disabled={busy || !text.trim()}>
                  Send
                </button>
                {lastQueued && waiting.length === 0 && <SendState id={lastQueued} />}
              </div>
            </form>
          </ConductGate>
        </div>
      )}
    </>
  );
}

/** Messages (#/messages, item 4.11): conversations with the teaching staff of a course, and notices. */
export function MessagesScreen({ conversationId, query, onNavigate }: Props) {
  const params = new URLSearchParams(query);
  const askedSite = params.get("site") ? Number(params.get("site")) : null;
  const [list, setList] = useState<Conversation[] | null>(null);
  const hasList = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [writing, setWriting] = useState(askedSite !== null);
  const [queuedNew, setQueuedNew] = useState<string | null>(null);
  const newOnes = usePending().filter((q) => q.path === "/conversations/");

  const load = useCallback(() => {
    get<Conversation[]>("/conversations/")
      .then((l) => {
        hasList.current = true;
        setList(l);
        setError(null);
      })
      // Without a connection the list last read stays: only a page with nothing to show says so.
      .catch((err) => {
        if (!isNetworkError(err)) setError(errorMessage(err, "Could not load your messages."));
        else if (!hasList.current) setError("No connection. Your messages show when it returns.");
      });
  }, []);

  useEffect(() => {
    if (conversationId === null) load();
  }, [conversationId, load, newOnes.length]);

  if (conversationId !== null) return <ConversationView key={conversationId} id={conversationId} onNavigate={onNavigate} />;

  return (
    <>
      <div className="page-head">
        <h1>Messages</h1>
        {!writing && <button onClick={() => setWriting(true)}>New message</button>}
      </div>
      {writing && (
        <NewMessage
          initialSite={askedSite}
          onCancel={() => setWriting(false)}
          onSent={(conversation, queued) => {
            setWriting(false);
            if (conversation) onNavigate(`/messages/${conversation.id}`);
            else if (queued) setQueuedNew(queued.id);
          }}
        />
      )}
      {queuedNew && <SendState id={queuedNew} />}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {list === null && !error && <p className="loading">Loading messages…</p>}
      {list !== null && list.length === 0 && newOnes.length === 0 && <p className="muted">No messages yet.</p>}
      {list !== null && (list.length > 0 || newOnes.length > 0) && (
        <ul className="talk-list" aria-label="Conversations">
          {newOnes.map((q) => (
            <li key={q.id} className="talk-row">
              <span className="talk-row-main">
                <span className="talk-title">{String((q.body as { subject?: string }).subject ?? q.label)}</span>
                <SendState id={q.id} />
              </span>
            </li>
          ))}
          {list.map((c) => (
            <li key={c.id}>
              <a
                className={c.unread > 0 ? "talk-row unread" : "talk-row"}
                href={`#/messages/${c.id}`}
                onClick={(e) => {
                  e.preventDefault();
                  onNavigate(`/messages/${c.id}`);
                }}
              >
                <span className="talk-row-main">
                  <span className="talk-title">{c.subject}</span>
                  <span className="muted small">
                    {c.site_code}
                    {c.audience !== "direct" ? ` · ${AUDIENCE[c.audience]}` : ""}
                    {c.last_message_at ? ` · ${when(c.last_message_at)}` : ""}
                  </span>
                </span>
                {c.unread > 0 && (
                  <span className="count">
                    {c.unread} <span className="sr-only">unread</span>
                  </span>
                )}
              </a>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
