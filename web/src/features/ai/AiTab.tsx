import { useEffect, useState, type FormEvent } from "react";
import { ApiError, errorMessage, get, patch, post } from "../../api/client";
import type { Module, Paginated } from "../../api/types";
import type { AiStatus, Draft, DraftQuestion, DraftRubric, HelperAnswer } from "../../api/types-connect";
import type { QuestionBank } from "../../api/types-quizzes";
import "../tools/tools.css";

interface Props {
  siteId: number;
  status: AiStatus;
  modules: Module[];
  onStatus: (status: AiStatus) => void;
}

/**
 * AI help on a course, within decision D5 (items 6.11, 6.12). Teaching staff switch it on for their course and
 * ask for drafts, which they check and edit before saving; students ask the study helper, which answers only
 * from the course's own material and shows where from. The site screen shows this tab only when GSA has
 * switched AI on, and to a student only while the helper may be used.
 */
export function AiTab({ siteId, status, modules, onStatus }: Props) {
  return (
    <div className="ai-help">
      {status.teaching && <Switches siteId={siteId} status={status} onStatus={onStatus} />}
      {status.teaching && status.drafts && (
        <>
          <QuestionDrafts siteId={siteId} modules={modules} />
          <RubricDraft siteId={siteId} />
        </>
      )}
      {status.study_helper && (status.helper_available || status.teaching) ? (
        <Helper siteId={siteId} />
      ) : (
        !status.teaching && <p className="muted">{status.helper_reason}</p>
      )}
    </div>
  );
}

