import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post, remove } from "../../api/client";
import { QTYPE_LABEL, type ExportResult, type ImportReport, type QType, type Question, type QuestionBank, type QuestionCategory } from "../../api/types-quizzes";
import { BackLink } from "./AttemptPlayer";
import { QuestionEditor } from "./QuestionEditor";
import { categoryTree, getAll, plainText } from "./quizUtil";

interface Props {
  siteId: number;
  onBack: () => void;
}

/**
 * Question banks (item 3.01): the course's own and those its department shares, with categories and tags, the
 * questions in them, import from Moodle XML, GIFT or QTI with a report of what was skipped and why, and export.
 */
export function BanksScreen({ siteId, onBack }: Props) {
  const [banks, setBanks] = useState<QuestionBank[] | null>(null);
  const [bankId, setBankId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(
    (select?: number) =>
      getAll<QuestionBank>("/question-banks/")
        .then((all) => {
          const rows = all.filter((b) => b.site === siteId || b.site === null);
          setBanks(rows);
          setBankId((current) => select ?? current ?? rows.find((b) => b.site === siteId)?.id ?? rows[0]?.id ?? null);
          setError(null);
        })
        .catch((err) => setError(errorMessage(err, "Could not load the question banks."))),
    [siteId],
  );
  useEffect(() => {
    void load();
  }, [load]);

  const bank = banks?.find((b) => b.id === bankId) ?? null;
  return (
    <>
      <BackLink onBack={onBack} />
      <h2>Question banks</h2>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {banks === null ? (
        <p className="loading">Loading…</p>
      ) : (
        <div className="form-row">
          {banks.length > 0 && (
            <label className="grow">
              Bank
              <select value={bankId ?? ""} onChange={(e) => setBankId(Number(e.target.value))}>
                {banks.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name} ({b.site ? "this course" : `department ${b.department_code}`})
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="actions">
            <button className="secondary" onClick={() => setCreating(!creating)} aria-expanded={creating}>
              New bank
            </button>
          </div>
        </div>
      )}
      {banks?.length === 0 && !creating && <p className="muted">No question banks yet. Make one for this course to start writing questions.</p>}
      {creating && (
        <NewBank
          siteId={siteId}
          onMade={(made) => {
            setCreating(false);
            void load(made.id);
          }}
        />
      )}
      {bank && <BankView key={bank.id} bank={bank} />}
    </>
  );
}

function NewBank({ siteId, onMade }: { siteId: number; onMade: (bank: QuestionBank) => void }) {
  const [name, setName] = useState("");
  const [owner, setOwner] = useState<"site" | "department">("site");
  const [department, setDepartment] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function make(e: FormEvent) {
    e.preventDefault();
    try {
      onMade(await post<QuestionBank>("/question-banks/", owner === "site" ? { name, site: siteId } : { name, department_code: department.trim().toUpperCase() }));
    } catch (err) {
      setError(errorMessage(err, "Could not make the bank."));
    }
  }
  return (
    <form className="stack sub-form" onSubmit={make}>
      <div className="grid2">
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Belongs to
          <select value={owner} onChange={(e) => setOwner(e.target.value as "site" | "department")}>
            <option value="site">This course</option>
            <option value="department">A department, shared with its teaching staff</option>
          </select>
        </label>
        {owner === "department" && (
          <label>
            Department code
            <input value={department} onChange={(e) => setDepartment(e.target.value)} required placeholder="CROPS" />
          </label>
        )}
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">Make the bank</button>
      </div>
    </form>
  );
}

type Panel = { kind: "none" } | { kind: "edit"; question: Question | null; qtype: QType } | { kind: "import" } | { kind: "export" } | { kind: "categories" };

function BankView({ bank }: { bank: QuestionBank }) {
  const [categories, setCategories] = useState<QuestionCategory[]>([]);
  const [questions, setQuestions] = useState<Question[] | null>(null);
  const [filter, setFilter] = useState({ category: "", qtype: "", tag: "", archived: false });
  const [panel, setPanel] = useState<Panel>({ kind: "none" });
  const [newType, setNewType] = useState<QType>("multichoice");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    const params = new URLSearchParams({ bank: String(bank.id) });
    if (filter.category) params.set("category", filter.category);
    if (filter.qtype) params.set("qtype", filter.qtype);
    if (filter.tag.trim()) params.set("tag", filter.tag.trim());
    if (filter.archived) params.set("archived", "1");
    return Promise.all([getAll<QuestionCategory>(`/question-categories/?bank=${bank.id}`), getAll<Question>(`/questions/?${params}`)])
      .then(([cats, qs]) => {
        setCategories(cats);
        setQuestions(qs);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load the questions.")));
  }, [bank.id, filter]);
  useEffect(() => {
    void load();
  }, [load]);

  async function act(work: () => Promise<unknown>, done: string) {
    try {
      await work();
      setMessage(done);
      setError(null);
      void load();
    } catch (err) {
      setMessage(null);
      setError(errorMessage(err, "That could not be done."));
    }
  }

  const tree = categoryTree(categories);
  const catName = (id: number | null) => categories.find((c) => c.id === id)?.name ?? "No category";
  const manage = bank.can_manage;

  return (
    <section aria-labelledby="bank-head">
      <h3 id="bank-head">
        {bank.name} <span className="muted small">{bank.owner_label}</span>
      </h3>
      {!manage && <p className="notice">Your department shares this bank: you can use its questions in quizzes, but only its owners change it.</p>}
      {manage && (
        <div className="actions bank-actions">
          <label className="inline">
            <span className="sr-only">Type of the new question</span>
            <select value={newType} onChange={(e) => setNewType(e.target.value as QType)} aria-label="Type of the new question">
              {(Object.keys(QTYPE_LABEL) as QType[]).map((t) => (
                <option key={t} value={t}>
                  {QTYPE_LABEL[t]}
                </option>
              ))}
            </select>
          </label>
          <button onClick={() => setPanel({ kind: "edit", question: null, qtype: newType })}>New question</button>
          <button className="secondary" onClick={() => setPanel({ kind: "categories" })}>
            Categories
          </button>
          <button className="secondary" onClick={() => setPanel({ kind: "import" })}>
            Import
          </button>
          <button className="secondary" onClick={() => setPanel({ kind: "export" })}>
            Export
          </button>
        </div>
      )}
      {!manage && (
        <div className="actions bank-actions">
          <button className="secondary" onClick={() => setPanel({ kind: "export" })}>
            Export
          </button>
        </div>
      )}
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
      {panel.kind === "edit" && (
        <QuestionEditor
          key={panel.question?.id ?? `new-${panel.qtype}`}
          bankId={bank.id}
          categories={tree.map((t) => t.category)}
          question={panel.question}
          qtype={panel.qtype}
          onSaved={(q) => {
            setPanel({ kind: "none" });
            setMessage(q.new_version ? `Saved “${q.name}” as version ${q.versions_count}: attempts already made keep the earlier version.` : `Saved “${q.name}”.`);
            void load();
          }}
          onCancel={() => setPanel({ kind: "none" })}
        />
      )}
      {panel.kind === "categories" && <Categories bank={bank} categories={categories} onChanged={load} onClose={() => setPanel({ kind: "none" })} />}
      {panel.kind === "import" && <Import bank={bank} categories={categories} onImported={load} onClose={() => setPanel({ kind: "none" })} />}
      {panel.kind === "export" && <Export bank={bank} categories={categories} onClose={() => setPanel({ kind: "none" })} />}

      <fieldset className="grid2 bank-filters">
        <legend>Show</legend>
        <label>
          Category
          <select value={filter.category} onChange={(e) => setFilter((prev) => ({ ...prev, category: e.target.value }))}>
            <option value="">All</option>
            {tree.map(({ category, depth }) => (
              <option key={category.id} value={category.id}>
                {" ".repeat(depth)}
                {category.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Type
          <select value={filter.qtype} onChange={(e) => setFilter((prev) => ({ ...prev, qtype: e.target.value }))}>
            <option value="">All</option>
            {(Object.keys(QTYPE_LABEL) as QType[]).map((t) => (
              <option key={t} value={t}>
                {QTYPE_LABEL[t]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tag
          <input value={filter.tag} onChange={(e) => setFilter((prev) => ({ ...prev, tag: e.target.value }))} />
        </label>
        <label className="inline">
          <input type="checkbox" checked={filter.archived} onChange={(e) => setFilter((prev) => ({ ...prev, archived: e.target.checked }))} />
          Archived too
        </label>
      </fieldset>
      {questions === null ? (
        <p className="loading">Loading…</p>
      ) : questions.length === 0 ? (
        <p className="muted">No questions here yet.</p>
      ) : (
        <ul className="plain">
          {questions.map((q) => (
            <li key={q.id} className="module">
              <div className="panel-head">
                <div>
                  <strong>{q.name}</strong> {q.is_archived && <span className="pill">Archived</span>}
                  <p className="muted small">
                    {QTYPE_LABEL[q.qtype]} · {catName(q.category)} · version {q.latest.number}
                    {q.tags.length > 0 && ` · ${q.tags.join(", ")}`}
                  </p>
                  <p className="small question-preview">{plainText(q.latest.text_html).slice(0, 160)}</p>
                </div>
              </div>
              {manage && (
                <div className="actions">
                  <button className="secondary small-button" onClick={() => setPanel({ kind: "edit", question: q, qtype: q.qtype })} aria-label={`Change “${q.name}”`}>
                    Change
                  </button>
                  <button
                    className="secondary small-button"
                    onClick={() => void act(() => patch(`/questions/${q.id}/`, { is_archived: !q.is_archived }), q.is_archived ? `“${q.name}” is back in use.` : `“${q.name}” is archived.`)}
                    aria-label={`${q.is_archived ? "Restore" : "Archive"} “${q.name}”`}
                  >
                    {q.is_archived ? "Restore" : "Archive"}
                  </button>
                  <button
                    className="secondary danger-text small-button"
                    onClick={() => window.confirm(`Delete “${q.name}”?`) && void act(() => remove(`/questions/${q.id}/`), `“${q.name}” is deleted.`)}
                    aria-label={`Delete “${q.name}”`}
                  >
                    Delete
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Categories({ bank, categories, onChanged, onClose }: { bank: QuestionBank; categories: QuestionCategory[]; onChanged: () => Promise<void>; onClose: () => void }) {
  const [name, setName] = useState("");
  const [parent, setParent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const run = async (work: () => Promise<unknown>) => {
    try {
      await work();
      setError(null);
      await onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not change the categories."));
    }
  };
  async function add(e: FormEvent) {
    e.preventDefault();
    await run(() => post("/question-categories/", { bank: bank.id, name, parent: parent ? Number(parent) : null }));
    setName("");
  }
  const tree = categoryTree(categories);
  return (
    <section className="sub-form stack" aria-labelledby="cat-head">
      <h3 id="cat-head">Categories</h3>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {tree.length === 0 && <p className="muted">No categories yet.</p>}
      <ul className="plain">
        {tree.map(({ category, depth }) => (
          <li key={category.id} className="pick-row" style={{ paddingLeft: depth * 18 }}>
            <input
              aria-label={`Name of category ${category.name}`}
              defaultValue={category.name}
              onBlur={(e) => e.target.value.trim() && e.target.value !== category.name && void run(() => patch(`/question-categories/${category.id}/`, { name: e.target.value.trim() }))}
            />
            <button
              className="secondary danger-text small-button"
              onClick={() => window.confirm(`Delete the category “${category.name}” and those inside it?`) && void run(() => remove(`/question-categories/${category.id}/`))}
              aria-label={`Delete category ${category.name}`}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
      <form className="form-row" onSubmit={add}>
        <label className="grow">
          New category
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Inside
          <select value={parent} onChange={(e) => setParent(e.target.value)}>
            <option value="">The top level</option>
            {tree.map(({ category, depth }) => (
              <option key={category.id} value={category.id}>
                {" ".repeat(depth)}
                {category.name}
              </option>
            ))}
          </select>
        </label>
        <div className="actions">
          <button type="submit">Add category</button>
        </div>
      </form>
      <div className="actions">
        <button className="secondary" onClick={onClose}>
          Done
        </button>
      </div>
    </section>
  );
}

const FORMAT_LABEL: Record<string, string> = { moodle_xml: "Moodle XML", gift: "GIFT", qti: "QTI 2.1 (item file or content package)" };

function Import({ bank, categories, onImported, onClose }: { bank: QuestionBank; categories: QuestionCategory[]; onImported: () => Promise<void>; onClose: () => void }) {
  const [format, setFormat] = useState("moodle_xml");
  const [file, setFile] = useState<File | null>(null);
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("");
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      let body: FormData | Record<string, unknown>;
      if (file) {
        body = new FormData();
        body.set("bank", String(bank.id));
        body.set("format", format);
        body.set("file", file);
        if (category) body.set("category", category);
      } else body = { bank: bank.id, format, content, ...(category ? { category: Number(category) } : {}) };
      setReport(await post<ImportReport>("/questions/import/", body));
      await onImported();
    } catch (err) {
      setError(errorMessage(err, "Could not read the file."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="sub-form stack" aria-labelledby="import-head">
      <h3 id="import-head">Import questions</h3>
      <form className="stack" onSubmit={run}>
        <div className="grid2">
          <label>
            Format
            <select value={format} onChange={(e) => setFormat(e.target.value)}>
              {Object.entries(FORMAT_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Into the category
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">As the file says (or the top level)</option>
              {categoryTree(categories).map(({ category: c, depth }) => (
                <option key={c.id} value={c.id}>
                  {" ".repeat(depth)}
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="span2">
            File (at most 5 MB)
            <input type="file" accept=".xml,.txt,.gift,.zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          {!file && (
            <label className="span2">
              Or paste the text
              <textarea rows={6} value={content} onChange={(e) => setContent(e.target.value)} />
            </label>
          )}
        </div>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="submit" disabled={busy || (!file && !content.trim())}>
            {busy ? "Importing…" : "Import"}
          </button>
          <button type="button" className="secondary" onClick={onClose}>
            Done
          </button>
        </div>
      </form>
      {report && (
        <div role="status" className="import-report stack">
          <p>
            <strong>
              {report.imported.length} imported, {report.skipped.length} skipped.
            </strong>
          </p>
          {report.imported.length > 0 && (
            <details open={report.imported.length <= 10}>
              <summary>Imported</summary>
              <ul>
                {report.imported.map((q) => (
                  <li key={q.id}>
                    {q.name} <span className="muted small">({QTYPE_LABEL[q.qtype]}{q.category.length ? `, ${q.category.join(" / ")}` : ""})</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {report.skipped.length > 0 && (
            <div className="notice bad">
              <strong>Skipped, with the reason:</strong>
              <ul>
                {report.skipped.map((s, i) => (
                  <li key={i}>
                    {s.name || "A question with no name"}: {s.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {report.warnings.length > 0 && (
            <div className="notice">
              <strong>Warnings:</strong>
              <ul>
                {report.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Export({ bank, categories, onClose }: { bank: QuestionBank; categories: QuestionCategory[]; onClose: () => void }) {
  const [format, setFormat] = useState("moodle_xml");
  const [category, setCategory] = useState("");
  const [result, setResult] = useState<{ data: ExportResult; url: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => () => void (result && URL.revokeObjectURL(result.url)), [result]);

  async function run(e: FormEvent) {
    e.preventDefault();
    try {
      const params = new URLSearchParams({ bank: String(bank.id), file_format: format });
      if (category) params.set("category", category);
      const data = await get<ExportResult>(`/questions/export/?${params}`);
      const url = URL.createObjectURL(new Blob([data.content], { type: format === "moodle_xml" ? "application/xml" : "text/plain" }));
      setResult({ data, url });
      setError(null);
    } catch (err) {
      setError(errorMessage(err, "Could not export the questions."));
    }
  }

  return (
    <section className="sub-form stack" aria-labelledby="export-head">
      <h3 id="export-head">Export questions</h3>
      <form className="form-row" onSubmit={run}>
        <label>
          Format
          <select value={format} onChange={(e) => setFormat(e.target.value)}>
            <option value="moodle_xml">Moodle XML</option>
            <option value="gift">GIFT</option>
          </select>
        </label>
        <label className="grow">
          Category
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">The whole bank</option>
            {categoryTree(categories).map(({ category: c, depth }) => (
              <option key={c.id} value={c.id}>
                {" ".repeat(depth)}
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <div className="actions">
          <button type="submit">Prepare the file</button>
        </div>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {result && (
        <div role="status" className="stack">
          <p>
            {result.data.exported} {result.data.exported === 1 ? "question" : "questions"} ready.{" "}
            <a className="button" href={result.url} download={result.data.filename}>
              Save {result.data.filename}
            </a>
          </p>
          {result.data.skipped.length > 0 && (
            <div className="notice">
              <strong>Not in the file, as the format cannot hold them:</strong>
              <ul>
                {result.data.skipped.map((s, i) => (
                  <li key={i}>
                    {s.name}: {s.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      <div className="actions">
        <button className="secondary" onClick={onClose}>
          Done
        </button>
      </div>
    </section>
  );
}
