import { useState } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { SimilarityReport } from "../../api/types-assess";
import { dmyTime } from "../../app/format";
import "./assess.css";

const STATUS: Record<SimilarityReport["status"], string> = {
  not_checked: "Not checked yet: each hand-in is checked in the background shortly after it arrives.",
  waiting: "Being checked now.",
  done: "",
  no_text: "No text could be read from this work, so it was not compared.",
  failed: "The check could not be finished. Check again.",
};

/**
 * The similarity report beside the mark (item 3.20; ADR 0006 and 0031), for teaching staff only: the overall
 * overlap with other GSA work and each matching passage side by side. Fetched only when opened. The other
 * work is named only to staff who teach its course too. It always says that overlap is evidence for a
 * person to judge, never a verdict.
 */
export function SimilarityPanel({ submissionId }: { submissionId: number }) {
  const [report, setReport] = useState<SimilarityReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function load() {
    if (report || busy) return;
    setBusy(true);
    get<SimilarityReport>(`/submissions/${submissionId}/similarity/`)
      .then((r) => {
        setReport(r);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load the similarity report.")))
      .finally(() => setBusy(false));
  }

  async function checkAgain() {
    setBusy(true);
    try {
      setReport(await post<SimilarityReport>(`/submissions/${submissionId}/similarity/`));
      setError(null);
    } catch (err) {
      setError(errorMessage(err, "Could not check it again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="similarity" onToggle={(e) => (e.currentTarget.open ? load() : undefined)}>
      <summary>Similarity with other GSA work</summary>
      <div className="stack">
        {busy && !report && <p className="loading">Opening the report…</p>}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {report && (
          <>
            <p className="statement">{report.statement}</p>
            {report.status === "done" ? (
              <div>
                <p className="overlap-figure">{Number(report.overall_percent ?? 0)}% found in other GSA work</p>
                <p className="muted small">
                  {report.word_count} words compared, from hand-in {report.attempt_number}
                  {report.checked_at ? `, checked ${dmyTime(report.checked_at)}` : ""}.
                </p>
              </div>
            ) : (
              <p className="muted">{STATUS[report.status]}</p>
            )}
            {report.notes.length > 0 && (
              <ul className="small">
                {report.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            )}
            {report.status === "done" && report.matches.length === 0 && <p>No passage matches any other GSA work.</p>}
            {report.matches.map((m) => (
              <section key={m.id} aria-labelledby={`match-${m.id}`}>
                <h3 id={`match-${m.id}`} className="small-heading">
                  {Number(m.percent)}% shared with {m.other.label}
                </h3>
                {!m.other.known && (
                  <p className="muted small">Named only to staff who teach that course too. Ask its lecturer if you need to know more.</p>
                )}
                <ol className="passages" aria-label={`Matching passages with ${m.other.label}`}>
                  {m.passages.map((p, i) => (
                    <li key={i} className="passage">
                      <div>
                        <p className="side">This work ({p.words} words)</p>
                        <blockquote>{p.mine}</blockquote>
                      </div>
                      <div>
                        <p className="side">The other work</p>
                        <blockquote>{p.theirs}</blockquote>
                      </div>
                    </li>
                  ))}
                </ol>
              </section>
            ))}
            <div className="actions">
              <button type="button" className="secondary" disabled={busy} onClick={checkAgain}>
                Check again now
              </button>
              <a className="button secondary" href="#/help/assessment-and-ai">
                How to read this report
              </a>
            </div>
          </>
        )}
      </div>
    </details>
  );
}
