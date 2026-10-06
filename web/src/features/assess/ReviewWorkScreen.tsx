import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { PeerWork } from "../../api/types-assess";
import type { RubricScore } from "../../api/types-marking";
import { dmyTime } from "../../app/format";
import { useCrumb } from "../../app/frame";
import { plainMark } from "../assignments/words";
import { RubricMarker } from "../marking/RubricMarker";
import "../marking/marking.css";
import "./assess.css";

interface Props {
  siteId: number;
  reviewId: number;
}

/**
 * One piece of work to review (item 4.13): the work without its author's name, the assignment's rubric to
 * score it by, and a comment. It can be changed until the reviews are due.
 */
export default function ReviewWorkScreen({ siteId, reviewId }: Props) {
  const [work, setWork] = useState<PeerWork | null>(null);
  const [scores, setScores] = useState<RubricScore[]>([]);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  useCrumb(work ? `Review: ${work.label}` : null);

  useEffect(() => {
    get<PeerWork>(`/peer-reviews/${reviewId}/`)
      .then((w) => {
        setWork(w);
        setScores(w.scores);
        setComment(w.comment);
      })
      .catch((err) => setError(errorMessage(err, "Could not open the work.")));
  }, [reviewId]);

  async function send(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const saved = await post<PeerWork>(`/peer-reviews/${reviewId}/`, { scores, comment });
      setWork(saved);
      setSent(saved.mark !== null ? `Review sent: ${plainMark(saved.mark)} out of ${plainMark(saved.max_mark)}.` : "Review sent.");
    } catch (err) {
      setError(errorMessage(err, "Could not send the review."));
    } finally {
      setSaving(false);
    }
  }

  if (!work)
    return error ? (
      <p role="alert" className="error">
        {error}
      </p>
    ) : (
      <p className="loading">Opening the work…</p>
    );
  const scored = work.rubric.criteria.every((c) => scores.some((s) => s.criterion === c.id && (s.level !== null || s.points !== null)));
  return (
    <div className="stack">
      <div className="page-head">
        <div className="stacked">
          <h1>
            {work.assignment}: {work.label}
          </h1>
          <p className="muted">
            {work.is_self ? "Assess your own work against the rubric." : "Whose work this is stays hidden, and they will not see your name."} Due{" "}
            {dmyTime(work.reviews_due_at)}.
          </p>
        </div>
        <a className="button secondary" href={`#/sites/${siteId}/assignments`}>
          Back to assignments
        </a>
      </div>
      <section className="module" aria-label="The work">
        <h2>The work</h2>
        {work.text ? <div className="answer">{work.text}</div> : null}
        {work.files.map((f) => (
          <a key={f.id} className="file-link" href={f.download_url}>
            Download {f.filename}
          </a>
        ))}
        {!work.text && work.files.length === 0 && <p className="muted">Nothing was handed in.</p>}
      </section>
      <form className="module stack" onSubmit={send} aria-label="Your review">
        <h2>Your review</h2>
        <RubricMarker rubric={work.rubric} scores={scores} onChange={setScores} disabled={!work.open} />
        <label>
          Comment for the student
          <textarea value={comment} rows={5} disabled={!work.open} onChange={(e) => setComment(e.target.value)} />
        </label>
        <p className="muted small">Be specific and kind: say what works, and one thing that would make it better.</p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {sent && (
          <p role="status" className="notice good">
            {sent}
          </p>
        )}
        {work.open ? (
          <div className="actions">
            <button type="submit" disabled={saving || !scored}>
              {work.submitted_at ? "Send the changed review" : "Send review"}
            </button>
          </div>
        ) : (
          <p className="notice">Reviews were due {dmyTime(work.reviews_due_at)}; this one can no longer change.</p>
        )}
      </form>
    </div>
  );
}
