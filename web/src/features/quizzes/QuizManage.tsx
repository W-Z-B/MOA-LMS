import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post, remove } from "../../api/client";
import { QTYPE_LABEL, type AttemptSummary, type MarkingItem, type Question, type Quiz, type QuizOverride, type QuizStatistics, type SiteMember } from "../../api/types-quizzes";
import { dmyTime } from "../../app/format";
import { QUIZ_SECTIONS, type QuizSection } from "../../app/router";
import { BackLink } from "./AttemptPlayer";
import { QuizQuestions } from "./QuizQuestions";
import { getAll, plainText, toLocalInput } from "./quizUtil";
import { QuizSettings } from "./QuizSettings";
import { PaperQuizzes } from "../assess/PaperQuizzes";

const SECTION_LABEL: Record<QuizSection, string> = {
  settings: "Settings",
  questions: "Questions",
  students: "Extra time",
  marking: "Marking",
  results: "Results",
  statistics: "Statistics",
  paper: "On paper",
};

interface Props {
  siteId: number;
  quizId: number;
  section: QuizSection;
  onOpen: (path: string) => void;
  onBack: () => void;
}

/** A quiz for its teaching staff (items 3.02 to 3.06 and 3.23): each part has an address of its own. */
export function QuizManage({ siteId, quizId, section, onOpen, onBack }: Props) {
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    get<Quiz>(`/quizzes/${quizId}/`)
      .then(setQuiz)
      .catch((err) => setError(errorMessage(err, "Could not open the quiz.")));
  }, [quizId]);
  useEffect(load, [load]);

  if (!quiz)
    return error ? (
      <p role="alert" className="error">
        {error}
      </p>
    ) : (
      <p className="loading">Opening the quiz…</p>
    );
  return (
    <>
      <BackLink onBack={onBack} />
      <div className="panel-head title-row">
        <h2>{quiz.title}</h2>
        <span className={quiz.is_published ? "chip chip-approved" : "chip chip-draft"}>{quiz.is_published ? "Published" : "Draft"}</span>
      </div>
      {/* Links, not tabs: each part is a page of its own with its own address. */}
      <nav className="subnav" aria-label="Parts of the quiz">
        {QUIZ_SECTIONS.map((s) => (
          <a key={s} href={`#/sites/${siteId}/quizzes/${quizId}/${s}`} aria-current={s === section ? "page" : undefined}>
            {SECTION_LABEL[s]}
          </a>
        ))}
      </nav>
      {section === "settings" && <QuizSettings key={quiz.id} quiz={quiz} onSaved={setQuiz} onDeleted={onBack} />}
      {section === "questions" && <QuizQuestions quiz={quiz} siteId={siteId} onChanged={load} />}
      {section === "students" && <Overrides quiz={quiz} siteId={siteId} />}
      {section === "marking" && <MarkingQueue quiz={quiz} onOpen={onOpen} />}
      {section === "results" && <Results quiz={quiz} onOpen={onOpen} />}
      {section === "statistics" && <Statistics quiz={quiz} />}
      {section === "paper" && <PaperQuizzes quizId={quiz.id} />}
    </>
  );
}

