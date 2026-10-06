import { useState, type FormEvent } from "react";
import { errorMessage, post } from "../../api/client";
import type { AssignmentDetail, ModerationState, WorkSubmission } from "../../api/types-marking";
import { dmyTime } from "../../app/format";
import { plainMark } from "../assignments/words";

interface Props {
  assignment: AssignmentDetail;
  submission: WorkSubmission;
  moderation: ModerationState | null;
  /** After a second mark (no submission) or the agreement (the submission with its agreed mark). */
  onChanged: (agreed?: WorkSubmission) => void;
}

/**
 * Second marking and agreement (item 3.17): another marker's mark is kept beside the first, the two agree a
 * mark, and the agreed mark becomes the mark; both originals stay. A release waits for the agreement.
 */
export function Moderation({ assignment, submission, moderation, onChanged }: Props) {
  const [mark, setMark] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const stage = !submission.mark
    ? "unmarked"
    : !moderation && assignment.moderation === "sample"
      ? "not_sampled"
      : !moderation?.second_mark
        ? "second"
        : !moderation.agreed_mark
          ? "agree"
          : "agreed";

  async function send(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (stage === "second") {
        await post(`/submissions/${submission.id}/second-mark/`, { mark, note });
        onChanged();
      } else {
        onChanged(await post<WorkSubmission>(`/submissions/${submission.id}/agree/`, { mark, note }));
      }
      setMark("");
      setNote("");
    } catch (err) {
      setError(errorMessage(err, "Could not save it."));
    }
  }

  return (
    <section className="stack moderation" aria-label="Second marking">
      <h3 className="small-heading">Second marking</h3>
      {stage === "unmarked" && <p className="muted small">The first marking comes first.</p>}
      {stage === "not_sampled" && <p className="muted small">Not in the sample for a second marker.</p>}
      {moderation && (
        <dl className="facts small">
          <div>
            <dt>First mark</dt>
            <dd>{plainMark(moderation.first_mark) || "—"}</dd>
          </div>
          <div>
            <dt>Second mark</dt>
            <dd>
              {plainMark(moderation.second_mark) || "Waiting"}
              {moderation.second_note && ` (${moderation.second_note})`}
            </dd>
          </div>
          {moderation.agreed_mark && (
            <div>
              <dt>Agreed</dt>
              <dd>
                {plainMark(moderation.agreed_mark)} on {dmyTime(moderation.agreed_at!)}
                {moderation.agreed_note && ` (${moderation.agreed_note})`}
              </dd>
            </div>
          )}
        </dl>
      )}
      {(stage === "second" || stage === "agree") && (
        <form className="stack" onSubmit={send}>
          <label>
            {stage === "second" ? "Your second mark (another marker than the first)" : "The agreed mark"}
            <input type="number" min={0} max={Number(assignment.max_mark)} step="any" value={mark} onChange={(e) => setMark(e.target.value)} required />
          </label>
          <label>
            Note (optional)
            <input value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <div className="actions">
            <button type="submit" className="secondary">
              {stage === "second" ? "Save the second mark" : "Record the agreed mark"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
