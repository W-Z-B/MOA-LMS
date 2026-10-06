/**
 * The field checklist (items 3.12 and 3.15): a lecturer or assessor on a phone, often without signal, picks a
 * student and marks every criterion with big toggles, adds a comment, photos and (only when asked for) the
 * place, and saves. The record goes through the offline queue with one Idempotency-Key for every try and
 * the phone's time; the photos wait on the phone until the record has gone (photoOutbox.ts).
 */

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, errorMessage, get } from "../../api/client";
import type { Criterion, Observation, PracticalTask, TaskStudent } from "../../api/types-practicals";
import { dmyTime } from "../../app/format";
import { isNetworkError, sendPracticalWrite, usePending } from "../../app/offlineQueue";
import { SendState } from "../../app/SendState";
import { keepCopy, readCopy, type FieldCopy } from "./fieldCopy";
import { LocationButton, PhotoPicker, PhotoState, type Place } from "./FieldWidgets";
import { localDateTime, observationsPath } from "./helpers";
import { attachPhotos } from "./photoOutbox";
import { practicalsPath } from "./routes";

interface Props {
  siteId: number;
  taskId: number;
  personId: number | null;
  onNavigate: (to: string) => void;
}

/** Students with an observation still waiting on this phone for signal, by person id. */
function useWaitingFor(taskId: number): Map<number, number> {
  const items = usePending();
  const counts = new Map<number, number>();
  for (const item of items) {
    if (item.path !== observationsPath(taskId)) continue;
    const student = (item.body as { student?: number }).student;
    if (typeof student === "number") counts.set(student, (counts.get(student) ?? 0) + 1);
  }
  return counts;
}

export function ChecklistScreen({ siteId, taskId, personId, onNavigate }: Props) {
  const [copy, setCopy] = useState<FieldCopy | null>(null);
  const [offlineCopy, setOfflineCopy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([get<PracticalTask>(`/practical-tasks/${taskId}/`), get<TaskStudent[]>(`/practical-tasks/${taskId}/students/`)])
      .then(([task, students]) => {
        const fresh = { task, students, at: new Date().toISOString() };
        keepCopy(fresh);
        setCopy(fresh);
        setOfflineCopy(false);
        setError(null);
      })
      .catch((err) => {
        const kept = isNetworkError(err) ? readCopy(taskId) : null;
        if (kept) {
          setCopy(kept);
          setOfflineCopy(true);
        } else
          setError(
            isNetworkError(err)
              ? "No signal, and this task has not been opened on this phone before. Open it once with signal to mark it in the field."
              : errorMessage(err, "Could not open the checklist."),
          );
      });
  }, [taskId]);

  useEffect(load, [load]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!copy) return <p className="loading">Opening the checklist…</p>;
  const student = personId === null ? null : copy.students.find((s) => s.person_id === personId);

  return (
    <div className="field">
      <p>
        <button type="button" className="link accent" onClick={() => onNavigate(practicalsPath(siteId, taskId))}>
          ← {copy.task.title}
        </button>
      </p>
      {offlineCopy && (
        <p className="notice" role="status">
          No signal: showing the copy kept on this phone on {dmyTime(copy.at)}. What you save is sent when the signal returns.
        </p>
      )}
      {personId === null || !student ? (
        <StudentPicker copy={copy} siteId={siteId} onNavigate={onNavigate} />
      ) : (
        <Checklist
          key={student.person_id}
          task={copy.task}
          student={student}
          onNext={() => {
            onNavigate(practicalsPath(siteId, taskId, "observe"));
            load();
          }}
          onBack={() => onNavigate(practicalsPath(siteId, taskId))}
        />
      )}
    </div>
  );
}

