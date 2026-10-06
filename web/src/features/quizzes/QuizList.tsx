import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { Quiz } from "../../api/types-quizzes";
import { dmyTime } from "../../app/format";
import { studentState } from "./quizUtil";

interface Props {
  siteId: number;
  teaching: boolean;
  onOpen: (path: string) => void;
}

/** The site's quizzes (feature 10). Students see the published ones with where they stand; teaching staff all. */
export function QuizList({ siteId, teaching, onOpen }: Props) {
  const [quizzes, setQuizzes] = useState<Quiz[] | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<Quiz>>(`/quizzes/?site=${siteId}`)
      .then((r) => {
        setQuizzes(r.results);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load the quizzes.")));
  }, [siteId]);
  useEffect(load, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    try {
      const quiz = await post<Quiz>("/quizzes/", { site: siteId, title });
      onOpen(`${quiz.id}/questions`);
    } catch (err) {
      setError(errorMessage(err, "Could not create the quiz."));
    }
  }

  return (
    <>
      {teaching && (
        <div className="actions" style={{ marginBottom: 12 }}>
          <button className="secondary" onClick={() => onOpen("banks")}>
            Question banks
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {quizzes === null && !error && <p className="loading">Loading quizzes…</p>}
      {quizzes?.length === 0 && <p className="muted">No quizzes yet.</p>}
      <ul className="plain">
        {quizzes?.map((quiz) => {
          const state = teaching ? null : studentState(quiz);
          return (
            <li key={quiz.id} className="module quiz-row">
              <div className="panel-head">
                <div>
                  <h3>
                    <a href={`#/sites/${siteId}/quizzes/${quiz.id}`}>{quiz.title}</a>
                  </h3>
                  <p className="muted small">
                    {[
                      quiz.closes_at ? `Closes ${dmyTime(quiz.my_status?.closes_at ?? quiz.closes_at)}` : "No closing date",
                      quiz.time_limit_minutes ? `${quiz.my_status?.time_limit_minutes ?? quiz.time_limit_minutes} minutes` : "No time limit",
                      quiz.is_practice ? "Practice: does not count" : `${Number(quiz.max_mark)} marks`,
                    ].join(" · ")}
                  </p>
                </div>
                <span className="quiz-chips">
                  {state && <span className={`chip chip-${state.tone}`}>{state.label}</span>}
                  {teaching && <span className={quiz.is_published ? "chip chip-approved" : "chip chip-draft"}>{quiz.is_published ? "Published" : "Draft"}</span>}
                  {teaching && quiz.is_practice && <span className="chip">Practice</span>}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
      {teaching && (
        <form className="form-row sub-form" onSubmit={create}>
          <label className="grow">
            New quiz
            <input id="quiz-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Week 1 check: soils" required />
          </label>
          <div className="actions">
            <button type="submit">Create quiz</button>
          </div>
        </form>
      )}
    </>
  );
}
