import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post, remove } from "../../api/client";
import type { KeyedResult, Paper, PaperGrid, PaperGridRow } from "../../api/types-assess";
import { dmy } from "../../app/format";
import "./assess.css";

const PARTS = [
  ["questions", "Question paper"],
  ["answer-sheet", "Answer sheet"],
  ["key", "Marking key"],
] as const;

/**
 * A quiz on paper, for a room without devices (item 3.24): make a paper from the quiz (versions A and B),
 * print it, then key each student's answers in on a grid or from a CSV file. Each sheet keyed is an attempt
 * at the quiz, marked by the same rules as online and counted the same way.
 */
export function PaperQuizzes({ quizId }: { quizId: number }) {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState({ title: "", sat_on: new Date().toISOString().slice(0, 10), versions: "2" });

  const load = useCallback(() => {
    get<Paper[]>(`/quizzes/${quizId}/papers/`)
      .then(setPapers)
      .catch((err) => setError(errorMessage(err, "Could not load the papers.")));
  }, [quizId]);
  useEffect(load, [load]);

  async function make(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const made = await post<Paper>(`/quizzes/${quizId}/papers/`, { ...draft, versions: Number(draft.versions) });
      setDraft({ ...draft, title: "" });
      load();
      setOpen(made.id);
    } catch (err) {
      setError(errorMessage(err, "Could not make the paper."));
    }
  }

  async function drop(paper: Paper) {
    if (!window.confirm(`Delete the paper “${paper.title}”?`)) return;
    try {
      await remove(`/quiz-papers/${paper.id}/`);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not delete it."));
    }
  }

  return (
    <div className="stack">
      <p className="muted">
        For a room without devices. The questions are drawn once when the paper is made. Version B has the questions and options in another order, so
        neighbours have different papers. Questions that cannot be answered on paper (fill in the blanks, file uploads, labelling a picture) stop a paper
        being made.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <form className="module stack" onSubmit={make} aria-label="Make a paper">
        <h3 className="small-heading">Make a paper</h3>
        <div className="form-row">
          <label>
            Title
            <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} required maxLength={160} />
          </label>
          <label>
            Day it is sat
            <input type="date" value={draft.sat_on} onChange={(e) => setDraft({ ...draft, sat_on: e.target.value })} required />
          </label>
          <label>
            Versions
            <select value={draft.versions} onChange={(e) => setDraft({ ...draft, versions: e.target.value })}>
              <option value="2">A and B</option>
              <option value="1">A only</option>
            </select>
          </label>
        </div>
        <div className="actions">
          <button type="submit">Make the paper</button>
        </div>
      </form>
      {papers.length === 0 && <p className="muted">No papers yet.</p>}
      {papers.map((paper) => (
        <section key={paper.id} className="module" aria-labelledby={`paper-${paper.id}`}>
          <div className="panel-head">
            <div className="stacked">
              <h3 id={`paper-${paper.id}`}>{paper.title}</h3>
              <p className="muted small">
                Sat {dmy(paper.sat_on)} · {paper.questions} questions · {paper.keyed} answer sheet{paper.keyed === 1 ? "" : "s"} keyed
              </p>
            </div>
            <div className="actions">
              <button type="button" aria-expanded={open === paper.id} onClick={() => setOpen(open === paper.id ? null : paper.id)}>
                {open === paper.id ? "Close" : "Key answers"}
              </button>
              {paper.keyed === 0 && (
                <button type="button" className="secondary" onClick={() => drop(paper)}>
                  Delete
                </button>
              )}
            </div>
          </div>
          {paper.versions.map((label) => (
            <p key={label} className="actions" aria-label={`Print version ${label}`}>
              <strong>Version {label}:</strong>
              {PARTS.map(([part, words]) => (
                <a key={part} className="file-link" href={`/api/v1/quiz-papers/${paper.id}/pdf/?version=${label}&part=${part}`} download>
                  {words} ({label})
                </a>
              ))}
            </p>
          ))}
          {open === paper.id && <KeyGrid paperId={paper.id} onKeyed={load} />}
        </section>
      ))}
    </div>
  );
}

