import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ApiError, errorMessage, patch, post } from "../../api/client";
import { QTYPE_LABEL, type QType, type Question, type QuestionCategory, type QuestionData } from "../../api/types-quizzes";
import { blankData, blankGap, gapKeys } from "./quizUtil";
import { ZoneEditor } from "./ZoneEditor";

/** Moodle's grade steps, as a share of the question's mark. Negatives only for several right answers. */
const STEPS = [100, 90, 83.33333, 80, 75, 70, 66.66667, 60, 50, 40, 33.33333, 30, 25, 20, 16.66667, 14.28571, 12.5, 11.11111, 10, 5, 0];

interface Props {
  bankId: number;
  categories: QuestionCategory[];
  /** The question to change; null with qtype for a new one. */
  question: Question | null;
  qtype: QType;
  onSaved: (question: Question) => void;
  onCancel: () => void;
}

/**
 * Writing or changing a question of any type (item 3.01). The server checks every setting (quizzes.schemas) and
 * says what is wrong; a question an attempt has used keeps that version, and the change becomes a new one.
 */
export function QuestionEditor({ bankId, categories, question, qtype, onSaved, onCancel }: Props) {
  const latest = question?.latest;
  const [name, setName] = useState(question?.name ?? "");
  const [category, setCategory] = useState<number | "">(question?.category ?? categories[0]?.id ?? "");
  const [tags, setTags] = useState((question?.tags ?? []).join(", "));
  const [text, setText] = useState(latest?.text ?? "");
  const [mark, setMark] = useState(latest?.default_mark ?? "1");
  const [general, setGeneral] = useState(latest?.general_feedback ?? "");
  const [data, setData] = useState<QuestionData>(() => (latest ? structuredClone(latest.data) : blankData(qtype)));
  const [image, setImage] = useState<File | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const head = useRef<HTMLHeadingElement>(null);
  // The editor comes into view, and to the keyboard, when it opens.
  useEffect(() => head.current?.focus(), []);
  const preview = useMemo(() => (image ? URL.createObjectURL(image) : (latest?.image_url ?? null)), [image, latest]);
  useEffect(() => () => void (image && preview && URL.revokeObjectURL(preview)), [image, preview]);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (qtype === "image_label" && !image && !latest?.image_url) {
      setErrors(["Choose the image the labels go on."]);
      return;
    }
    setSaving(true);
    setErrors([]);
    const sent = { ...data };
    if (qtype === "cloze") {
      const keys = gapKeys(text);
      sent.gaps = Object.fromEntries(keys.map((k) => [k, data.gaps?.[k] ?? blankGap()]));
    }
    if (qtype === "matching") sent.extra_answers = (data.extra_answers ?? []).filter((x: string) => x.trim());
    const body = {
      bank: bankId,
      category: category === "" ? null : category,
      qtype,
      name,
      tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
      text,
      data: sent,
      default_mark: mark,
      general_feedback: general,
    };
    try {
      let saved = question ? await patch<Question>(`/questions/${question.id}/`, body) : await post<Question>("/questions/", body);
      if (image) {
        const form = new FormData();
        form.set("image", image);
        saved = await post<Question>(`/questions/${saved.id}/image/`, form);
      }
      onSaved(saved);
    } catch (err) {
      // The server lists every problem with the settings; show them all, not only the first.
      const fields = err instanceof ApiError ? err.fields : undefined;
      setErrors(fields ? Object.entries(fields).flatMap(([key, v]) => [v].flat().map((m) => (key === "data" || key === "non_field_errors" ? String(m) : `${key.replace(/_/g, " ")}: ${m}`))) : [errorMessage(err, "Could not save the question.")]);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="stack question-editor" onSubmit={save} aria-labelledby="editor-head">
      <h3 id="editor-head" tabIndex={-1} ref={head}>
        {question ? `Change: ${question.name}` : `New question: ${QTYPE_LABEL[qtype]}`}
        {question && latest?.in_use && <span className="muted small"> (used in an attempt: saving makes version {latest.number + 1})</span>}
      </h3>
      <div className="grid2">
        <label>
          Name (for the bank; students do not see it)
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} />
        </label>
        <label>
          Category
          <select value={category} onChange={(e) => setCategory(e.target.value ? Number(e.target.value) : "")}>
            <option value="">No category</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tags, separated by commas
          <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="soils, week 1" />
        </label>
        <label>
          Default mark
          <input type="number" min={0.01} step="0.01" value={mark} onChange={(e) => setMark(e.target.value)} required />
        </label>
        <label className="span2">
          Question text
          <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} required />
          {qtype === "cloze" && (
            <span className="muted small" style={{ fontWeight: 400 }}>
              Write a gap as [[1]], [[2]] and so on where the student fills it in.
            </span>
          )}
        </label>
      </div>
      <TypeSettings qtype={qtype} text={text} setText={setText} data={data} setData={setData} />
      {qtype === "image_label" && (
        <>
          <label>
            The image (PNG, JPG or WEBP; at most 5 MB)
            <input type="file" accept=".png,.jpg,.jpeg,.webp" onChange={(e) => setImage(e.target.files?.[0] ?? null)} />
          </label>
          {preview && (
            <img
              src={preview}
              alt=""
              hidden
              onLoad={(e) => {
                const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
                if (w && h && (w !== data.image_width || h !== data.image_height)) setData((d) => ({ ...d, image_width: w, image_height: h }));
              }}
            />
          )}
          <ZoneEditor src={preview} data={data} onChange={setData} />
        </>
      )}
      <label>
        General feedback (shown with the review, whatever the answer)
        <textarea value={general} onChange={(e) => setGeneral(e.target.value)} />
      </label>
      {errors.length > 0 && (
        <div role="alert" className="notice bad">
          <strong>The question was not saved:</strong>
          <ul>
            {errors.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="actions">
        <button type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save question"}
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

interface TypeProps {
  qtype: QType;
  text: string;
  setText: (t: string) => void;
  data: QuestionData;
  setData: (d: QuestionData | ((d: QuestionData) => QuestionData)) => void;
}

/** A row of a repeated list (choices, pairs, answers), with its own legend and a Remove button. */
function Row({ legend, onRemove, children }: { legend: string; onRemove?: () => void; children: ReactNode }) {
  return (
    <fieldset className="edit-row">
      <legend>{legend}</legend>
      <div className="grid2">{children}</div>
      {onRemove && (
        <button type="button" className="secondary danger-text small-button" onClick={onRemove} aria-label={`Remove ${legend.toLowerCase()}`}>
          Remove
        </button>
      )}
    </fieldset>
  );
}

function Fraction({ value, negative, onChange, label = "Share of the mark" }: { value: number; negative?: boolean; onChange: (v: number) => void; label?: string }) {
  const steps = negative ? [...STEPS, ...STEPS.slice(0, -1).reverse().map((s) => -s)] : STEPS;
  const percent = Number(value) * 100;
  const known = steps.find((s) => Math.abs(s - percent) < 0.01);
  const options = known === undefined ? [...steps, percent] : steps;
  return (
    <label>
      {label}
      <select value={String(known ?? percent)} onChange={(e) => onChange(Number(e.target.value) / 100)}>
        {options.map((s) => (
          <option key={s} value={String(s)}>
            {s === 0 ? "None" : `${Number(s.toFixed(2))}%`}
          </option>
        ))}
      </select>
    </label>
  );
}

function list<T>(data: QuestionData, key: string): T[] {
  return (data[key] as T[]) ?? [];
}

function TypeSettings({ qtype, text, setText, data, setData }: TypeProps) {
  const update = (key: string, index: number, change: Record<string, unknown>) =>
    setData((d) => ({ ...d, [key]: list<Record<string, unknown>>(d, key).map((row, i) => (i === index ? { ...row, ...change } : row)) }));
  const add = (key: string, row: Record<string, unknown>) => setData((d) => ({ ...d, [key]: [...list(d, key), row] }));
  const drop = (key: string, index: number) => setData((d) => ({ ...d, [key]: list(d, key).filter((_, i) => i !== index) }));
  const flag = (key: string, label: string) => (
    <label className="inline">
      <input type="checkbox" checked={!!data[key]} onChange={(e) => setData((d) => ({ ...d, [key]: e.target.checked }))} />
      {label}
    </label>
  );

  switch (qtype) {
    case "multichoice": {
      const choices = list<{ text: string; fraction: number; feedback: string }>(data, "choices");
      return (
        <div className="stack">
          <fieldset className="actions">
            <legend>Right answers</legend>
            <label className="inline">
              <input type="radio" name="mc-single" checked={data.single} onChange={() => setData((d) => ({ ...d, single: true }))} />
              One right answer
            </label>
            <label className="inline">
              <input type="radio" name="mc-single" checked={!data.single} onChange={() => setData((d) => ({ ...d, single: false }))} />
              Several right answers
            </label>
          </fieldset>
          {flag("shuffle", "Shuffle the choices")}
          {choices.map((c, i) => (
            <Row key={i} legend={`Choice ${i + 1}`} onRemove={choices.length > 2 ? () => drop("choices", i) : undefined}>
              <label className="span2">
                Text
                <input value={c.text} onChange={(e) => update("choices", i, { text: e.target.value })} required />
              </label>
              <Fraction value={c.fraction} negative={!data.single} onChange={(v) => update("choices", i, { fraction: v })} />
              <label>
                Feedback if chosen
                <input value={c.feedback} onChange={(e) => update("choices", i, { feedback: e.target.value })} />
              </label>
            </Row>
          ))}
          <div className="actions">
            <button type="button" className="secondary small-button" onClick={() => add("choices", { text: "", fraction: 0, feedback: "" })}>
              Add a choice
            </button>
          </div>
        </div>
      );
    }
    case "truefalse":
      return (
        <div className="stack">
          <fieldset className="actions">
            <legend>The statement is</legend>
            {[true, false].map((v) => (
              <label key={String(v)} className="inline">
                <input type="radio" name="tf-correct" checked={data.correct === v} onChange={() => setData((d) => ({ ...d, correct: v }))} />
                {v ? "True" : "False"}
              </label>
            ))}
          </fieldset>
          <div className="grid2">
            <label>
              Feedback for “True”
              <input value={data.feedback_true ?? ""} onChange={(e) => setData((d) => ({ ...d, feedback_true: e.target.value }))} />
            </label>
            <label>
              Feedback for “False”
              <input value={data.feedback_false ?? ""} onChange={(e) => setData((d) => ({ ...d, feedback_false: e.target.value }))} />
            </label>
          </div>
        </div>
      );
    case "matching": {
      const pairs = list<{ prompt: string; answer: string }>(data, "pairs");
      return (
        <div className="stack">
          {pairs.map((p, i) => (
            <Row key={i} legend={`Pair ${i + 1}`} onRemove={pairs.length > 2 ? () => drop("pairs", i) : undefined}>
              <label>
                Item
                <input value={p.prompt} onChange={(e) => update("pairs", i, { prompt: e.target.value })} required />
              </label>
              <label>
                Its match
                <input value={p.answer} onChange={(e) => update("pairs", i, { answer: e.target.value })} required />
              </label>
            </Row>
          ))}
          <div className="actions">
            <button type="button" className="secondary small-button" onClick={() => add("pairs", { prompt: "", answer: "" })}>
              Add a pair
            </button>
          </div>
          <label>
            Wrong matches to add to the list, one on each line
            <textarea value={(data.extra_answers ?? []).join("\n")} onChange={(e) => setData((d) => ({ ...d, extra_answers: e.target.value.split("\n") }))} />
          </label>
          {flag("shuffle", "Shuffle the items")}
        </div>
      );
    }
    case "ordering": {
      const items = list<{ id?: string; text: string }>(data, "items");
      const move = (i: number, by: number) =>
        setData((d) => {
          const next = [...list(d, "items")];
          [next[i], next[i + by]] = [next[i + by], next[i]];
          return { ...d, items: next };
        });
      return (
        <div className="stack">
          <p className="muted small">Write the items in the right order; students see them mixed.</p>
          {items.map((item, i) => (
            <div key={i} className="form-row">
              <label className="grow">
                Item {i + 1}
                <input value={item.text} onChange={(e) => update("items", i, { text: e.target.value })} required />
              </label>
              <div className="actions">
                <button type="button" className="secondary small-button" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Move item ${i + 1} up`}>
                  Up
                </button>
                <button type="button" className="secondary small-button" disabled={i === items.length - 1} onClick={() => move(i, 1)} aria-label={`Move item ${i + 1} down`}>
                  Down
                </button>
                {items.length > 2 && (
                  <button type="button" className="secondary danger-text small-button" onClick={() => drop("items", i)} aria-label={`Remove item ${i + 1}`}>
                    Remove
                  </button>
                )}
              </div>
            </div>
          ))}
          <div className="actions">
            <button type="button" className="secondary small-button" onClick={() => add("items", { text: "" })}>
              Add an item
            </button>
          </div>
          <label>
            Marking
            <select value={data.grading} onChange={(e) => setData((d) => ({ ...d, grading: e.target.value }))}>
              <option value="absolute_position">A share for each item in its right place</option>
              <option value="all_or_nothing">All in the right order, or nothing</option>
            </select>
          </label>
        </div>
      );
    }
    case "shortanswer":
      return (
        <div className="stack">
          <TextAnswers answers={list(data, "answers")} onChange={(answers) => setData((d) => ({ ...d, answers }))} hint="A * stands for any letters: “photo*” accepts photosynthesis." />
          {flag("case_sensitive", "Capital letters must match")}
        </div>
      );
    case "numerical":
      return <NumericalSettings data={data} setData={setData} />;
    case "cloze": {
      const keys = gapKeys(text);
      const gaps = (data.gaps ?? {}) as Record<string, ReturnType<typeof blankGap>>;
      const setGap = (key: string, gap: ReturnType<typeof blankGap>) => setData((d) => ({ ...d, gaps: { ...(d.gaps ?? {}), [key]: gap } }));
      const next = String(Math.max(0, ...keys.map(Number)) + 1);
      return (
        <div className="stack">
          {keys.length === 0 && <p className="muted">No gaps yet.</p>}
          {keys.map((key) => {
            const gap = gaps[key] ?? blankGap();
            return (
              <fieldset key={key} className="stack edit-row">
                <legend>Gap {key}</legend>
                <div className="grid2">
                  <label>
                    The student
                    <select value={gap.kind} onChange={(e) => setGap(key, { ...gap, kind: e.target.value, answers: e.target.value === "numerical" ? [{ value: "", tolerance: 0, fraction: 1, feedback: "" }] as never : gap.answers })}>
                      <option value="short">Types a word or words</option>
                      <option value="numerical">Types a number</option>
                      <option value="choice">Chooses from a list</option>
                    </select>
                  </label>
                  <label>
                    Weight within the question
                    <input type="number" min={0.1} step="0.1" value={gap.weight} onChange={(e) => setGap(key, { ...gap, weight: Number(e.target.value) })} />
                  </label>
                </div>
                {gap.kind === "numerical" ? (
                  <NumericAnswers answers={gap.answers as never} onChange={(answers) => setGap(key, { ...gap, answers: answers as never })} />
                ) : (
                  <TextAnswers
                    answers={gap.answers}
                    onChange={(answers) => setGap(key, { ...gap, answers })}
                    hint={gap.kind === "choice" ? "Every answer here is offered in the list; give the wrong ones no share." : undefined}
                    allowZero={gap.kind === "choice"}
                  />
                )}
              </fieldset>
            );
          })}
          <div className="actions">
            <button type="button" className="secondary small-button" onClick={() => setText(`${text}${text.endsWith(" ") || !text ? "" : " "}[[${next}]]`)}>
              Add a gap at the end of the text
            </button>
          </div>
        </div>
      );
    }
    case "essay":
      return (
        <div className="grid2">
          <label>
            Fewest words (optional)
            <input type="number" min={0} value={data.min_words ?? ""} onChange={(e) => setData((d) => ({ ...d, min_words: e.target.value === "" ? null : Number(e.target.value) }))} />
          </label>
          <label>
            Most words (optional)
            <input type="number" min={0} value={data.max_words ?? ""} onChange={(e) => setData((d) => ({ ...d, max_words: e.target.value === "" ? null : Number(e.target.value) }))} />
          </label>
          <label className="span2">
            Starting text for the answer (optional)
            <textarea value={data.response_template ?? ""} onChange={(e) => setData((d) => ({ ...d, response_template: e.target.value }))} />
          </label>
          <label className="span2">
            Notes for the marker (students do not see them)
            <textarea value={data.grader_info ?? ""} onChange={(e) => setData((d) => ({ ...d, grader_info: e.target.value }))} />
          </label>
        </div>
      );
    case "file": {
      const allowed = new Set<string>(data.allowed_extensions ?? []);
      return (
        <div className="stack">
          <fieldset className="actions">
            <legend>File types accepted</legend>
            {["pdf", "docx", "xlsx", "pptx", "jpg", "jpeg", "png", "webp", "heic", "heif"].map((ext) => (
              <label key={ext} className="inline">
                <input
                  type="checkbox"
                  checked={allowed.has(ext)}
                  onChange={(e) => {
                    const next = new Set(allowed);
                    if (e.target.checked) next.add(ext);
                    else next.delete(ext);
                    setData((d) => ({ ...d, allowed_extensions: [...next] }));
                  }}
                />
                {ext.toUpperCase()}
              </label>
            ))}
          </fieldset>
          <div className="grid2">
            <label>
              Largest file in MB (1 to 20)
              <input type="number" min={1} max={20} value={data.max_size_mb} onChange={(e) => setData((d) => ({ ...d, max_size_mb: Number(e.target.value) }))} />
            </label>
            <label className="span2">
              Notes for the marker (students do not see them)
              <textarea value={data.grader_info ?? ""} onChange={(e) => setData((d) => ({ ...d, grader_info: e.target.value }))} />
            </label>
          </div>
        </div>
      );
    }
    case "image_label": {
      const labels = list<{ id: string; text: string }>(data, "labels");
      const freeId = () => {
        const taken = new Set(labels.map((l) => l.id));
        let i = 0;
        while (taken.has(i < 26 ? String.fromCharCode(97 + i) : `x${i}`)) i += 1;
        return i < 26 ? String.fromCharCode(97 + i) : `x${i}`;
      };
      return (
        <div className="stack">
          <label>
            How students answer
            <select value={data.mode} onChange={(e) => setData((d) => ({ ...d, mode: e.target.value }))}>
              <option value="drop_zones">They see the zones and choose a label for each</option>
              <option value="markers">The zones are hidden; they place each label on the image</option>
            </select>
          </label>
          {labels.map((l, i) => (
            <div key={l.id} className="form-row">
              <label className="grow">
                Label {i + 1}
                <input value={l.text} onChange={(e) => update("labels", i, { text: e.target.value })} required />
              </label>
              {labels.length > 1 && (
                <div className="actions">
                  <button
                    type="button"
                    className="secondary danger-text small-button"
                    onClick={() => setData((d) => ({ ...d, labels: labels.filter((_, j) => j !== i), zones: list<{ label: string }>(d, "zones").filter((z) => z.label !== l.id) }))}
                    aria-label={`Remove label ${i + 1}`}
                  >
                    Remove
                  </button>
                </div>
              )}
            </div>
          ))}
          <div className="actions">
            <button type="button" className="secondary small-button" onClick={() => add("labels", { id: freeId(), text: "" })}>
              Add a label
            </button>
          </div>
        </div>
      );
    }
  }
}

type TextAnswer = { text: string; fraction: number; feedback: string };

function TextAnswers({ answers, onChange, hint, allowZero }: { answers: TextAnswer[]; onChange: (a: TextAnswer[]) => void; hint?: string; allowZero?: boolean }) {
  const set = (i: number, change: Partial<TextAnswer>) => onChange(answers.map((a, j) => (j === i ? { ...a, ...change } : a)));
  return (
    <div className="stack">
      {hint && <p className="muted small">{hint}</p>}
      {answers.map((a, i) => (
        <Row key={i} legend={`Accepted answer ${i + 1}`} onRemove={answers.length > 1 ? () => onChange(answers.filter((_, j) => j !== i)) : undefined}>
          <label>
            Answer
            <input value={a.text} onChange={(e) => set(i, { text: e.target.value })} required />
          </label>
          <Fraction value={a.fraction} onChange={(v) => set(i, { fraction: v })} label={allowZero ? "Share of the mark (none for a wrong one)" : undefined} />
          <label className="span2">
            Feedback
            <input value={a.feedback} onChange={(e) => set(i, { feedback: e.target.value })} />
          </label>
        </Row>
      ))}
      <div className="actions">
        <button type="button" className="secondary small-button" onClick={() => onChange([...answers, { text: "", fraction: allowZero ? 0 : 1, feedback: "" }])}>
          Add an answer
        </button>
      </div>
    </div>
  );
}

type NumAnswer = { value: string | number | null; tolerance: number; fraction: number; feedback: string };

function NumericAnswers({ answers, onChange }: { answers: NumAnswer[]; onChange: (a: NumAnswer[]) => void }) {
  const set = (i: number, change: Partial<NumAnswer>) => onChange(answers.map((a, j) => (j === i ? { ...a, ...change } : a)));
  return (
    <div className="stack">
      {answers.map((a, i) => (
        <Row key={i} legend={`Accepted answer ${i + 1}`} onRemove={answers.length > 1 ? () => onChange(answers.filter((_, j) => j !== i)) : undefined}>
          <label>
            Number (* for any number)
            <input inputMode="decimal" value={a.value === null ? "*" : String(a.value)} onChange={(e) => set(i, { value: e.target.value === "*" ? null : e.target.value })} required />
          </label>
          <label>
            Give or take
            <input type="number" min={0} step="any" value={a.tolerance} onChange={(e) => set(i, { tolerance: Number(e.target.value) })} />
          </label>
          <Fraction value={a.fraction} onChange={(v) => set(i, { fraction: v })} />
          <label>
            Feedback
            <input value={a.feedback} onChange={(e) => set(i, { feedback: e.target.value })} />
          </label>
        </Row>
      ))}
      <div className="actions">
        <button type="button" className="secondary small-button" onClick={() => onChange([...answers, { value: "", tolerance: 0, fraction: 0.5, feedback: "" }])}>
          Add an answer
        </button>
      </div>
    </div>
  );
}

function NumericalSettings({ data, setData }: { data: QuestionData; setData: TypeProps["setData"] }) {
  const units: { unit: string; multiplier: number }[] = data.units ?? [];
  const setUnits = (next: typeof units) => setData((d) => ({ ...d, units: next }));
  return (
    <div className="stack">
      <NumericAnswers answers={data.answers ?? []} onChange={(answers) => setData((d) => ({ ...d, answers }))} />
      <fieldset className="stack">
        <legend>Units</legend>
        <label>
          Unit
          <select value={data.unit_mode} onChange={(e) => setData((d) => ({ ...d, unit_mode: e.target.value }))}>
            <option value="none">No unit</option>
            <option value="optional">Optional</option>
            <option value="required">Required</option>
          </select>
        </label>
        {data.unit_mode !== "none" && (
          <>
            {units.map((u, i) => (
              <div key={i} className="form-row">
                <label>
                  Unit {i + 1}
                  <input value={u.unit} onChange={(e) => setUnits(units.map((x, j) => (j === i ? { ...x, unit: e.target.value } : x)))} required />
                </label>
                <label>
                  Worth (1 for the main unit)
                  <input type="number" step="any" value={u.multiplier} onChange={(e) => setUnits(units.map((x, j) => (j === i ? { ...x, multiplier: Number(e.target.value) } : x)))} />
                </label>
                <div className="actions">
                  <button type="button" className="secondary danger-text small-button" onClick={() => setUnits(units.filter((_, j) => j !== i))} aria-label={`Remove unit ${i + 1}`}>
                    Remove
                  </button>
                </div>
              </div>
            ))}
            <div className="actions">
              <button type="button" className="secondary small-button" onClick={() => setUnits([...units, { unit: "", multiplier: units.length ? 1 : 1 }])}>
                Add a unit
              </button>
            </div>
            <label>
              Share taken off for a wrong or missing unit
              <select value={String(data.unit_penalty)} onChange={(e) => setData((d) => ({ ...d, unit_penalty: Number(e.target.value) }))}>
                {[...new Set([0, 0.1, 0.2, 0.25, 0.5, 1, Number(data.unit_penalty ?? 0.1)])].map((p) => (
                  <option key={p} value={String(p)}>
                    {Number((p * 100).toFixed(2))}%
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
      </fieldset>
    </div>
  );
}
