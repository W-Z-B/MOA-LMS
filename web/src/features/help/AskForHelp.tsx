import { useState, type FormEvent } from "react";
import { errorMessage } from "../../api/client";
import type { HelpRequest } from "../../api/types-help";
import { useCrumb } from "../../app/frame";
import { sendOrQueue } from "../../app/offlineQueue";
import { SendState } from "../../app/SendState";
import "./help.css";

interface Props {
  /** The address the person asked from, which is sent with the question when they leave it ticked. */
  from: string;
  onNavigate: (to: string) => void;
}

/**
 * Ask for help (item 7.17): a question and the page the person was on, sent to the course administrators. On
 * a phone without signal it waits on the phone and is sent when the signal returns (it carries an
 * Idempotency-Key, so it is never sent twice).
 */
export function AskForHelp({ from, onNavigate }: Props) {
  useCrumb("Ask for help");
  const page = from.startsWith("/") && !from.startsWith("/help") ? from : "";
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [sendPage, setSendPage] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<{ queued: string | null } | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const outcome = await sendOrQueue<HelpRequest>({
        kind: "help",
        method: "POST",
        path: "/help-requests/",
        body: { subject, message, page: sendPage ? page : "", client_sent_at: new Date().toISOString() },
        label: `Help request: ${subject}`,
      });
      setSent({ queued: outcome.queued ? outcome.item.id : null });
    } catch (err) {
      setError(errorMessage(err, "Your request could not be sent. Try again."));
    } finally {
      setBusy(false);
    }
  }

  if (sent)
    return (
      <>
        <h1>Ask for help</h1>
        {sent.queued ? (
          <p className="notice">
            Your request is kept on this phone. <SendState id={sent.queued} />
          </p>
        ) : (
          <p role="status" className="notice good">
            Sent. The course administrators have your request; their answer comes to you as a notification.
          </p>
        )}
        <p className="help-foot">
          <a href="#/help/requests">My help requests</a>
          {page && (
            <a
              href={`#${page}`}
              onClick={(e) => {
                e.preventDefault();
                onNavigate(page);
              }}
            >
              Back to the page I was on
            </a>
          )}
        </p>
      </>
    );

  return (
    <>
      <h1>Ask for help</h1>
      <p className="lead">
        Your question goes to the course administrators. For a question about a course&apos;s work, write to its lecturer from Messages
        instead.
      </p>
      <form className="help-form panel-card padded" onSubmit={send}>
        <label>
          What do you need help with?
          <input required maxLength={160} value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="For example: I cannot find my quiz" />
        </label>
        <label>
          What were you trying to do, and what happened?
          <textarea required maxLength={4000} rows={6} value={message} onChange={(e) => setMessage(e.target.value)} />
        </label>
        {page && (
          <label className="check">
            <input type="checkbox" checked={sendPage} onChange={(e) => setSendPage(e.target.checked)} />
            <span>
              Send the page I was on: <code>{page}</code>
            </span>
          </label>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div>
          <button type="submit" disabled={busy}>
            {busy ? "Sending…" : "Send to the course administrators"}
          </button>
        </div>
        <p className="muted small">Without signal, it waits on this phone and is sent when the signal returns.</p>
      </form>
    </>
  );
}