function Switches({ siteId, status, onStatus }: { siteId: number; status: AiStatus; onStatus: (status: AiStatus) => void }) {
  const [error, setError] = useState<string | null>(null);
  async function set(change: Partial<Pick<AiStatus, "drafts" | "study_helper">>) {
    try {
      onStatus(await patch<AiStatus>(`/sites/${siteId}/ai/`, change));
      setError(null);
    } catch (err) {
      setError(errorMessage(err, "Could not change AI help for this course."));
    }
  }
  return (
    <section aria-labelledby="ai-switches" className="panel-card padded">
      <h2 id="ai-switches">AI help on this course</h2>
      <p className="muted small">The model runs on GSA's own server. It is sent course material and questions, never anything else about students.</p>
      <fieldset className="stack">
        <legend>Switched on</legend>
        <label className="inline">
          <input type="checkbox" checked={status.drafts} onChange={(e) => set({ drafts: e.target.checked })} /> Drafts for teaching staff
        </label>
        <label className="inline">
          <input type="checkbox" checked={status.study_helper} onChange={(e) => set({ study_helper: e.target.checked })} /> Study helper for students
          (off while a quiz or assignment is open to them)
        </label>
      </fieldset>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}

/** Tell the server a reviewed draft was saved, so the audit log marks the record as AI-drafted. */
const markSaved = (draft: number, record: "question" | "rubric" | "content", id: number) =>
  post(`/ai/drafts/${draft}/saved/`, { record, id }).catch(() => undefined);

function QuestionDrafts({ siteId, modules }: { siteId: number; modules: Module[] }) {
  const items = modules.flatMap((m) => m.items.filter((i) => i.kind === "page" || (i.kind === "file" && /\.(docx|pptx)$/i.test(i.filename ?? ""))));
  const [item, setItem] = useState<number | "">(items[0]?.id ?? "");
  const [count, setCount] = useState("5");
  const [draft, setDraft] = useState<Draft<{ questions: DraftQuestion[] }> | null>(null);
  const [banks, setBanks] = useState<QuestionBank[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    get<Paginated<QuestionBank>>("/question-banks/")
      .then((page) => setBanks(page.results.filter((b) => b.site === siteId && b.can_manage)))
      .catch(() => setBanks([]));
  }, [siteId]);

  async function ask(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      setDraft(await post<Draft<{ questions: DraftQuestion[] }>>(`/sites/${siteId}/ai/drafts/questions/`, { item, count: Number(count) }));
    } catch (err) {
      setError(errorMessage(err, "Could not draft questions."));
    } finally {
      setBusy(false);
    }
  }

  const change = (index: number, question: DraftQuestion | null) =>
    setDraft((d) => d && { ...d, output: { questions: d.output.questions.flatMap((q, i) => (i === index ? (question ? [question] : []) : [q])) } });

  return (
    <section aria-labelledby="ai-questions">
      <h2 id="ai-questions">Draft questions from your material</h2>
      {items.length === 0 ? (
        <p className="muted">Put up a page, or a Word or PowerPoint file, in Content first.</p>
      ) : (
        <form className="form-row" onSubmit={ask}>
          <label className="grow">
            From
            <select value={item} onChange={(e) => setItem(Number(e.target.value))}>
              {items.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            How many
            <input type="number" min={1} max={10} inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value)} />
          </label>
          <div className="actions">
            <button type="submit" disabled={busy}>
              {busy ? "Drafting…" : "Draft questions"}
            </button>
          </div>
        </form>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {saved && (
        <p role="status" className="notice good">
          {saved}
        </p>
      )}
      {draft && draft.output.questions.length > 0 && (
        <>
          <p className="notice">Drafted with AI help. Check every question and its answers, and change them, before you save.</p>
          <ul className="plain tool-list" aria-label="Drafted questions">
            {draft.output.questions.map((q, index) => (
              <QuestionCard
                key={`${draft.draft}-${index}`}
                question={q}
                banks={banks}
                onChange={(next) => change(index, next)}
                onSave={async (bank) => {
                  const made = await post<{ id: number }>("/questions/", { ...q, bank, default_mark: "1" });
                  await markSaved(draft.draft, "question", made.id);
                  change(index, null);
                  setSaved(`Saved “${q.name}” to the bank.`);
                }}
              />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function QuestionCard({
  question,
  banks,
  onChange,
  onSave,
}: {
  question: DraftQuestion;
  banks: QuestionBank[];
  onChange: (question: DraftQuestion | null) => void;
  onSave: (bank: number) => Promise<void>;
}) {
  const [bank, setBank] = useState<number | "">(banks[0]?.id ?? "");
  const [error, setError] = useState<string | null>(null);
  const choices = question.data.choices;
  const setChoice = (index: number, change: Partial<(typeof choices)[number]>) =>
    onChange({ ...question, data: { ...question.data, choices: choices.map((c, i) => (i === index ? { ...c, ...change } : c)) } });
  const chosenBank = bank === "" ? banks[0]?.id : bank;
  return (
    <li className="panel-card padded draft-card">
      <div className="stack">
        <label>
          Name
          <input value={question.name} onChange={(e) => onChange({ ...question, name: e.target.value })} />
        </label>
        <label>
          Question
          <textarea value={question.text} onChange={(e) => onChange({ ...question, text: e.target.value })} />
        </label>
        <fieldset className="stack">
          <legend>Choices (the right one marked)</legend>
          {choices.map((c, i) => (
            <div key={i} className="draft-choice">
              <input
                type="radio"
                name={`right-${question.name}-${question.text.length}`}
                checked={c.fraction === 1}
                onChange={() => onChange({ ...question, data: { ...question.data, choices: choices.map((x, j) => ({ ...x, fraction: j === i ? 1 : 0 })) } })}
                aria-label={`Choice ${i + 1} is right`}
              />
              <input value={c.text} onChange={(e) => setChoice(i, { text: e.target.value })} aria-label={`Choice ${i + 1}`} />
            </div>
          ))}
        </fieldset>
        <label>
          Feedback after answering
          <textarea value={question.general_feedback} onChange={(e) => onChange({ ...question, general_feedback: e.target.value })} />
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        {banks.length > 0 ? (
          <>
            <label>
              Bank
              <select value={chosenBank} onChange={(e) => setBank(Number(e.target.value))}>
                {banks.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => chosenBank !== undefined && onSave(chosenBank).catch((err) => setError(errorMessage(err, "Could not save the question.")))}
            >
              Save to the bank
            </button>
          </>
        ) : (
          <p className="muted small">Make a question bank for this course in Quizzes to save questions.</p>
        )}
        <button type="button" className="secondary" onClick={() => onChange(null)}>
          Leave out
        </button>
      </div>
    </li>
  );
}

function RubricDraft({ siteId }: { siteId: number }) {
  const [title, setTitle] = useState("");
  const [task, setTask] = useState("");
  const [criteria, setCriteria] = useState("");
  const [levels, setLevels] = useState("4");
  const [draft, setDraft] = useState<Draft<DraftRubric> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  async function ask(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      const names = criteria.split("\n").map((c) => c.trim()).filter(Boolean);
      setDraft(await post<Draft<DraftRubric>>(`/sites/${siteId}/ai/drafts/rubric/`, { title, task, criteria: names, levels: Number(levels) }));
    } catch (err) {
      setError(errorMessage(err, "Could not draft the rubric."));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!draft) return;
    try {
      const made = await post<{ id: number }>("/rubrics/", { site: siteId, title: draft.output.title, kind: "scored", criteria: draft.output.criteria });
      await markSaved(draft.draft, "rubric", made.id);
      setSaved(`Saved the rubric “${draft.output.title}”. Find it in the assignment's rubric list.`);
      setDraft(null);
    } catch (err) {
      setError(errorMessage(err, "Could not save the rubric."));
    }
  }

  const setLevel = (c: number, l: number, description: string) =>
    setDraft(
      (d) =>
        d && {
          ...d,
          output: {
            ...d.output,
            criteria: d.output.criteria.map((row, i) => (i === c ? { ...row, levels: row.levels.map((lv, j) => (j === l ? { ...lv, description } : lv)) } : row)),
          },
        },
    );

  return (
    <section aria-labelledby="ai-rubric">
      <h2 id="ai-rubric">Draft a rubric's wording</h2>
      <form className="stack sub-form" onSubmit={ask}>
        <label>
          Rubric title
          <input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={160} />
        </label>
        <label>
          What the students are asked to do
          <textarea value={task} onChange={(e) => setTask(e.target.value)} required />
        </label>
        <label>
          Criteria, one on each line
          <textarea value={criteria} onChange={(e) => setCriteria(e.target.value)} required />
        </label>
        <label>
          Levels for each criterion
          <select value={levels} onChange={(e) => setLevels(e.target.value)}>
            {[2, 3, 4, 5, 6].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <div className="actions">
          <button type="submit" disabled={busy}>
            {busy ? "Drafting…" : "Draft the wording"}
          </button>
        </div>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {saved && (
        <p role="status" className="notice good">
          {saved}
        </p>
      )}
      {draft && (
        <div className="panel-card padded draft-card">
          <p className="notice">Drafted with AI help. Check and change every level before you save.</p>
          {draft.output.criteria.map((row, c) => (
            <fieldset key={row.title} className="stack">
              <legend>{row.title}</legend>
              {row.levels.map((lv, l) => (
                <label key={l}>
                  {lv.points} points
                  <textarea value={lv.description} onChange={(e) => setLevel(c, l, e.target.value)} />
                </label>
              ))}
            </fieldset>
          ))}
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setDraft(null)}>
              Discard
            </button>
            <button type="button" onClick={save}>
              Save as a rubric of this course
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function Helper({ siteId }: { siteId: number }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<HelperAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setAnswer(await post<HelperAnswer>(`/sites/${siteId}/ai/ask/`, { question }));
    } catch (err) {
      setAnswer(null);
      setError(err instanceof ApiError ? err.detail : "Could not ask the study helper.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="ai-helper">
      <h2 id="ai-helper">Study helper</h2>
      <p className="muted small">It answers only from this course's material and shows where the answer comes from. Your question is not kept.</p>
      <form className="stack" onSubmit={ask}>
        <label>
          Your question
          <textarea value={question} onChange={(e) => setQuestion(e.target.value)} required maxLength={1000} />
        </label>
        <div className="actions">
          <button type="submit" disabled={busy}>
            {busy ? "Looking…" : "Ask"}
          </button>
        </div>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {answer && (
        <div className="panel-card padded" role="status">
          <p className={answer.answered ? "ai-answer" : "notice"}>{answer.answer}</p>
          {answer.sources.length > 0 && (
            <>
              <p className="small">
                <strong>From the course's material</strong>
              </p>
              <ol className="sources">
                {answer.sources.map((s) => (
                  <li key={s.item}>
                    <a href={`#${s.link}`}>{s.title}</a> <span className="muted small">({s.module})</span>
                  </li>
                ))}
              </ol>
            </>
          )}
          {answer.answered && <p className="muted small">Drafted by AI from the pages above. Check it against them.</p>}
        </div>
      )}
    </section>
  );
}
