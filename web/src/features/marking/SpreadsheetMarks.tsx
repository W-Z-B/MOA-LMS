import { useState, type FormEvent } from "react";
import { errorMessage, post } from "../../api/client";
import type { UploadResult } from "../../api/types-marking";

const OUTCOME_WORDS: Record<string, string> = {
  new: "New",
  changed: "Changed",
  unchanged: "Unchanged",
  unknown_student: "Refused: unknown student",
  no_submission: "Refused: nothing handed in",
  not_a_number: "Refused: not a number",
  negative: "Refused: below zero",
  above_max: "Refused: above the maximum",
  locked_in_srms: "Refused: locked in the SRMS",
  repeated: "Refused: repeated",
};
const SAVED = ["new", "changed", "unchanged"];

/**
 * Marks from a spreadsheet (item 2.25), checked before they are saved: the file is checked first and every
 * line's outcome shown; only a file with no refused line can be applied, exactly as it was checked. The
 * marks are saved as drafts, to be released from the marking screen.
 */
export function SpreadsheetMarks({ assignmentId, anonymous, onApplied }: { assignmentId: number; anonymous: boolean; onApplied: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(apply: boolean) {
    if (!file) return;
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.set("file", file);
    if (apply && result) {
      body.set("apply", "true");
      body.set("token", result.token);
    }
    try {
      const answer = await post<UploadResult>(`/assignments/${assignmentId}/marks-upload/`, body);
      setResult(answer);
      if (answer.applied) onApplied();
    } catch (err) {
      setError(errorMessage(err, "Could not read the file."));
    } finally {
      setBusy(false);
    }
  }

  function check(e: FormEvent) {
    e.preventDefault();
    void send(false);
  }

  return (
    <section className="stack" aria-label="Marks from a spreadsheet">
      <p className="muted small">
        A CSV file whose first line names the columns: {anonymous ? "candidate (the pseudonym)" : "student number"}, mark and feedback. Save a
        spreadsheet as CSV to make one. The marks are saved as drafts.
      </p>
      <form className="form-row" onSubmit={check}>
        <label className="grow">
          Spreadsheet (CSV)
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setResult(null);
            }}
          />
        </label>
        <div className="actions">
          <button type="submit" className="secondary" disabled={!file || busy}>
            Check the file
          </button>
        </div>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {result && (
        <>
          <p role="status" className={result.applied ? "notice good" : result.refused ? "notice bad" : "notice"}>
            {result.applied
              ? `Saved ${result.to_save} mark${result.to_save === 1 ? "" : "s"} as drafts.`
              : result.refused
                ? `${result.refused} line${result.refused === 1 ? " is" : "s are"} refused. Correct the file and check it again.`
                : `Checked: ${result.to_save} mark${result.to_save === 1 ? "" : "s"} to save, nothing refused.`}
          </p>
          <div className="scroll-x" tabIndex={0} role="region" aria-label="Each line of the file">
            <table className="cards">
              <thead>
                <tr>
                  <th className="num">Line</th>
                  <th>Student</th>
                  <th className="num">Mark</th>
                  <th>Outcome</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row) => (
                  <tr key={row.line} className={SAVED.includes(row.outcome) ? undefined : "refused-row"}>
                    <td className="num" data-label="Line">
                      {row.line}
                    </td>
                    <td data-label="Student">{row.student_no}</td>
                    <td className="num" data-label="Mark">
                      {row.mark ?? ""}
                    </td>
                    <td data-label="Outcome">
                      <span className="stacked">
                        <strong>{OUTCOME_WORDS[row.outcome] ?? row.outcome}</strong>
                        <span className="muted small">{row.detail}</span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!result.applied && result.refused === 0 && result.to_save > 0 && (
            <div className="actions">
              <button type="button" disabled={busy} onClick={() => send(true)}>
                Apply {result.to_save} mark{result.to_save === 1 ? "" : "s"}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
