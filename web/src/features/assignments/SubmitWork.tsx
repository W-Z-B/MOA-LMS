import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { AssignmentDetail, History, Receipt, WorkSubmission } from "../../api/types-marking";
import { dmyTime } from "../../app/format";
import { submitAssignmentText } from "../../app/offlineQueue";
import { SendState } from "../../app/SendState";
import { FeedbackList, RubricView } from "./Feedback";
import { acceptFor, fileSize, markWords, penaltyRule } from "./words";

interface Props {
  assignment: AssignmentDetail;
  onChanged: () => void;
}

/**
 * A student's side of an assignment (items 2.21, 2.22, 2.35, 3.22): what may be handed in and the late rule,
 * the hand-in itself with several files and the integrity statement, the receipt, the history of every
 * hand-in, and the mark with its penalty, rubric and feedback once released.
 */
export function SubmitWork({ assignment, onChanged }: Props) {
  const mine = assignment.my_submission;
  const [text, setText] = useState(mine?.text ?? "");
  const [files, setFiles] = useState<File[]>([]);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [queued, setQueued] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [receipt, setReceipt] = useState<WorkSubmission | null>(null);
  // When the assignment was opened: what is shown follows the due date as it stood then.
  const [now] = useState(() => Date.now());

  const due = assignment.my_due_at ?? assignment.due_at;
  const late = new Date(due).getTime() < now;
  const closed =
    (late && !assignment.allow_late) ||
    (mine !== null && (mine.mark !== null || !assignment.allow_resubmission || late)) ||
    (assignment.opens_at !== null && new Date(assignment.opens_at).getTime() > now);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSending(true);
    try {
      if (files.length) {
        // Files cannot be kept on the device: work with files attached needs a connection.
        const body = new FormData();
        if (text) body.set("text", text);
        files.forEach((f) => body.append("files", f));
        if (accepted) body.set("integrity_accepted", "true");
        setReceipt(await post<WorkSubmission>(`/assignments/${assignment.id}/submit/`, body));
        setFiles([]);
        onChanged();
        return;
      }
      // A typed answer is safe to send again (it replaces work not yet marked), so without a connection it
      // waits on this device and is sent when the connection returns (item 4.02).
      const sent = await submitAssignmentText<WorkSubmission>(assignment.id, assignment.title, text, accepted);
      if (sent.queued) setQueued(sent.item.id);
      else {
        setReceipt(sent.result);
        onChanged();
      }
    } catch (err) {
      setError(err instanceof TypeError ? "No connection. Attach the files again when you are back online." : errorMessage(err, "Could not hand in."));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="stack sub-form">
      <dl className="facts">
        <div>
          <dt>Due</dt>
          <dd>
            {dmyTime(due)}
            {mine?.extended || (assignment.my_due_at && assignment.my_due_at !== assignment.due_at) ? " (extended for you)" : ""}
          </dd>
        </div>
        <div>
          <dt>What to hand in</dt>
          <dd>
            {assignment.max_files === 0
              ? "A typed answer only."
              : `A typed answer, or up to ${assignment.max_files} file${assignment.max_files === 1 ? "" : "s"}: ${assignment.accepts}, each at most ${assignment.upload_limit_mb} MB.`}
          </dd>
        </div>
        <div>
          <dt>Late work</dt>
          <dd>{penaltyRule(assignment)}</dd>
        </div>
        {assignment.is_group && (
          <div>
            <dt>Group work</dt>
            <dd>One member hands in for the whole group{mine?.group ? ` (${mine.group})` : ""}; the mark is the group's.</dd>
          </div>
        )}
      </dl>
      {assignment.rubric_detail && <RubricView rubric={assignment.rubric_detail} scores={mine?.mark?.rubric_scores ?? []} />}

      {mine?.mark && <MarkBox submission={mine} max={assignment.max_mark} />}

      {receipt && <ReceiptBox submission={receipt} title={assignment.title} />}

      {!closed && (
        <form className="stack" onSubmit={submit} aria-label={`Hand in ${assignment.title}`}>
          {mine && <p className="muted">You handed in on {dmyTime(mine.submitted_at)}. Handing in again replaces it; every hand-in is kept.</p>}
          <label>
            Your answer
            <textarea id={`answer-${assignment.id}`} value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          {assignment.max_files > 0 && (
            <label>
              Files (up to {assignment.max_files})
              <input
                id={`files-${assignment.id}`}
                type="file"
                multiple={assignment.max_files > 1}
                accept={acceptFor(assignment.accepted_kinds)}
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
            </label>
          )}
          {files.length > assignment.max_files && (
            <p role="alert" className="error">
              Choose at most {assignment.max_files} file{assignment.max_files === 1 ? "" : "s"}.
            </p>
          )}
          {assignment.requires_integrity && assignment.integrity_statement && (
            <label className="inline integrity">
              <input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} required />
              <span>{assignment.integrity_statement}</span>
            </label>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <div className="actions">
            <button type="submit" disabled={sending || (!text && files.length === 0) || files.length > assignment.max_files}>
              {sending ? "Handing in…" : mine ? "Hand in again" : "Hand in"}
            </button>
            <SendState id={queued} />
          </div>
        </form>
      )}
      {closed && !mine?.mark && (
        <p className="muted">
          {mine ? "Handed in. It can no longer be replaced." : assignment.opens_at && new Date(assignment.opens_at).getTime() > now ? `Opens ${dmyTime(assignment.opens_at)}.` : "The deadline has passed."}
        </p>
      )}
      {mine && <HandInHistory submissionId={mine.id} />}
      <ReceiptLookup />
    </div>
  );
}

/** The released mark: the result, the late penalty taken, the feedback and any files or recordings. */
export function MarkBox({ submission, max }: { submission: WorkSubmission; max: string }) {
  const mark = submission.mark!;
  const words = markWords(mark, max);
  return (
    <section className="mark-box" aria-label="Your mark">
      <p className="mark-result">
        Marked: <strong>{words.result}</strong>
      </p>
      {words.penalty && <p className="muted">{words.penalty}</p>}
      {mark.feedback && <p style={{ whiteSpace: "pre-wrap" }}>{mark.feedback}</p>}
      <FeedbackList files={submission.feedback_files} />
      {submission.srms_locked_at && <p className="muted small">Sent to the SRMS on {dmyTime(submission.srms_locked_at)}: the mark is final here.</p>}
    </section>
  );
}

/** What the student keeps as proof: the receipt code, the time, and the content's fingerprint (item 2.21). */
function ReceiptBox({ submission, title }: { submission: WorkSubmission; title: string }) {
  return (
    <section className="receipt" role="status" aria-label="Receipt">
      <h4>Received: {title}</h4>
      <p>
        Receipt <strong className="code">{submission.receipt}</strong>, handed in {dmyTime(submission.submitted_at)}
        {submission.is_late ? " (late)" : ""}.
      </p>
      {submission.files.length > 0 && (
        <ul className="plain small">
          {submission.files.map((f) => (
            <li key={f.id}>
              {f.filename} ({fileSize(f.size)})
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">The receipt is also in your notifications. Keep the code: it finds this hand-in again.</p>
      <div className="actions no-print">
        <button type="button" className="secondary" onClick={() => window.print()}>
          Print the receipt
        </button>
      </div>
    </section>
  );
}

function HandInHistory({ submissionId }: { submissionId: number }) {
  const [history, setHistory] = useState<History | null>(null);
  const [open, setOpen] = useState(false);
  const load = useCallback(() => {
    get<History>(`/submissions/${submissionId}/history/`)
      .then(setHistory)
      .catch(() => setHistory(null));
  }, [submissionId]);
  useEffect(() => {
    if (open) load();
  }, [open, load]);

  return (
    <details className="history" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>Every hand-in and its receipt</summary>
      {history && (
        <ol className="plain">
          {history.attempts.map((a) => (
            <li key={a.number}>
              <strong>
                {a.number}. {dmyTime(a.submitted_at)}
              </strong>
              {a.is_late && <span className="pill">Late</span>}
              {a.is_marked_attempt && <span className="pill">Marked</span>}
              <span className="muted small" style={{ display: "block" }}>
                Receipt {a.receipt} · fingerprint {a.content_hash.slice(0, 16)}
                {a.integrity_accepted ? " · integrity statement accepted" : ""}
              </span>
              {a.files.map((f) => (
                <a key={f.id} href={f.download_url} className="file-link">
                  {f.filename}
                </a>
              ))}
            </li>
          ))}
        </ol>
      )}
    </details>
  );
}

/** Find a hand-in again from its receipt code. */
export function ReceiptLookup() {
  const [code, setCode] = useState("");
  const [found, setFound] = useState<Receipt | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function look(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFound(null);
    try {
      setFound(await get<Receipt>(`/receipts/${encodeURIComponent(code.trim())}/`));
    } catch (err) {
      setError(errorMessage(err, "No such receipt."));
    }
  }

  return (
    <details className="history">
      <summary>Look up a receipt</summary>
      <form className="form-row" onSubmit={look}>
        <label className="grow">
          Receipt code
          <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="GSA-XXXXX-XXXXX" required />
        </label>
        <div className="actions">
          <button type="submit" className="secondary">
            Look up
          </button>
        </div>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {found && (
        <p role="status">
          {found.receipt}: {found.assignment} ({found.site}), hand-in {found.attempt} by {found.student_no} on {dmyTime(found.submitted_at)}
          {found.is_late ? ", late" : ""}. Fingerprint {found.content_hash.slice(0, 16)}; {found.files.length} file{found.files.length === 1 ? "" : "s"}.
        </p>
      )}
    </details>
  );
}
