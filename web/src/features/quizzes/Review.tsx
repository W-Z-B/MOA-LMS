import type { ReactNode } from "react";
import type { AnswerState, Attempt, AttemptQuestion } from "../../api/types-quizzes";
import { dmyTime } from "../../app/format";
import { describeResponse } from "./describe";
import { Rich } from "./Rich";

const STATE_LABEL: Record<AnswerState, string> = {
  correct: "Correct",
  partial: "Partly correct",
  incorrect: "Not correct",
  needs_marking: "Waiting to be marked",
};

/**
 * A submitted attempt, showing only what the server sends: marks, right answers and feedback each appear once
 * the quiz's review options (and, for marks, the release) allow (item 3.05).
 */
export function Review({ attempt, extra }: { attempt: Attempt; extra?: (q: AttemptQuestion) => ReactNode }) {
  const result = attempt.score !== null;
  return (
    <div className="stack">
      <section className="module" aria-labelledby="result-head">
        <h2 id="result-head" style={{ marginTop: 0 }}>
          Attempt {attempt.number}: {attempt.submitted_at ? `submitted ${dmyTime(attempt.submitted_at)}` : "in progress"}
        </h2>
        {attempt.auto_submitted && <p className="muted">It was submitted automatically when the time ran out.</p>}
        {result ? (
          <p className="result-line">
            Score <strong className="num">{attempt.score}</strong> out of {Number(attempt.max_score).toFixed(2)}
            {attempt.percent !== null && (
              <>
                {" "}
                (<strong className="num">{attempt.percent}%</strong>)
              </>
            )}
            {attempt.passed !== null && <span className={attempt.passed ? "chip chip-approved" : "chip chip-rejected"}>{attempt.passed ? "Passed" : "Not passed"}</span>}
          </p>
        ) : attempt.needs_grading ? (
          <p className="notice">Some answers are waiting to be marked. Your result is shown when it is released.</p>
        ) : attempt.is_released ? (
          <p className="notice">Your answers are in. This quiz does not show marks yet.</p>
        ) : (
          <p className="notice">Your answers are in. Your mark is shown here when it is released.</p>
        )}
        {attempt.overall_feedback && <p className="notice good">{attempt.overall_feedback}</p>}
      </section>
      {attempt.questions.map((q) => (
        <section key={q.position} className="module question-review" aria-labelledby={`review-q${q.position}`}>
          <div className="panel-head">
            <h3 id={`review-q${q.position}`}>Question {q.position}</h3>
            {q.state && <span className={`chip answer-${q.state}`}>{STATE_LABEL[q.state]}</span>}
          </div>
          {/* A gap of a fill-in-the-blanks question is shown as a numbered blank; the answers follow. */}
          <Rich html={q.qtype === "cloze" ? q.text.replace(/\[\[(\d{1,3})\]\]/g, "____ (gap $1)") : q.text} />
          {q.image_url && q.qtype !== "image_label" && <img className="question-image" src={q.image_url} alt="" />}
          <p>
            <span className="muted">Answer given: </span>
            {q.file_url ? <a href={q.file_url}>{describeResponse(q.qtype, q.data, q.response)}</a> : describeResponse(q.qtype, q.data, q.response)}
          </p>
          {q.awarded !== undefined && (
            <p className="muted">
              Mark: <span className="num">{q.awarded ?? "not marked yet"}</span> out of {Number(q.max_mark).toFixed(2)}
            </p>
          )}
          {q.right_answer && (
            <p>
              <span className="muted">Right answer: </span>
              {describeResponse(q.qtype, q.data, q.right_answer)}
            </p>
          )}
          {q.feedback && (
            <div className="feedback">
              <Rich html={q.feedback} />
            </div>
          )}
          {q.general_feedback && (
            <div className="feedback">
              <Rich html={q.general_feedback} />
            </div>
          )}
          {q.comment && <p className="feedback">Marker's comment: {q.comment}</p>}
          {extra?.(q)}
        </section>
      ))}
    </div>
  );
}
