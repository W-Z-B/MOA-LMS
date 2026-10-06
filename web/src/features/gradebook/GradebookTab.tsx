import { useCallback, useEffect, useState } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { Site } from "../../api/types";
import type { CourseworkSent, GradebookData, GradebookRow, SrmsState } from "../../api/types-marking";
import { dmy, dmyTime } from "../../app/format";
import { plainMark, STATE_WORDS } from "../assignments/words";
import { CategoriesEditor } from "./CategoriesEditor";
import { WorkingView } from "./WorkingView";
import "../marking/marking.css";

interface Props {
  site: Site;
  teaching: boolean;
}

const OUTCOME = { accepted: "Accepted", locked: "Already locked", unknown: "Not known to the SRMS" } as const;

function srmsWords(state: SrmsState | null): string {
  if (!state) return "";
  const locked = state.locked_since ? ` · locked since ${dmy(state.locked_since)}` : "";
  return `${OUTCOME[state.outcome]} ${dmy(state.sent_at)}${locked}`;
}

function assignmentCell(row: GradebookRow, id: number): string {
  const cell = row.marks[String(id)];
  if (!cell) return "";
  if (cell.anonymous && cell.submitted) return "Hidden (anonymous)";
  if (cell.mark != null) return plainMark(cell.mark);
  return cell.submitted ? "Handed in" : "";
}

/**
 * The gradebook (items 2.28 to 2.31, 3.18): every assignment, quiz, practical task and graded forum that
 * counts, the categories and the coursework total; the working of each student's total; the export and
 * print; and, for the lecturer of an SRMS course, sending the coursework to the SRMS, which locks the marks
 * it takes. A student sees their own row and the working of their own total.
 */
