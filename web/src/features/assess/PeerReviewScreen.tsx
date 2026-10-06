import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, errorMessage, get, post, remove } from "../../api/client";
import type { PeerReviewRow, PeerSetup, PeerStaffView, PeerStudentView, PeerWorkRow } from "../../api/types-assess";
import type { AssignmentDetail } from "../../api/types-marking";
import { dmyTime } from "../../app/format";
import { useCrumb } from "../../app/frame";
import { fromLocalInput, plainMark, toLocalInput } from "../assignments/words";
import "./assess.css";

interface Props {
  siteId: number;
  assignmentId: number;
}

const isStaff = (view: PeerStaffView | PeerStudentView): view is PeerStaffView => "work" in view;

/**
 * Peer review of an assignment (item 4.13). Teaching staff set it up, give the work out, read and moderate the
 * reviews, release them and fold peer marks into the marks. A student sees the work given to them to review,
 * without names, and once released the reviews of their own work, without the reviewers' names.
 */
export default function PeerReviewScreen({ siteId, assignmentId }: Props) {
  const [assignment, setAssignment] = useState<AssignmentDetail | null>(null);
  const [view, setView] = useState<PeerStaffView | PeerStudentView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  useCrumb(assignment ? `Peer review: ${assignment.title}` : null);

  const load = useCallback(() => {
    Promise.all([get<AssignmentDetail>(`/assignments/${assignmentId}/`), get<PeerStaffView | PeerStudentView>(`/assignments/${assignmentId}/peer-review/`)])
      .then(([a, v]) => {
        setAssignment(a);
        setView(v);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not open the peer review.")));
  }, [assignmentId]);
  useEffect(load, [load]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!assignment || !view) return <p className="loading">Opening the peer review…</p>;
  return (
    <div className="stack">
      <div className="page-head">
        <div className="stacked">
          <h1>Peer review: {assignment.title}</h1>
          {view.setup && <p className="muted">Reviews due {dmyTime(view.setup.reviews_due_at)}</p>}
        </div>
        <a className="button secondary" href={`#/sites/${siteId}/assignments`}>
          Back to assignments
        </a>
      </div>
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}
      {isStaff(view) ? (
        <StaffPeerReview assignment={assignment} view={view} onChanged={(words) => {
            setNotice(words);
            load();
          }} />
      ) : (
        <StudentPeerReview siteId={siteId} view={view} />
      )}
    </div>
  );
}

function StudentPeerReview({ siteId, view }: { siteId: number; view: PeerStudentView }) {
  if (!view.setup) return <p className="muted">This assignment has no peer review.</p>;
  return (
    <>
      <section className="module" aria-labelledby="to-review">
        <h2 id="to-review">Work for you to review</h2>
        {!view.setup.allocated_at && <p className="muted">The work is given out after the due date. You will be told when.</p>}
        {view.setup.allocated_at && view.to_do.length === 0 && <p className="muted">You were not given any work to review.</p>}
        <ul className="plain">
          {view.to_do.map((t) => (
            <li key={t.id} className="item-row">
              <a href={`#/sites/${siteId}/peer-reviews/${t.id}`}>{t.label}</a>{" "}
              <span className={t.submitted_at ? "chip chip-approved" : "chip chip-waiting"}>{t.submitted_at ? "Review sent" : "To review"}</span>
            </li>
          ))}
        </ul>
        <p className="muted small">Names are hidden both ways: you do not see whose work it is, and they will not see who reviewed it.</p>
      </section>
      <section className="module" aria-labelledby="received">
        <h2 id="received">Reviews of your work</h2>
        {view.received === null ? (
          <p className="muted">Your lecturer shows you the reviews once they have read them.</p>
        ) : view.received.length === 0 ? (
          <p className="muted">No reviews of your work.</p>
        ) : (
          view.received.map((r, i) => (
            <div key={i} className="key-card">
              <h3 className="small-heading">
                {r.label}
                {r.mark !== null ? `: ${plainMark(r.mark)}` : ""}
              </h3>
              {r.comment && <p style={{ whiteSpace: "pre-wrap" }}>{r.comment}</p>}
              {r.scores.filter((s) => s.comment).length > 0 && (
                <ul className="small">
                  {r.scores
                    .filter((s) => s.comment)
                    .map((s) => (
                      <li key={s.criterion}>{s.comment}</li>
                    ))}
                </ul>
              )}
            </div>
          ))
        )}
      </section>
    </>
  );
}

function StaffPeerReview({ assignment, view, onChanged }: { assignment: AssignmentDetail; view: PeerStaffView; onChanged: (words: string) => void }) {
  const [error, setError] = useState<string | null>(null);
  const setup = view.setup;
  const base = `/assignments/${assignment.id}/peer-review/`;

  async function act(path: string, words: (r: Record<string, number>) => string, confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return;
    setError(null);
    try {
      const r = await post<Record<string, number>>(`${base}${path}`);
      onChanged(words(r));
    } catch (err) {
      setError(errorMessage(err, "That could not be done."));
    }
  }

  async function takeOff() {
    if (!window.confirm("Take peer review off this assignment?")) return;
    try {
      await remove(base);
      onChanged("Peer review is off.");
    } catch (err) {
      setError(errorMessage(err, "Could not take it off."));
    }
  }

  if (!view.rubric)
    return (
      <p className="notice">
        Peer review needs a rubric on the assignment, so students assess against the same criteria you do. Add one under Change on the assignment first.
      </p>
    );
  return (
    <>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <SetupForm assignment={assignment} setup={setup} onSaved={() => onChanged(setup ? "Peer review changed." : "Peer review is set up.")} />
      {setup && (
        <div className="actions">
          {!setup.allocated_at && (
            <button type="button" onClick={() => act("allocate/", (r) => `Given out: ${r.reviews} reviews.`)}>
              Give the work out now
            </button>
          )}
          {setup.allocated_at && !setup.released_at && (
            <button
              type="button"
              onClick={() => act("release/", (r) => `Reviews shown to ${r.students} students.`, "Show each student the reviews of their work that count?")}
            >
              Show students their reviews
            </button>
          )}
          {setup.allocated_at && Number(setup.peer_weight) > 0 && (
            <button
              type="button"
              className="secondary"
              onClick={() =>
                act(
                  "apply/",
                  (r) => `Peer marks folded into ${r.applied} draft mark${r.applied === 1 ? "" : "s"}; ${r.skipped} left as they were.`,
                  `Make each draft mark ${100 - Number(setup.peer_weight)}% your mark and ${Number(setup.peer_weight)}% the peer mark?`,
                )
              }
            >
              Fold peer marks into the marks
            </button>
          )}
          {!setup.allocated_at && (
            <button type="button" className="secondary" onClick={takeOff}>
              Take peer review off
            </button>
          )}
        </div>
      )}
      {setup && !setup.allocated_at && <p className="muted">The work is given out by itself within the hour after the due date, or now with the button.</p>}
      {view.work.length > 0 && (
        <section aria-labelledby="peer-work">
          <h2 id="peer-work">The work and its reviews</h2>
          {view.work.map((w) => (
            <WorkReviews key={w.submission} work={w} max={assignment.max_mark} onChanged={onChanged} />
          ))}
        </section>
      )}
    </>
  );
}

function SetupForm({ assignment, setup, onSaved }: { assignment: AssignmentDetail; setup: PeerSetup | null; onSaved: () => void }) {
  const firstDue = new Date(new Date(assignment.due_at).getTime() + 7 * 86_400_000).toISOString();
  const [each, setEach] = useState(String(setup?.reviews_each ?? 3));
  const [due, setDue] = useState(toLocalInput(setup?.reviews_due_at ?? firstDue));
  const [self, setSelf] = useState(setup?.self_assessment ?? false);
  const [weight, setWeight] = useState(setup ? plainMark(setup.peer_weight) : "0");
  const [error, setError] = useState<string | null>(null);
  const fixed = Boolean(setup?.allocated_at);

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api(`/assignments/${assignment.id}/peer-review/`, {
        method: "PUT",
        body: JSON.stringify({
          ...(fixed ? {} : { reviews_each: Number(each), self_assessment: self }),
          reviews_due_at: fromLocalInput(due),
          peer_weight: weight || "0",
        }),
      });
      onSaved();
    } catch (err) {
      setError(errorMessage(err, "Could not save peer review."));
    }
  }

  return (
    <form className="module stack" onSubmit={save} aria-label="Peer review settings">
      <h2>{setup ? "Settings" : "Set up peer review"}</h2>
      <div className="form-row">
        <label>
          Pieces of work each student reviews
          <input type="number" min={1} max={10} value={each} disabled={fixed} onChange={(e) => setEach(e.target.value)} required />
        </label>
        <label>
          Reviews due
          <input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} required />
        </label>
        <label>
          Share of the mark from peers (%)
          <input type="number" min={0} max={100} step="any" value={weight} onChange={(e) => setWeight(e.target.value)} />
        </label>
      </div>
      <label className="inline">
        <input type="checkbox" checked={self} disabled={fixed} onChange={(e) => setSelf(e.target.checked)} /> Each student also assesses their own work
      </label>
      <p className="muted small">0% keeps peer review as feedback only. Reviews use the assignment's rubric; names are hidden both ways.</p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="submit">{setup ? "Save changes" : "Set up peer review"}</button>
      </div>
    </form>
  );
}