function KeyGrid({ paperId, onKeyed }: { paperId: number; onKeyed: () => void }) {
  const [grid, setGrid] = useState<PaperGrid | null>(null);
  const [rows, setRows] = useState<PaperGridRow[]>([]);
  const [changed, setChanged] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<KeyedResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);

  const load = useCallback(() => {
    get<PaperGrid>(`/quiz-papers/${paperId}/grid/`)
      .then((g) => {
        setGrid(g);
        setRows(g.rows.map((r) => ({ ...r, version: r.version || g.versions[0] })));
        setChanged(new Set());
      })
      .catch((err) => setError(errorMessage(err, "Could not open the grid.")));
  }, [paperId]);
  useEffect(load, [load]);

  if (!grid) return error ? <p role="alert" className="error">{error}</p> : <p className="loading">Opening the grid…</p>;
  const width = Math.max(...Object.values(grid.columns).map((c) => c.length));

  const put = (studentNo: string, change: Partial<PaperGridRow>) => {
    setRows(rows.map((r) => (r.student_no === studentNo ? { ...r, ...change } : r)));
    setChanged(new Set(changed).add(studentNo));
  };
  const cell = (row: PaperGridRow, index: number, value: string) => {
    const answers = Array.from({ length: width }, (_, i) => row.answers[i] ?? "");
    answers[index] = value;
    put(row.student_no, { answers });
  };

  async function save() {
    setError(null);
    try {
      const body = rows.filter((r) => changed.has(r.student_no)).map((r) => ({ student_no: r.student_no, version: r.version, answers: r.answers }));
      const r = await post<KeyedResult>(`/quiz-papers/${paperId}/grid/`, { rows: body });
      setResult(r);
      load();
      onKeyed();
    } catch (err) {
      setError(errorMessage(err, "Could not save the answers."));
    }
  }

  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      setResult(await post<KeyedResult>(`/quiz-papers/${paperId}/upload/`, form));
      load();
      onKeyed();
    } catch (err) {
      setError(errorMessage(err, "Could not read the file."));
    }
  }

  return (
    <div className="stack">
      <details className="similarity">
        <summary>How to key the answers</summary>
        <ul className="small">
          <li>Choose the version the student sat, then type what they wrote for each question.</li>
          <li>Lettered options: the letter, such as B; several letters where several apply, such as AC.</li>
          <li>True or false: T or F. Matching: one letter for each numbered line, in order. Ordering: every letter, first to last.</li>
          <li>Short answers and numbers: as written. Essays: the marks you gave, or ? to mark it later in the quiz's Marking.</li>
          <li>Leave a question empty when it was not answered. Keying a student again replaces what was keyed before.</li>
        </ul>
        {Object.entries(grid.columns).map(([label, columns]) => (
          <p key={label} className="small">
            Version {label}: {columns.map((c) => `${c.number}. ${c.hint}`).join("; ")}
          </p>
        ))}
      </details>
      <div className="key-grid" role="region" aria-label="Answers keyed in" tabIndex={0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Student</th>
              <th scope="col">Version</th>
              {Array.from({ length: width }, (_, i) => (
                <th key={i} scope="col">
                  Q{i + 1}
                </th>
              ))}
              <th scope="col">Score</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.student_no}>
                <th scope="row">
                  {row.student_no}
                  <br />
                  <span className="small muted">{row.name}</span>
                </th>
                <td>
                  <select aria-label={`Version for ${row.name}`} value={row.version} onChange={(e) => put(row.student_no, { version: e.target.value })}>
                    {grid.versions.map((v) => (
                      <option key={v}>{v}</option>
                    ))}
                  </select>
                </td>
                {Array.from({ length: width }, (_, i) => (
                  <td key={i}>
                    <input
                      aria-label={`Question ${i + 1}, ${row.name}`}
                      title={grid.columns[row.version]?.[i]?.hint}
                      value={row.answers[i] ?? ""}
                      size={4}
                      onChange={(e) => cell(row, i, e.target.value)}
                    />
                  </td>
                ))}
                <td>
                  {row.score !== null ? `${Number(row.score)} / ${Number(row.max_score)}` : "—"}
                  {row.needs_marking && <span className="chip chip-waiting">To mark</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="actions">
        <button type="button" onClick={save} disabled={changed.size === 0}>
          Save the answers keyed
        </button>
      </div>
      <form className="form-row" onSubmit={upload} aria-label="Answers from a CSV file">
        <label>
          Or send a CSV file: student_no, version, q1, q2 …
          <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <div className="actions">
          <button type="submit" className="secondary" disabled={!file}>
            Key from the file
          </button>
        </div>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {result && (
        <div role="status" className={result.errors.length ? "notice" : "notice good"}>
          <p>
            {result.saved} answer sheet{result.saved === 1 ? "" : "s"} saved and marked.
          </p>
          {result.errors.length > 0 && (
            <ul className="small">
              {result.errors.map((e, i) => (
                <li key={i}>
                  {e.student_no || "A row"}: {e.detail}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