export function GradebookTab({ site, teaching }: Props) {
  const [book, setBook] = useState<GradebookData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showing, setShowing] = useState<GradebookRow | null>(null);
  const [categories, setCategories] = useState(false);
  const canSend = site.source === "srms" && (site.my_role === "lecturer" || site.my_role === "admin");

  const load = useCallback(() => {
    get<GradebookData>(`/sites/${site.id}/gradebook/`)
      .then((b) => {
        setBook(b);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load the gradebook.")));
  }, [site.id]);

  useEffect(load, [load]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!book) return <p className="loading">Loading…</p>;

  const counted = book.quizzes.filter((q) => q.counts);
  return (
    <div className="gradebook">
      {teaching && (
        <div className="actions tab-actions no-print">
          <a className="button" href={`/api/v1/sites/${site.id}/gradebook/export/`} download>
            Export to a spreadsheet
          </a>
          <button type="button" className="secondary" onClick={() => window.print()}>
            Print
          </button>
          <button type="button" className="secondary" aria-expanded={categories} onClick={() => setCategories(!categories)}>
            Categories and weights
          </button>
        </div>
      )}
      {teaching && categories && <CategoriesEditor siteId={site.id} onChanged={load} />}
      {teaching && canSend && <SendToSrms siteId={site.id} onSent={load} />}

      {book.rows.length === 0 ? (
        <p className="muted">No students in this course.</p>
      ) : (
        // Focusable and named, so a keyboard user can scroll a gradebook wider than the screen.
        <div className="scroll-x" tabIndex={0} role="region" aria-label="Gradebook">
          <table>
            <thead>
              <tr>
                <th>Student</th>
                {book.assignments.map((a) => (
                  <th key={`a${a.id}`} className="num">
                    {a.title} / {plainMark(a.max_mark)}
                  </th>
                ))}
                {counted.map((q) => (
                  <th key={`q${q.id}`} className="num">
                    {q.title} (quiz %)
                  </th>
                ))}
                {book.practicals.map((t) => (
                  <th key={`p${t.id}`} className="num">
                    {t.title} (practical %)
                  </th>
                ))}
                {book.forums.map((f) => (
                  <th key={`f${f.id}`} className="num">
                    {f.title} (forum %)
                  </th>
                ))}
                {(book.tools ?? []).map((t) => (
                  <th key={`t${t.id}`} className="num">
                    {t.title} ({t.tool} %)
                  </th>
                ))}
                {book.categories.map((c) => (
                  <th key={`c${c.id}`} className="num">
                    {c.name} (%)
                  </th>
                ))}
                <th className="num">Coursework %</th>
                {teaching && <th>SRMS</th>}
              </tr>
            </thead>
            <tbody>
              {book.rows.map((row) => (
                <tr key={row.person_id}>
                  <td className="student">
                    {teaching ? (
                      <button type="button" className="link accent" onClick={() => setShowing(showing?.person_id === row.person_id ? null : row)} aria-label={`How ${row.name}'s total is worked out`}>
                        {row.student_no} {row.name}
                      </button>
                    ) : (
                      `${row.student_no} ${row.name}`
                    )}
                  </td>
                  {book.assignments.map((a) => (
                    <td key={`a${a.id}`} className="num">
                      {assignmentCell(row, a.id)}
                    </td>
                  ))}
                  {counted.map((q) => (
                    <td key={`q${q.id}`} className="num">
                      {row.quizzes[String(q.id)]?.percent ?? ""}
                    </td>
                  ))}
                  {book.practicals.map((t) => (
                    <td key={`p${t.id}`} className="num">
                      <ItemCell cell={row.practicals[String(t.id)]} />
                    </td>
                  ))}
                  {book.forums.map((f) => (
                    <td key={`f${f.id}`} className="num">
                      <ItemCell cell={row.forums[String(f.id)]} />
                    </td>
                  ))}
                  {(book.tools ?? []).map((t) => (
                    <td key={`t${t.id}`} className="num">
                      <ItemCell cell={row.tools?.[String(t.id)]} />
                    </td>
                  ))}
                  {book.categories.map((c) => (
                    <td key={`c${c.id}`} className="num">
                      {row.categories[String(c.id)] ?? ""}
                    </td>
                  ))}
                  <td className="num">
                    <strong>{row.coursework_percent ?? ""}</strong>
                  </td>
                  {teaching && <td className="small">{srmsWords(row.srms)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">
        Coursework totals are returned to the SRMS, where the examination mark is added and the result is approved and published.
        {teaching && " Choose a student to see how their total is worked out."}
      </p>
      {teaching && showing && (
        <div className="module">
          <div className="spread">
            <h3>
              {showing.student_no} {showing.name}
            </h3>
            <button type="button" className="secondary" onClick={() => setShowing(null)}>
              Close
            </button>
          </div>
          <WorkingView key={showing.person_id} siteId={site.id} personId={showing.person_id} />
        </div>
      )}
      {!teaching && book.rows.length > 0 && (
        <div className="module">
          <h3>How your coursework total is worked out</h3>
          <WorkingView siteId={site.id} />
        </div>
      )}
    </div>
  );
}

function ItemCell({ cell }: { cell?: { state: keyof typeof STATE_WORDS; percent: string | null } }) {
  if (!cell) return null;
  if (cell.state === "graded" || cell.state === "dropped") return <>{cell.percent}</>;
  return <span className="state">{STATE_WORDS[cell.state]}</span>;
}

/**
 * Send the coursework to the SRMS (items 2.31, 3.18) and show, for each student, what the SRMS did with it:
 * accepted (and now locked here), already locked there, or a student it does not know.
 */
function SendToSrms({ siteId, onSent }: { siteId: number; onSent: () => void }) {
  const [sent, setSent] = useState<CourseworkSent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send() {
    if (!window.confirm("Send every student's coursework total to the SRMS now? The marks it accepts are then locked here.")) return;
    setBusy(true);
    setError(null);
    try {
      setSent(await post<CourseworkSent>(`/sites/${siteId}/coursework/send/`));
      onSent();
    } catch (err) {
      setError(errorMessage(err, "Could not send the coursework."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="stack sub-form no-print" aria-label="Send coursework to the SRMS">
      <div className="actions">
        <button type="button" onClick={send} disabled={busy}>
          {busy ? "Sending…" : "Send coursework to the SRMS"}
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {sent && (
        <div role="status" className="stack">
          <p className="notice good">
            Sent {dmyTime(sent.sent_at)}: {sent.accepted.length} accepted, {sent.locked.length} already locked in the SRMS
            {sent.unknown.length ? `, ${sent.unknown.length} not known to it` : ""}.
          </p>
          <ul className="plain" aria-label="Each student">
            {sent.students.map((s) => (
              <li key={s.student_no} className="spread">
                <span>
                  {s.student_no}: {s.percent}%
                </span>
                <span className={s.outcome === "accepted" ? "chip chip-approved" : s.outcome === "locked" ? "chip chip-waiting" : "chip chip-rejected"}>
                  {OUTCOME[s.outcome]}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