function StudentPicker({ copy, siteId, onNavigate }: { copy: FieldCopy; siteId: number; onNavigate: (to: string) => void }) {
  const [filter, setFilter] = useState("");
  const waiting = useWaitingFor(copy.task.id);
  const words = filter.trim().toLowerCase();
  const shown = copy.students.filter((s) => !words || `${s.name} ${s.student_no}`.toLowerCase().includes(words));
  return (
    <>
      <h2>Who are you observing?</h2>
      <label>
        Find a student
        <input type="search" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Name or student number" />
      </label>
      {shown.length === 0 && <p className="muted">No student matches.</p>}
      <ul className="pick-list">
        {shown.map((s) => {
          const queued = waiting.get(s.person_id) ?? 0;
          const left = s.attempts_left - queued;
          return (
            <li key={s.person_id}>
              <button
                type="button"
                className="pick"
                disabled={left <= 0}
                onClick={() => onNavigate(practicalsPath(siteId, copy.task.id, "observe", s.person_id))}
              >
                <span className="pick-name">{s.name}</span>
                <span className="pick-sub">
                  {s.student_no} ·{" "}
                  {left <= 0 ? "no attempts left" : `attempt ${s.attempts + queued + 1} of ${copy.task.max_attempts}`}
                  {queued > 0 && ` · ${queued} waiting to send`}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </>
  );
}

interface Mark {
  passed: boolean | null;
  score: number | null;
  comment: string;
}

const answered = (c: Criterion, m: Mark | undefined) => (c.kind === "scored" ? m?.score != null : m?.passed != null);

function Checklist({ task, student, onNext, onBack }: { task: PracticalTask; student: TaskStudent; onNext: () => void; onBack: () => void }) {
  const [marks, setMarks] = useState<Record<number, Mark>>({});
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const [comments, setComments] = useState("");
  const [where, setWhere] = useState(task.location);
  const [observedAt, setObservedAt] = useState(localDateTime);
  const [photos, setPhotos] = useState<File[]>([]);
  const [place, setPlace] = useState<Place | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<{ queueId: string | null; photoId: string | null; result: Observation | null } | null>(null);
  const savedRef = useRef<HTMLDivElement>(null);
  const waiting = useWaitingFor(task.id).get(student.person_id) ?? 0;

  useEffect(() => {
    if (saved) savedRef.current?.focus();
  }, [saved]);

  const set = (c: Criterion, change: Partial<Mark>) =>
    setMarks((all) => ({ ...all, [c.id]: { ...(all[c.id] ?? { passed: null, score: null, comment: "" }), ...change } }));

  let earned = 0;
  let possible = 0;
  for (const c of task.criteria) {
    possible += c.max_score;
    const m = marks[c.id];
    if (c.kind === "scored") earned += Math.min(m?.score ?? 0, c.max_score);
    else if (m?.passed) earned += 1;
  }
  const criticalFailed = task.criteria.some(
    (c) => c.is_critical && answered(c, marks[c.id]) && !(c.kind === "scored" ? (marks[c.id].score ?? 0) >= c.pass_score : marks[c.id].passed),
  );
  const missing = task.criteria.filter((c) => !answered(c, marks[c.id]));

  async function save(e: FormEvent) {
    e.preventDefault();
    if (missing.length > 0) {
      setError(`Every criterion needs a result. Still to mark: ${missing.map((c) => c.text).join("; ")}.`);
      document.getElementById(`criterion-${missing[0].id}`)?.focus();
      return;
    }
    setSaving(true);
    setError(null);
    const body: Record<string, unknown> = {
      student: student.person_id,
      // The phone's own time: when it was observed, which may be long before the signal returns.
      observed_at: new Date(observedAt).toISOString(),
      results: task.criteria.map((c) => ({
        criterion: c.id,
        ...(c.kind === "scored" ? { score: marks[c.id].score } : { passed: marks[c.id].passed }),
        comment: marks[c.id].comment,
      })),
      comments,
      location_text: where,
    };
    if (place) Object.assign(body, { latitude: place.latitude, longitude: place.longitude });
    const label = `Observation of ${student.name} on ${task.title}`;
    try {
      const sent = await sendPracticalWrite<Observation>(observationsPath(task.id), body, label);
      let photoId: string | null = null;
      try {
        photoId = await attachPhotos(sent, photos, { photosPath: "/observations/{id}/photos/", label: `Photos for ${label}` });
      } catch (err) {
        setError(`The checklist is saved, but the photos were not taken: ${errorMessage(err)}`);
      }
      setSaved({ queueId: sent.queued ? sent.item.id : null, photoId, result: sent.queued ? null : sent.result });
    } catch (err) {
      setError(err instanceof ApiError ? errorMessage(err) : "Could not save. Try again.");
    } finally {
      setSaving(false);
    }
  }

  const attempt = student.attempts + waiting + 1;
  if (saved)
    return (
      <div className="card-block saved-panel" tabIndex={-1} ref={savedRef} aria-labelledby="saved-heading">
        <h2 id="saved-heading">Saved: {student.name}</h2>
        {saved.result ? (
          <p role="status">
            Attempt {saved.result.attempt}: {saved.result.score.earned} of {saved.result.score.possible}
            {saved.result.critical_passed ? "" : ", a critical criterion not met"}. The student sees it once it is released.
          </p>
        ) : (
          <p>
            <SendState id={saved.queueId} />
          </p>
        )}
        <p>
          <PhotoState id={saved.photoId} />
        </p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="big-buttons">
          <button type="button" className="big" onClick={onNext}>
            Next student
          </button>
          <button type="button" className="big secondary" onClick={onBack}>
            Back to the class list
          </button>
        </div>
      </div>
    );

  return (
    <form className="checklist" onSubmit={save} noValidate>
      <div className="field-head">
        <h2>{student.name}</h2>
        <p className="muted">
          {student.student_no} · {task.title} · attempt {attempt} of {task.max_attempts}
        </p>
      </div>
      <ol className="criteria">
        {task.criteria.map((c) => {
          const m = marks[c.id];
          const commentOpen = open[c.id] || !!m?.comment;
          return (
            <li key={c.id} className={answered(c, m) ? "criterion done" : "criterion"}>
              <fieldset id={`criterion-${c.id}`} tabIndex={-1}>
                <legend>
                  <span className="criterion-text">{c.text}</span>
                  {c.is_critical && <span className="pill critical">Critical</span>}
                </legend>
                {c.kind === "pass_fail" ? (
                  <div className="toggle-pair">
                    <button type="button" className="toggle yes" aria-pressed={m?.passed === true} onClick={() => set(c, { passed: true })}>
                      <span aria-hidden="true">{m?.passed === true ? "✓ " : ""}</span>
                      Met
                    </button>
                    <button type="button" className="toggle no" aria-pressed={m?.passed === false} onClick={() => set(c, { passed: false })}>
                      <span aria-hidden="true">{m?.passed === false ? "✗ " : ""}</span>
                      Not met
                    </button>
                  </div>
                ) : c.max_score <= 10 ? (
                  <div className="score-row" role="group" aria-label={`Score out of ${c.max_score}, ${c.pass_score} to pass`}>
                    {Array.from({ length: c.max_score + 1 }, (_, n) => (
                      <button
                        key={n}
                        type="button"
                        className={n >= c.pass_score ? "toggle score yes" : "toggle score no"}
                        aria-pressed={m?.score === n}
                        aria-label={`${n} of ${c.max_score}`}
                        onClick={() => set(c, { score: n })}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                ) : (
                  <label>
                    Score out of {c.max_score} ({c.pass_score} to pass)
                    <input
                      type="number"
                      inputMode="numeric"
                      min={0}
                      max={c.max_score}
                      value={m?.score ?? ""}
                      onChange={(e) => set(c, { score: e.target.value === "" ? null : Math.min(Number(e.target.value), c.max_score) })}
                    />
                  </label>
                )}
                {commentOpen ? (
                  <label className="criterion-comment">
                    Comment
                    <input value={m?.comment ?? ""} maxLength={500} onChange={(e) => set(c, { comment: e.target.value })} />
                  </label>
                ) : (
                  <button type="button" className="link accent" onClick={() => setOpen({ ...open, [c.id]: true })}>
                    Add a comment
                  </button>
                )}
              </fieldset>
            </li>
          );
        })}
      </ol>
      <label>
        Comments for the student
        <textarea value={comments} onChange={(e) => setComments(e.target.value)} />
      </label>
      <PhotoPicker files={photos} onChange={setPhotos} idPrefix={`obs-${task.id}`} />
      <div className="grid2">
        <label>
          Where
          <input value={where} maxLength={160} onChange={(e) => setWhere(e.target.value)} placeholder="Plot 7" />
        </label>
        <label>
          Observed at
          <input type="datetime-local" value={observedAt} onChange={(e) => setObservedAt(e.target.value)} required />
        </label>
      </div>
      <LocationButton place={place} onChange={setPlace} />
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="sticky-save">
        <span className="tally" aria-live="polite">
          {earned} of {possible}
          {criticalFailed ? " · critical not met" : ""}
          {missing.length > 0 ? ` · ${missing.length} to mark` : ""}
        </span>
        <button type="submit" className="big" disabled={saving}>
          {saving ? "Saving…" : "Save observation"}
        </button>
      </div>
    </form>
  );
}
