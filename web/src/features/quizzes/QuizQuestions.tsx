import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, patch, post, remove } from "../../api/client";
import { QTYPE_LABEL, type Question, type QuestionBank, type QuestionCategory, type Quiz, type QuizSlot } from "../../api/types-quizzes";
import { getAll, plainText } from "./quizUtil";

/** The quiz's slots, and the banks, questions and categories this site may build it from. */
async function fetchSlots(quizId: number, siteId: number) {
  const rows = await getAll<QuizSlot>(`/quiz-slots/?quiz=${quizId}`);
  const usable = (await getAll<QuestionBank>("/question-banks/")).filter((b) => b.site === null || b.site === siteId);
  const [qs, cs] = await Promise.all([
    Promise.all(usable.map((b) => getAll<Question>(`/questions/?bank=${b.id}&archived=1`))),
    Promise.all(usable.map((b) => getAll<QuestionCategory>(`/question-categories/?bank=${b.id}`))),
  ]);
  return { rows, usable, qs: qs.flat(), cs: cs.flat() };
}

interface Props {
  quiz: Quiz;
  siteId: number;
  onChanged: () => void;
}

/**
 * The questions of a quiz (item 3.02): fixed questions, or a number drawn at random from a category for each
 * attempt. They cannot change once a student has made an attempt; the server says so.
 */
