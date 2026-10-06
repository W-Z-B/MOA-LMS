import { useEffect, useState } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { Attempt, AttemptSummary, Quiz } from "../../api/types-quizzes";
import { dmyTime } from "../../app/format";
import { BackLink } from "./AttemptPlayer";
import { studentState } from "./quizUtil";

const GRADING: Record<Quiz["grading_method"], string> = {
  highest: "your highest attempt counts",
  average: "the average of your attempts counts",
  first: "your first attempt counts",
  last: "your last attempt counts",
};

interface Props {
  quizId: number;
  onOpen: (path: string) => void;
  onBack: () => void;
}

/** A quiz as a student sees it before starting: its rules, their attempts, and Start or Continue. */
export function StudentQuiz({ quizId, onOpen, onBack }: Props) {
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [attempts, setAttempts] = useState<AttemptSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    Promise.all([get<Quiz>(`/quizzes/${quizId}/`), get<AttemptSummary[]>(`/quizzes/${quizId}/attempts/`)])
      .then(([q, a]) => {
        setQuiz(q);
        setAttempts(a);
      })
      .catch((err) => setError(errorMessage(err, "Could not open the quiz.")));
  }, [quizId]);

  async function start() {
    setStarting(true);
    setError(null);
    try {
      const attempt = await post<Attempt>(`/quizzes/${quizId}/start/`);
      onOpen(`${quizId}/attempts/${attempt.id}`);
    } catch (err) {
      setError(err instanceof TypeError ? "No connection. A quiz needs a connection to start." : errorMessage(err, "Could not start the quiz."));
      setStarting(false);
    }
  }

  if (!quiz)
    return error ? (
      <p role="alert" className="error">
        {error}
      </p>
    ) : (
      <p className="loading">Opening the quiz…</p>
    );
  const mine = quiz.my_status;
  const state = studentState(quiz);
  const inProgress = mine?.in_progress_attempt ?? null;
  const left = mine && mine.attempts_allowed ? mine.attempts_allowed - mine.attempts_used : null;
  const closes = mine?.closes_at ?? quiz.closes_at;
  const closed = !!closes && new Date(closes) <= new Date();
  const notYet = !!quiz.opens_at && new Date(quiz.opens_at) > new Date();
  const canStart = inProgress !== null || (!closed && !notYet && (left === null || left > 0));
  const limit = mine?.time_limit_minutes ?? quiz.time_limit_minutes;

  return (
    <>
      <BackLink onBack={onBack} />
      <div className="panel-head title-row">
        <h2>{quiz.title}</h2>
        <span className={`chip chip-${state.tone}`}>{state.label}</span>
      </div>
      {quiz.description && <p style={{ whiteSpace: "pre-wrap" }}>{quiz.description}</p>}
      <ul className="facts">
        <li>{quiz.opens_at ? `Opens ${dmyTime(quiz.opens_at)}` : "Open now"}</li>
        <li>{closes ? `Closes ${dmyTime(closes)}` : "No closing date"}</li>
        <li>{limit ? `Time limit: ${limit} minutes, counted by the server from when you start` : "No time limit"}</li>
        <li>
          {quiz.is_practice
            ? "Practice: as many attempts as you like; it does not count"
            : left === null
              ? `Attempts: as many as you like; ${GRADING[quiz.grading_method]}`
              : `Attempts: ${mine?.attempts_used ?? 0} of ${mine?.attempts_allowed} used; ${GRADING[quiz.grading_method]}`}
        </li>
        {quiz.pass_mark && <li>Pass mark: {Number(quiz.pass_mark)}%</li>}
      </ul>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {canStart && (
        <div className="actions">
          <button className="wide" onClick={() => void (inProgress ? onOpen(`${quizId}/attempts/${inProgress}`) : start())} disabled={starting}>
            {inProgress ? "Continue my attempt" : starting ? "Starting…" : attempts.length ? "Start another attempt" : "Start the quiz"}
          </button>
        </div>
      )}
      {attempts.length > 0 && (
        <>
          <h3>Your attempts</h3>
          <ul className="plain">
            {attempts.map((a) => (
              <li key={a.id} className="module">
                <div className="panel-head">
                  <div>
                    <strong>Attempt {a.number}</strong>
                    <p className="muted small">
                      {a.state === "in_progress"
                        ? "In progress"
                        : `Submitted ${a.submitted_at ? dmyTime(a.submitted_at) : ""}${a.auto_submitted ? " (time ran out)" : ""}`}
                      {a.percent !== null ? ` · ${a.score} out of ${Number(a.max_score)} (${a.percent}%)` : a.state === "finished" ? " · mark not shown yet" : ""}
                    </p>
                  </div>
                  {a.state === "finished" && (
                    <button className="secondary" onClick={() => onOpen(`${quizId}/attempts/${a.id}`)} aria-label={`Review attempt ${a.number}`}>
                      Review
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