function WorkReviews({ work, max, onChanged }: { work: PeerWorkRow; max: string; onChanged: (words: string) => void }) {
  const [override, setOverride] = useState(work.override ? plainMark(work.override) : "");
  const [error, setError] = useState<string | null>(null);

  async function moderate(review: PeerReviewRow) {
    const leaving = review.moderation === "counts";
    const note = leaving ? window.prompt("Why is this review left out? (kept for the record)") : "";
    if (note === null) return;
    try {
      await post(`/peer-reviews/${review.id}/moderate/`, { moderation: leaving ? "left_out" : "counts", note: note ?? "" });
      onChanged(leaving ? "The review is left out." : "The review counts again.");
    } catch (err) {
      setError(errorMessage(err, "Could not change it."));
    }
  }

  async function saveOverride(e: FormEvent) {
    e.preventDefault();
    try {
      await post(`/submissions/${work.submission}/peer-mark/`, { override: override === "" ? null : override, note: "" });
      onChanged(override === "" ? "The peer mark comes from the reviews again." : `Peer mark set to ${override}.`);
    } catch (err) {
      setError(errorMessage(err, "Could not set the peer mark."));
    }
  }

  return (
    <details className="similarity">
      <summary>
        {work.label}: peer mark {work.peer_mark !== null ? plainMark(work.peer_mark) : "none yet"}
        {work.self_mark !== null ? `, own ${plainMark(work.self_mark)}` : ""}
      </summary>
      <div className="stack">
        <p className="muted small">
          Mark now: {work.mark !== null ? `${plainMark(work.mark)} out of ${plainMark(max)}` : "not marked"}
          {work.staff_mark !== null ? ` (your mark ${plainMark(work.staff_mark)} before peer marks were folded in)` : ""}
        </p>
        {work.reviews.map((r) => (
          <div key={r.id} className="key-card">
            <p className="small">
              <strong>{r.is_self ? `Own assessment (${r.reviewer})` : `Reviewer ${r.reviewer}`}</strong>:{" "}
              {r.submitted_at ? (r.mark !== null ? plainMark(r.mark) : "sent") : "not sent yet"}
              {r.moderation === "left_out" && <span className="chip chip-rejected"> Left out</span>}
            </p>
            {r.comment && <p style={{ whiteSpace: "pre-wrap" }}>{r.comment}</p>}
            {r.moderation_note && <p className="muted small">Note: {r.moderation_note}</p>}
            {r.submitted_at && !r.is_self && (
              <button type="button" className="secondary small-button" onClick={() => moderate(r)}>
                {r.moderation === "counts" ? "Leave out" : "Let it count"}
              </button>
            )}
          </div>
        ))}
        <form className="form-row" onSubmit={saveOverride} aria-label={`Peer mark for ${work.label}`}>
          <label>
            Set the peer mark yourself (empty to use the reviews)
            <input type="number" min={0} max={Number(max)} step="any" value={override} onChange={(e) => setOverride(e.target.value)} />
          </label>
          <div className="actions">
            <button type="submit" className="secondary">
              Save peer mark
            </button>
          </div>
        </form>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
      </div>
    </details>
  );
}