export function QuizQuestions({ quiz, siteId, onChanged }: Props) {
  const [loaded, setSlots] = useState<QuizSlot[] | null>(null);
  const slots = loaded ?? [];
  const [questions, setQuestions] = useState<Record<number, Question>>({});
  const [categories, setCategories] = useState<Record<number, QuestionCategory>>({});
  const [banks, setBanks] = useState<QuestionBank[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(
    () =>
      fetchSlots(quiz.id, siteId)
        .then(({ rows, usable, qs, cs }) => {
          setSlots(rows);
          setBanks(usable);
          setQuestions(Object.fromEntries(qs.map((q) => [q.id, q])));
          setCategories(Object.fromEntries(cs.map((c) => [c.id, c])));
          setError(null);
        })
        .catch((err) => setError(errorMessage(err, "Could not load the questions."))),
    [quiz.id, siteId],
  );
  useEffect(() => {
    void load();
  }, [load]);

  async function act(work: () => Promise<unknown>) {
    try {
      await work();
      setError(null);
      await load();
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not change the questions."));
    }
  }

  // Moving one entry numbers them all again, 1, 2, 3 ..., so the order is always plain.
  const swap = (i: number, j: number) =>
    act(async () => {
      const order = [...slots];
      [order[i], order[j]] = [order[j], order[i]];
      for (const [index, slot] of order.entries())
        if (slot.position !== index + 1) await patch(`/quiz-slots/${slot.id}/`, { position: index + 1 });
    });

  // Nothing can be added until the banks and questions are in.
  if (loaded === null && !error) return <p className="loading">Loading the questions…</p>;

  const nextPosition = slots.length ? Math.max(...slots.map((s) => s.position)) + 1 : 1;

  return (
    <>
      <p className="muted">
        {slots.length === 0 ? "No questions yet." : `${slots.length} ${slots.length === 1 ? "entry" : "entries"}, worth ${Number(quiz.max_mark)} marks in all.`}
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <ol className="plain slot-list">
        {slots.map((slot, i) => {
          const q = slot.question ? questions[slot.question] : null;
          const cat = slot.category ? categories[slot.category] : null;
          const name = q ? q.name : `${slot.random_count} random from “${cat?.name ?? "a category"}”${slot.tag ? ` tagged ${slot.tag}` : ""}`;
          return (
            <li key={slot.id} className="module">
              <div className="panel-head">
                <div>
                  <strong>
                    {i + 1}. {name}
                  </strong>
                  <p className="muted small">
                    {q ? `${QTYPE_LABEL[q.qtype]} · ${plainText(q.latest.text_html).slice(0, 90)}` : slot.include_subcategories ? "Includes the categories inside it" : "This category only"}
                  </p>
                </div>
                <label className="slot-mark">
                  Mark{slot.question ? "" : " each"}
                  <input
                    type="number"
                    min={0.01}
                    step="0.01"
                    defaultValue={slot.mark ?? (q ? q.latest.default_mark : "1")}
                    onBlur={(e) => {
                      if (e.target.value && e.target.value !== (slot.mark ?? "")) void act(() => patch(`/quiz-slots/${slot.id}/`, { mark: e.target.value }));
                    }}
                  />
                </label>
              </div>
              <div className="actions">
                <button className="secondary small-button" disabled={i === 0} onClick={() => void swap(i, i - 1)} aria-label={`Move up: ${name}`}>
                  Up
                </button>
                <button className="secondary small-button" disabled={i === slots.length - 1} onClick={() => void swap(i, i + 1)} aria-label={`Move down: ${name}`}>
                  Down
                </button>
                <button className="secondary danger-text small-button" onClick={() => void act(() => remove(`/quiz-slots/${slot.id}/`))} aria-label={`Remove: ${name}`}>
                  Remove
                </button>
              </div>
            </li>
          );
        })}
      </ol>
      {adding ? (
        <AddSlot
          quiz={quiz}
          banks={banks}
          questions={Object.values(questions)}
          categories={Object.values(categories)}
          used={new Set(slots.map((s) => s.question).filter((x): x is number => x !== null))}
          position={nextPosition}
          onAdd={(body) => act(() => post("/quiz-slots/", body))}
          onClose={() => setAdding(false)}
        />
      ) : (
        <div className="actions">
          <button onClick={() => setAdding(true)}>Add questions</button>
        </div>
      )}
    </>
  );
}

interface AddProps {
  quiz: Quiz;
  banks: QuestionBank[];
  questions: Question[];
  categories: QuestionCategory[];
  used: Set<number>;
  position: number;
  onAdd: (body: Record<string, unknown>) => Promise<void>;
  onClose: () => void;
}

function AddSlot({ quiz, banks, questions, categories, used, position, onAdd, onClose }: AddProps) {
  const [chosen, setBank] = useState<number | "">("");
  const bank = chosen === "" ? (banks[0]?.id ?? "") : chosen;
  const [mode, setMode] = useState<"fixed" | "random">("fixed");
  const [category, setCategory] = useState<number | "">("");
  const [tag, setTag] = useState("");
  const [count, setCount] = useState("1");
  const [sub, setSub] = useState(true);
  const inBank = questions.filter((q) => q.bank === bank && !q.is_archived);
  const cats = categories.filter((c) => c.bank === bank);
  const shown = inBank.filter((q) => (category === "" || q.category === category) && (!tag || q.tags.includes(tag.trim().toLowerCase())));

  async function random(e: FormEvent) {
    e.preventDefault();
    await onAdd({ quiz: quiz.id, position, category, random_count: Number(count), include_subcategories: sub, tag: tag.trim().toLowerCase() });
    onClose();
  }

  if (banks.length === 0)
    return (
      <p className="notice">
        There is no question bank yet. Open <a href={`#/sites/${quiz.site}/quizzes/banks`}>Question banks</a> to make one and write questions.
      </p>
    );
  return (
    <section className="sub-form stack" aria-labelledby="add-head">
      <h3 id="add-head">Add questions</h3>
      <div className="grid2">
        <label>
          From the bank
          <select value={bank} onChange={(e) => setBank(Number(e.target.value))}>
            {banks.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name} ({b.owner_label})
              </option>
            ))}
          </select>
        </label>
        <label>
          Category
          <select value={category} onChange={(e) => setCategory(e.target.value ? Number(e.target.value) : "")} required={mode === "random"}>
            <option value="">{mode === "random" ? "Choose…" : "Every category"}</option>
            {cats.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tag (optional)
          <input value={tag} onChange={(e) => setTag(e.target.value)} />
        </label>
      </div>
      <fieldset className="actions">
        <legend>Add</legend>
        <label className="inline">
          <input type="radio" name="slot-mode" checked={mode === "fixed"} onChange={() => setMode("fixed")} />
          Chosen questions
        </label>
        <label className="inline">
          <input type="radio" name="slot-mode" checked={mode === "random"} onChange={() => setMode("random")} />
          Random questions for each attempt
        </label>
      </fieldset>
      {mode === "fixed" ? (
        shown.length === 0 ? (
          <p className="muted">No questions match.</p>
        ) : (
          <ul className="plain">
            {shown.map((q) => (
              <li key={q.id} className="pick-row">
                <span>
                  <strong>{q.name}</strong>
                  <span className="muted small"> · {QTYPE_LABEL[q.qtype]}</span>
                </span>
                <button className="secondary small-button" disabled={used.has(q.id)} onClick={() => void onAdd({ quiz: quiz.id, position, question: q.id })} aria-label={`Add “${q.name}”`}>
                  {used.has(q.id) ? "Added" : "Add"}
                </button>
              </li>
            ))}
          </ul>
        )
      ) : (
        <form className="form-row" onSubmit={random}>
          <label>
            How many
            <input type="number" min={1} value={count} onChange={(e) => setCount(e.target.value)} required />
          </label>
          <label className="inline">
            <input type="checkbox" checked={sub} onChange={(e) => setSub(e.target.checked)} />
            Include the categories inside it
          </label>
          <div className="actions">
            <button type="submit" disabled={category === ""}>
              Add random questions
            </button>
          </div>
        </form>
      )}
      <div className="actions">
        <button className="secondary" onClick={onClose}>
          Done
        </button>
      </div>
    </section>
  );
}
