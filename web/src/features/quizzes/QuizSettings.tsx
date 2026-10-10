import { useState, type FormEvent } from "react";
import { ApiError, errorMessage, patch, remove } from "../../api/client";
import type { Quiz, Review } from "../../api/types-quizzes";
import { toLocalInput } from "./quizUtil";

const fromLocalInput = (value: string) => (value ? new Date(value).toISOString() : null);

const REVIEW: { value: Review; label: string }[] = [
  { value: "immediately", label: "Straight after the attempt" },
  { value: "after_close", label: "After the quiz closes" },
  { value: "never", label: "Never" },
];

interface Draft {
  title: string;
  description: string;
  opens_at: string;
  closes_at: string;
  time_limit_minutes: string;
  attempts_allowed: string;
  grading_method: Quiz["grading_method"];
  pass_mark: string;
  weight: string;
  is_practice: boolean;
  is_secure_exam: boolean;
  shuffle_questions: boolean;
  shuffle_answers: boolean;
  questions_per_page: string;
  navigation: Quiz["navigation"];
  review_marks: Review;
  review_correct: Review;
  review_feedback: Review;
  auto_release: boolean;
}

const draftOf = (q: Quiz): Draft => ({
  title: q.title,
  description: q.description,
  opens_at: toLocalInput(q.opens_at),
  closes_at: toLocalInput(q.closes_at),
  time_limit_minutes: q.time_limit_minutes ? String(q.time_limit_minutes) : "",
  attempts_allowed: String(q.attempts_allowed),
  grading_method: q.grading_method,
  pass_mark: q.pass_mark ?? "",
  weight: q.weight,
  is_practice: q.is_practice,
  is_secure_exam: q.is_secure_exam,
  shuffle_questions: q.shuffle_questions,
  shuffle_answers: q.shuffle_answers,
  questions_per_page: String(q.questions_per_page),
  navigation: q.navigation,
  review_marks: q.review_marks,
  review_correct: q.review_correct,
  review_feedback: q.review_feedback,
  auto_release: q.auto_release,
});

interface Props {
  quiz: Quiz;
  onSaved: (quiz: Quiz) => void;
  onDeleted: () => void;
}

/**
 * A quiz's settings (items 3.02 and 3.03): when it opens and closes, the time limit, attempts and how they are
 * graded, the pass mark and weight, practice, shuffling and pages, and what students see afterwards. Publishing
 * is refused by the server until the quiz is ready; its reasons are listed here.
 */
