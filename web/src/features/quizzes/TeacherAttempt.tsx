import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { Attempt, AttemptQuestion, IntegrityLogEntry } from "../../api/types-quizzes";
import { BackLink } from "./AttemptPlayer";
import { Review } from "./Review";

/** One attempt for its teaching staff: every answer, marking essays and files (or changing any mark), and release. */
export function TeacherAttempt({ attemptId, onBack }: { attemptId: number; onBack: () => void }) {
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(() => {
    get<Attempt>(`/quiz-attempts/${attemptId}/`)
      .then(setAttempt)
      .catch((err) => setError(errorMessage(err, "Could not open the attempt.")));
  }, [attemptId]);
  useEffect(load, [load]);

  async function release() {
    try {
      setAttempt(await post<Attempt>(`/quiz-attempts/${attemptId}/release/`));
      setMessage("Result released. The student has been told.");
      setError(null);
    } catch (err) {
      setError(errorMessage(err, "Could not release the result."));
    }
  }

  if (!attempt)
    return error ? (
      <p role="alert" className="error">
        {error}
      </p>
    ) : (
      <p className="loading">Opening the attempt…</p>
    );
  const finished = attempt.state === "finished";
  return (
    <>
      <BackLink onBack={onBack} label="Back to the quiz" />
      <div className="panel-head title-row">
        <h2>
          {attempt.quiz_title}: {attempt.student_no}
        </h2>
        {finished && (
          <span className={attempt.is_released ? "chip chip-approved" : "chip chip-waiting"}>
            {attempt.is_released ? "Released" : attempt.needs_grading ? "Needs marking" : "Not released"}
          </span>
        )}
      </div>
      {message && (
        <p role="status" className="notice good">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!finished && <p className="notice">This attempt is still in progress. It can be marked once it is submitted.</p>}
      {finished && !attempt.is_released && !attempt.needs_grading && (
        <div className="actions" style={{ marginBottom: 12 }}>
          <button onClick={() => void release()}>Release this result</button>
        </div>
      )}
      {attempt.is_secure_exam && <IntegrityLog attemptId={attempt.id} />}
      <Review attempt={attempt} extra={finished ? (q) => <MarkForm attemptId={attempt.id} q={q} onMarked={setAttempt} /> : undefined} />
    </>
  );
}

/**
 * The sitting's integrity log (item 3.25): a plain timeline of what the student's browser reported during a
 * secure exam sitting, not an accusation. The course's teaching staff read it alongside the student's answers.
 */
function IntegrityLog({ attemptId }: { attemptId: number }) {
  const [events, setEvents] = useState<IntegrityLogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    get<IntegrityLogEntry[]>(`/quiz-attempts/${attemptId}/integrity-log/`)
      .then(setEvents)
      .catch((err) => setError(errorMessage(err, "Could not open the integrity log.")));
  }, [attemptId]);

  return (
    <section className="module" aria-labelledby="integrity-log-head">
      <h3 id="integrity-log-head">Integrity log</h3>
      <p className="muted small">
        What the page observed during this sitting, in server time. It is a timeline for you to weigh
        alongside the student&rsquo;s answers, not a verdict.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {events && events.length === 0 && <p className="muted">Nothing was reported during this sitting.</p>}
      {events && events.length > 0 && (
        <ul className="integrity-log-list">
          {events.map((e, i) => (
            <li key={i}>
              <time dateTime={e.at}>{new Date(e.at).toLocaleString()}</time> — {e.label}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function MarkForm({ attemptId, q, onMarked }: { attemptId: number; q: AttemptQuestion; onMarked: (a: Attempt) => void }) {
  const waiting = q.state === "needs_marking";
  const [open, setOpen] = useState(waiting);
  const [mark, setMark] = useState(q.awarded ?? "");
  const [comment, setComment] = useState(q.comment ?? "");
  const [error, setError] = useState<string | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      onMarked(await post<Attempt>(`/quiz-attempts/${attemptId}/answers/${q.position}/mark/`, { mark, comment }));
      setError(null);
      setOpen(false);
    } catch (err) {
      setError(errorMessage(err, "Could not save the mark."));
    }
  }

  if (!open)
    return (
      <button className="secondary small-button" onClick={() => setOpen(true)} aria-label={`Change the mark for question ${q.position}`}>
        Change the mark
      </button>
    );
  return (
    <form className="form-row sub-form" onSubmit={save}>
      <label>
        Mark out of {Number(q.max_mark)}
        <input type="number" min={0} max={Number(q.max_mark)} step="0.01" value={mark} onChange={(e) => setMark(e.target.value)} required />
      </label>
      <label className="grow">
        Comment for the student
        <input value={comment} onChange={(e) => setComment(e.target.value)} />
      </label>
      <div className="actions">
        <button type="submit" aria-label={`Save the mark for question ${q.position}`}>
          Save mark
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </form>
  );
}