/** Per-student extra time, extra attempts or a later close (item 3.23). Accommodations add their share already. */
function Overrides({ quiz, siteId }: { quiz: Quiz; siteId: number }) {
  const [rows, setRows] = useState<QuizOverride[]>([]);
  const [students, setStudents] = useState<SiteMember[]>([]);
  const [draft, setDraft] = useState({ student: "", extra_minutes: "0", extra_attempts: "0", closes_at: "", reason: "" });
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([getAll<QuizOverride>(`/quiz-overrides/?quiz=${quiz.id}`), get<SiteMember[]>(`/sites/${siteId}/members/`)])
      .then(([o, m]) => {
        setRows(o);
        setStudents(m.filter((x) => x.role === "student"));
      })
      .catch((err) => setError(errorMessage(err, "Could not load the extra time.")));
  }, [quiz.id, siteId]);
  useEffect(load, [load]);

  async function add(e: FormEvent) {
    e.preventDefault();
    try {
      await post("/quiz-overrides/", {
        quiz: quiz.id,
        student: Number(draft.student),
        extra_minutes: Number(draft.extra_minutes || 0),
        extra_attempts: Number(draft.extra_attempts || 0),
        closes_at: draft.closes_at ? new Date(draft.closes_at).toISOString() : null,
        reason: draft.reason,
      });
      setDraft({ student: "", extra_minutes: "0", extra_attempts: "0", closes_at: "", reason: "" });
      setError(null);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not save the extra time."));
    }
  }

  async function drop(row: QuizOverride) {
    try {
      await remove(`/quiz-overrides/${row.id}/`);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not remove it."));
    }
  }

  const taken = new Set(rows.map((r) => r.student));
  return (
    <>
      <p className="muted">
        For one student: more time, more attempts or a later closing date. A student's recorded accommodation already adds its share of extra time to
        every time limit.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {rows.length === 0 ? (
        <p className="muted">No one has extra time on this quiz.</p>
      ) : (
        <ul className="plain">
          {rows.map((r) => (
            <li key={r.id} className="module">
              <div className="panel-head">
                <div>
                  <strong>
                    {r.student_name} ({r.student_no})
                  </strong>
                  <p className="muted small">
                    {[
                      r.extra_minutes ? `${r.extra_minutes} more minutes` : "",
                      r.extra_attempts ? `${r.extra_attempts} more attempts` : "",
                      r.closes_at ? `closes for them ${dmyTime(r.closes_at)}` : "",
                      r.reason,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <button className="secondary danger-text small-button" onClick={() => void drop(r)} aria-label={`Remove extra time for ${r.student_name}`}>
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <form className="stack sub-form" onSubmit={add}>
        <h3>Give a student more</h3>
        <div className="grid2">
          <label className="span2">
            Student
            <select value={draft.student} onChange={(e) => setDraft((prev) => ({ ...prev, student: e.target.value }))} required>
              <option value="">Choose…</option>
              {students
                .filter((s) => !taken.has(s.person_id))
                .map((s) => (
                  <option key={s.person_id} value={s.person_id}>
                    {s.name} ({s.external_id})
                  </option>
                ))}
            </select>
          </label>
          <label>
            Extra minutes
            <input type="number" min={0} value={draft.extra_minutes} onChange={(e) => setDraft((prev) => ({ ...prev, extra_minutes: e.target.value }))} />
          </label>
          <label>
            Extra attempts
            <input type="number" min={0} value={draft.extra_attempts} onChange={(e) => setDraft((prev) => ({ ...prev, extra_attempts: e.target.value }))} />
          </label>
          <label>
            Closes for them (optional)
            <input type="datetime-local" value={draft.closes_at} min={toLocalInput(quiz.opens_at)} onChange={(e) => setDraft((prev) => ({ ...prev, closes_at: e.target.value }))} />
          </label>
          <label>
            Reason (kept for the record; not shown to the student)
            <input value={draft.reason} maxLength={200} onChange={(e) => setDraft((prev) => ({ ...prev, reason: e.target.value }))} />
          </label>
        </div>
        <div className="actions">
          <button type="submit">Save</button>
        </div>
      </form>
    </>
  );
}

/** Essays and files waiting for a person, oldest first, and releasing the results that are ready (items 3.04, 3.05). */
function MarkingQueue({ quiz, onOpen }: { quiz: Quiz; onOpen: (path: string) => void }) {
  const [rows, setRows] = useState<MarkingItem[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    get<MarkingItem[]>(`/quizzes/${quiz.id}/marking-queue/`)
      .then(setRows)
      .catch((err) => setError(errorMessage(err, "Could not load the marking.")));
  }, [quiz.id]);
  useEffect(load, [load]);

  async function release() {
    try {
      const r = await post<{ released: number; awaiting_marking: number }>(`/quizzes/${quiz.id}/release/`);
      setMessage(
        `${r.released} ${r.released === 1 ? "result" : "results"} released.` +
          (r.awaiting_marking ? ` ${r.awaiting_marking} still ${r.awaiting_marking === 1 ? "needs" : "need"} marking first.` : ""),
      );
      setError(null);
    } catch (err) {
      setError(errorMessage(err, "Could not release the results."));
    }
  }

  return (
    <>
      <div className="publish-bar">
        <p className="muted">
          {quiz.auto_release ? "Results are released as soon as they are fully marked." : "You release results when you are ready."}
        </p>
        <button onClick={() => void release()}>Release marked results</button>
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
      {rows === null ? (
        <p className="loading">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="muted">Nothing waits to be marked.</p>
      ) : (
        <ul className="plain">
          {rows.map((r) => (
            <li key={`${r.attempt}-${r.position}`} className="module">
              <div className="panel-head">
                <div>
                  <strong>
                    {r.student_name} ({r.student_no})
                  </strong>
                  <p className="muted small">
                    Question {r.position}: {r.question} · {QTYPE_LABEL[r.qtype]} · out of {Number(r.max_mark)} · submitted {dmyTime(r.submitted_at)}
                  </p>
                </div>
                <button onClick={() => onOpen(`${quiz.id}/attempts/${r.attempt}`)} aria-label={`Mark question ${r.position} for ${r.student_name}`}>
                  Mark
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Results({ quiz, onOpen }: { quiz: Quiz; onOpen: (path: string) => void }) {
  const [rows, setRows] = useState<AttemptSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    get<AttemptSummary[]>(`/quizzes/${quiz.id}/attempts/`)
      .then(setRows)
      .catch((err) => setError(errorMessage(err, "Could not load the attempts.")));
  }, [quiz.id]);
  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (rows === null) return <p className="loading">Loading…</p>;
  if (rows.length === 0) return <p className="muted">No one has attempted this quiz yet.</p>;
  return (
    <div className="scroll-x" tabIndex={0} role="region" aria-label="Attempts">
      <table>
        <thead>
          <tr>
            <th>Student</th>
            <th className="num">Attempt</th>
            <th>State</th>
            <th className="num">Score</th>
            <th>Open</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id}>
              <td>
                {a.student_name} <span className="muted small">{a.student_no}</span>
              </td>
              <td className="num">{a.number}</td>
              <td>
                {a.state === "in_progress" ? "In progress" : a.needs_grading ? "Needs marking" : a.is_released ? "Released" : "Marked, not released"}
                {a.auto_submitted && <span className="muted small"> (time ran out)</span>}
              </td>
              <td className="num">{a.percent !== null ? `${a.score} / ${Number(a.max_score)} (${a.percent}%)` : ""}</td>
              <td>
                <button className="secondary small-button" onClick={() => onOpen(`${quiz.id}/attempts/${a.id}`)} aria-label={`Open attempt ${a.number} by ${a.student_name}`}>
                  Open
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * How each question did (item 3.06): facility (the average mark, as a share), discrimination (whether the
 * students who did well overall did well on it) and how often each answer was given. A bar beside each
 * figure, drawn with CSS: no chart library.
 */
function Statistics({ quiz }: { quiz: Quiz }) {
  const [stats, setStats] = useState<QuizStatistics | null>(null);
  const [choices, setChoices] = useState<Record<number, Record<string, string>>>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    get<QuizStatistics>(`/quizzes/${quiz.id}/statistics/`)
      .then(async (s) => {
        setStats(s);
        // Multiple-choice answers are counted by option; their wording comes from the question itself.
        const mc = s.questions.filter((q) => q.qtype === "multichoice");
        const loaded = await Promise.all(mc.map((q) => get<Question>(`/questions/${q.question_id}/`).catch(() => null)));
        setChoices(
          Object.fromEntries(
            loaded
              .filter((q): q is Question => q !== null)
              .map((q) => [q.id, Object.fromEntries((q.latest.data.choices ?? []).map((c: { id: string; text: string }) => [c.id, plainText(c.text)]))]),
          ),
        );
      })
      .catch((err) => setError(errorMessage(err, "Could not load the statistics.")));
  }, [quiz.id]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!stats) return <p className="loading">Loading…</p>;
  if (stats.attempts === 0) return <p className="muted">Statistics appear once students have submitted attempts.</p>;
  const pct = (n: number | null) => (n === null ? "–" : `${n.toFixed(1)}%`);
  return (
    <>
      <ul className="facts">
        <li>{stats.attempts} submitted attempts</li>
        <li>Average {pct(stats.mean_percent)}</li>
        <li>Middle mark {pct(stats.median_percent)}</li>
        {stats.pass_rate !== null && <li>Passed {pct(stats.pass_rate)}</li>}
      </ul>
      <div className="scroll-x" tabIndex={0} role="region" aria-label="Statistics by question">
        <table className="stats-table">
          <thead>
            <tr>
              <th>Question</th>
              <th className="num">Answered</th>
              <th>Facility (how easy)</th>
              <th className="num">Discrimination</th>
            </tr>
          </thead>
          <tbody>
            {stats.questions.map((q) => (
              <tr key={q.question_id}>
                <td>
                  {q.positions.join(", ")}. {q.name}
                  <span className="muted small" style={{ display: "block" }}>
                    {QTYPE_LABEL[q.qtype]}
                  </span>
                </td>
                <td className="num">{q.answered}</td>
                <td>
                  <span className="bar-cell">
                    <span className="num">{q.facility_index.toFixed(1)}%</span>
                    <span className="hbar" aria-hidden="true">
                      <span style={{ width: `${Math.max(0, Math.min(100, q.facility_index))}%` }} />
                    </span>
                  </span>
                </td>
                <td className="num">
                  {q.discrimination_index === null ? "–" : `${q.discrimination_index.toFixed(1)}%`}
                  {q.discrimination_index !== null && q.discrimination_index < 20 && <span className="muted small"> weak</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Answers given</h3>
      {stats.questions
        .filter((q) => q.responses.length > 0)
        .map((q) => {
          const most = Math.max(...q.responses.map((r) => r.count), 1);
          return (
            <section key={q.question_id} className="module">
              <h4 style={{ margin: "0 0 6px" }}>
                {q.positions.join(", ")}. {q.name}
              </h4>
              <ul className="plain dist">
                {q.responses.map((r) => (
                  <li key={r.response}>
                    <span className="dist-label">{choices[q.question_id]?.[r.response] ?? r.response}</span>
                    <span className="hbar" aria-hidden="true">
                      <span style={{ width: `${(r.count / most) * 100}%` }} />
                    </span>
                    <span className="num">{r.count}</span>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      <p className="muted small">
        Facility is the average mark on the question as a share of its marks. Discrimination compares each student's mark on the question with their
        mark on the rest of the quiz: below 20% the question does not separate stronger and weaker students well.
      </p>
    </>
  );
}
