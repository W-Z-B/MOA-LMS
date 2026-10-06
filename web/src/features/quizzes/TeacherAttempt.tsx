import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { Attempt, AttemptQuestion } from "../../api/types-quizzes";
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
      <Review attempt={attempt} extra={finished ? (q) => <MarkForm attemptId={attempt.id} q={q} onMarked={setAttempt} /> : undefined} />
    </>
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