export function QuizSettings({ quiz, onSaved, onDeleted }: Props) {
  const [d, setD] = useState<Draft>(() => draftOf(quiz));
  const [error, setError] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setD((x) => ({ ...x, [key]: value }));
    setSaved(false);
  };

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const body = {
        ...d,
        opens_at: fromLocalInput(d.opens_at),
        closes_at: fromLocalInput(d.closes_at),
        time_limit_minutes: d.time_limit_minutes ? Number(d.time_limit_minutes) : null,
        attempts_allowed: Number(d.attempts_allowed || 0),
        pass_mark: d.pass_mark === "" ? null : d.pass_mark,
        questions_per_page: Number(d.questions_per_page || 0),
      };
      const updated = await patch<Quiz>(`/quizzes/${quiz.id}/`, body);
      setD(draftOf(updated));
      setSaved(true);
      onSaved(updated);
    } catch (err) {
      setError(errorMessage(err, "Could not save the settings."));
    }
  }

  async function publish(on: boolean) {
    setError(null);
    setProblems([]);
    try {
      onSaved(await patch<Quiz>(`/quizzes/${quiz.id}/`, { is_published: on }));
    } catch (err) {
      // The server says every reason the quiz is not ready (quizzes.services.quiz_problems).
      const reasons = err instanceof ApiError ? err.fields?.is_published : undefined;
      if (reasons) setProblems([reasons].flat().map(String));
      else setError(errorMessage(err, "Could not change the quiz."));
    }
  }

  async function destroy() {
    if (!window.confirm(`Delete the quiz “${quiz.title}”? This cannot be undone.`)) return;
    try {
      await remove(`/quizzes/${quiz.id}/`);
      onDeleted();
    } catch (err) {
      setError(errorMessage(err, "Could not delete the quiz."));
    }
  }

  return (
    <>
      <div className="publish-bar">
        <p>
          {quiz.is_published ? (
            <>
              <span className="chip chip-approved">Published</span> Students on this course can see it.
            </>
          ) : (
            <>
              <span className="chip chip-draft">Draft</span> Students cannot see it yet.
            </>
          )}
        </p>
        <button className={quiz.is_published ? "secondary" : undefined} onClick={() => void publish(!quiz.is_published)}>
          {quiz.is_published ? "Unpublish" : "Publish to students"}
        </button>
      </div>
      {problems.length > 0 && (
        <div role="alert" className="notice bad">
          <strong>The quiz cannot be published yet:</strong>
          <ul>
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      <form className="stack" onSubmit={save}>
        <div className="grid2">
          <label className="span2">
            Title
            <input value={d.title} onChange={(e) => set("title", e.target.value)} required />
          </label>
          <label className="span2">
            Instructions for students
            <textarea value={d.description} onChange={(e) => set("description", e.target.value)} />
          </label>
          <label>
            Opens
            <input type="datetime-local" value={d.opens_at} onChange={(e) => set("opens_at", e.target.value)} />
          </label>
          <label>
            Closes
            <input type="datetime-local" value={d.closes_at} onChange={(e) => set("closes_at", e.target.value)} />
          </label>
          <label>
            Time limit in minutes (blank for none)
            <input type="number" min={1} value={d.time_limit_minutes} onChange={(e) => set("time_limit_minutes", e.target.value)} />
          </label>
          <label>
            Attempts allowed (0 for unlimited)
            <input
              type="number"
              min={0}
              value={d.attempts_allowed}
              disabled={d.is_practice || d.is_secure_exam}
              onChange={(e) => set("attempts_allowed", e.target.value)}
            />
          </label>
          <label>
            Which attempt counts
            <select value={d.grading_method} onChange={(e) => set("grading_method", e.target.value as Draft["grading_method"])}>
              <option value="highest">The highest</option>
              <option value="average">The average of all</option>
              <option value="first">The first</option>
              <option value="last">The last</option>
            </select>
          </label>
          <label>
            Pass mark in % (blank for none)
            <input type="number" min={0} max={100} step="0.01" value={d.pass_mark} onChange={(e) => set("pass_mark", e.target.value)} />
          </label>
          <label>
            Weight in the coursework
            <input type="number" min={0} step="0.01" value={d.weight} disabled={d.is_practice} onChange={(e) => set("weight", e.target.value)} />
          </label>
          <label>
            Questions on each page (0 for all on one page)
            <input type="number" min={0} value={d.questions_per_page} onChange={(e) => set("questions_per_page", e.target.value)} />
          </label>
          <label>
            Moving between pages
            <select value={d.navigation} onChange={(e) => set("navigation", e.target.value as Draft["navigation"])}>
              <option value="free">Free: any order, and back again</option>
              <option value="sequential">In order: no going back</option>
            </select>
          </label>
        </div>
        <fieldset className="stack">
          <legend>Options</legend>
          <label className="inline">
            <input
              type="checkbox"
              checked={d.is_practice}
              disabled={d.is_secure_exam}
              onChange={(e) => set("is_practice", e.target.checked)}
            />
            Practice quiz: never counts, unlimited attempts
          </label>
          <label className="inline">
            <input
              type="checkbox"
              checked={d.is_secure_exam}
              disabled={d.is_practice}
              onChange={(e) => set("is_secure_exam", e.target.checked)}
            />
            Secure exam: one attempt only, enforced on the server; focus changes, copy, paste and right-click
            attempts during the sitting are logged for the integrity log. This is a deterrent built into the
            page, not a lockdown browser or webcam proctoring.
          </label>
          <label className="inline">
            <input type="checkbox" checked={d.shuffle_questions} onChange={(e) => set("shuffle_questions", e.target.checked)} />
            Shuffle the questions for each attempt
          </label>
          <label className="inline">
            <input type="checkbox" checked={d.shuffle_answers} onChange={(e) => set("shuffle_answers", e.target.checked)} />
            Shuffle the answers within questions
          </label>
          <label className="inline">
            <input type="checkbox" checked={d.auto_release} onChange={(e) => set("auto_release", e.target.checked)} />
            Release each result as soon as it is fully marked
          </label>
        </fieldset>
        <fieldset className="grid2">
          <legend>What students see after an attempt</legend>
          {(
            [
              ["review_marks", "Their marks"],
              ["review_correct", "The right answers"],
              ["review_feedback", "Feedback"],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              {label}
              <select value={d[key]} onChange={(e) => set(key, e.target.value as Review)}>
                {REVIEW.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </fieldset>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="submit">Save settings</button>
          {saved && (
            <span role="status" className="sync sent">
              Saved
            </span>
          )}
          <span className="grow" />
          <button type="button" className="secondary danger-text" onClick={() => void destroy()}>
            Delete quiz
          </button>
        </div>
      </form>
    </>
  );
}
