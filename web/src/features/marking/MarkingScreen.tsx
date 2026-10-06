import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { AssignmentDetail, GroupChoice, History, Neighbours, RubricScore, StoredFile, WorkSubmission } from "../../api/types-marking";
import { dmyTime } from "../../app/format";
import { useCrumb } from "../../app/frame";
import { plainMark } from "../assignments/words";
import { FeedbackFiles } from "./FeedbackFiles";
import { Moderation } from "./Moderation";
import { RubricMarker } from "./RubricMarker";
import { filledMark, penaltyPercent } from "./score";
import { SpreadsheetMarks } from "./SpreadsheetMarks";
import { SimilarityPanel } from "../assess/SimilarityPanel";
import "./marking.css";

interface Props {
  siteId: number;
  assignmentId: number;
  /** The submission open; the first not yet marked when absent. */
  submissionId: number | null;
  onNavigate: (to: string) => void;
}

const kindOf = (name: string) => {
  const ext = name.toLowerCase().split(".").pop() ?? "";
  if (ext === "pdf") return "pdf";
  if (["jpg", "jpeg", "png", "webp"].includes(ext)) return "image";
  return "other";
};

/**
 * The marking screen (items 2.23 to 2.25, 2.27, 3.09, 3.10, 3.16 to 3.18), after Canvas SpeedGrader: the
 * work beside the mark, previous and next and the next not yet marked, rubric marking that fills the mark,
 * feedback kept as a draft until released, feedback files and recordings, release one or all, second
 * marking, and for the whole class the archive and marks from a spreadsheet. Names stay hidden while
 * marking is anonymous.
 */
export function MarkingScreen({ siteId, assignmentId, submissionId, onNavigate }: Props) {
  const [assignment, setAssignment] = useState<AssignmentDetail | null>(null);
  const [rows, setRows] = useState<WorkSubmission[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  useCrumb(assignment ? `Marking: ${assignment.title}` : null);

  const address = useCallback(
    (id: number) => `/sites/${siteId}/assignments/${assignmentId}/marking/${id}`,
    [siteId, assignmentId],
  );

  const loadAll = useCallback(() => {
    Promise.all([
      get<AssignmentDetail>(`/assignments/${assignmentId}/`),
      get<WorkSubmission[]>(`/assignments/${assignmentId}/submissions/`),
    ])
      .then(([a, r]) => {
        setAssignment(a);
        setRows(r);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not open the marking.")));
  }, [assignmentId]);

  useEffect(loadAll, [loadAll]);

  // With no submission named, open the first not yet marked (or the first), so the address names it.
  useEffect(() => {
    if (submissionId === null && rows && rows.length) {
      const first = rows.find((r) => !r.mark) ?? rows[0];
      onNavigate(address(first.id));
    }
  }, [submissionId, rows, onNavigate, address]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!assignment || !rows) return <p className="loading">Opening the marking…</p>;
  const current = rows.find((r) => r.id === submissionId) ?? null;
  const marked = rows.filter((r) => r.mark).length;
  const released = rows.filter((r) => r.mark?.is_released).length;

  async function releaseAll() {
    if (!window.confirm(`Release every mark of “${assignment!.title}” to the students, with their feedback?`)) return;
    try {
      const done = await post<{ released: number }>(`/assignments/${assignmentId}/release/`);
      setNotice(`Released ${done.released} mark${done.released === 1 ? "" : "s"}.`);
      loadAll();
    } catch (err) {
      setNotice(errorMessage(err, "Could not release the marks."));
    }
  }

  return (
    <div className="marking">
      <div className="page-head">
        <div className="stacked">
          <h1>{assignment.title}</h1>
          <p className="muted">
            {rows.length} handed in · {marked} marked · {released} released · out of {plainMark(assignment.max_mark)}
          </p>
        </div>
        <a className="button" href={`#/sites/${siteId}/assignments`}>
          Back to assignments
        </a>
      </div>
      {assignment.anonymous && !assignment.marks_released_at && (
        <p className="notice">Anonymous marking: names are hidden until the marks are released. Students are shown by a candidate number.</p>
      )}
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}

      <details className="class-tools">
        <summary>The whole class: release, download, marks from a spreadsheet</summary>
        <div className="stack">
          <div className="actions">
            <button type="button" onClick={releaseAll} disabled={marked === released}>
              Release all marks
            </button>
            <a className="button" href={`/api/v1/assignments/${assignmentId}/download-all/`} download>
              Download every hand-in (zip)
            </a>
          </div>
          {assignment.moderation === "sample" && <SampleForSecondMarking assignmentId={assignmentId} onDone={setNotice} />}
          <SpreadsheetMarks assignmentId={assignmentId} anonymous={assignment.anonymous && !assignment.marks_released_at} onApplied={loadAll} />
        </div>
      </details>

      {rows.length === 0 && <p className="muted">Nothing has been handed in yet.</p>}
      {current && (
        <OneSubmission
          key={current.id}
          assignment={assignment}
          rows={rows}
          submission={current}
          open={(id) => onNavigate(address(id))}
          onSaved={(saved, words) => {
            setRows(rows.map((r) => (r.id === saved.id ? saved : r)));
            setNotice(words);
          }}
          onGroupSaved={loadAll}
        />
      )}
    </div>
  );
}

interface OneProps {
  assignment: AssignmentDetail;
  rows: WorkSubmission[];
  submission: WorkSubmission;
  open: (id: number) => void;
  onSaved: (saved: WorkSubmission, words: string) => void;
  onGroupSaved: () => void;
}

function OneSubmission({ assignment, rows, submission, open, onSaved, onGroupSaved }: OneProps) {
  const [neighbours, setNeighbours] = useState<Neighbours | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [mark, setMark] = useState(submission.mark ? plainMark(submission.mark.raw_mark) : "");
  const [feedback, setFeedback] = useState(submission.mark?.feedback ?? "");
  const [scores, setScores] = useState<RubricScore[]>(submission.mark?.rubric_scores ?? []);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const rubric = assignment.rubric_detail;
  const locked = submission.srms_locked_at !== null;
  const filled = rubric ? filledMark(rubric, scores, assignment.max_mark) : null;
  const value = rubric && rubric.kind !== "descriptive" ? (filled ?? "") : mark;
  const penalty = penaltyPercent(assignment, submission);

  const loadHistory = useCallback(() => {
    get<History>(`/submissions/${submission.id}/history/`)
      .then(setHistory)
      .catch(() => setHistory(null));
  }, [submission.id]);

  useEffect(() => {
    get<Neighbours>(`/submissions/${submission.id}/neighbours/`)
      .then(setNeighbours)
      .catch(() => setNeighbours(null));
    loadHistory();
  }, [submission.id, submission.mark, loadHistory]);

  async function save(release: boolean) {
    setSaving(true);
    setError(null);
    try {
      const saved = rubric
        ? await post<WorkSubmission>(`/submissions/${submission.id}/rubric-mark/`, {
            scores,
            ...(rubric.kind === "descriptive" ? { mark } : {}),
            feedback,
            is_released: release,
          })
        : await post<WorkSubmission>(`/submissions/${submission.id}/mark/`, { mark, feedback, is_released: release });
      onSaved(saved, release ? `Released to ${saved.student_name || saved.student_no}.` : "Saved as a draft. The student does not see it yet.");
    } catch (err) {
      setError(errorMessage(err, "Could not save the mark."));
    } finally {
      setSaving(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void save(false);
  }

  const who = submission.student_name ? `${submission.student_name} (${submission.student_no})` : submission.student_no;
  const max = Number(assignment.max_mark);
  const counts = value === "" ? null : Math.max(0, Number(value) - Math.round(max * penalty) / 100);

  return (
    <>
      <nav className="marking-nav" aria-label="Students">
        <button type="button" className="secondary" disabled={!neighbours?.previous} onClick={() => neighbours?.previous && open(neighbours.previous)}>
          Previous
        </button>
        <label className="grow">
          <span className="sr-only">Student</span>
          <select value={submission.id} onChange={(e) => open(Number(e.target.value))} aria-label="Student">
            {rows.map((r) => (
              <option key={r.id} value={r.id}>
                {r.student_name ? `${r.student_no} ${r.student_name}` : r.student_no}
                {r.mark ? (r.mark.is_released ? " · released" : " · draft") : " · not marked"}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="secondary" disabled={!neighbours?.next} onClick={() => neighbours?.next && open(neighbours.next)}>
          Next
        </button>
        <button type="button" disabled={!neighbours?.next_unmarked} onClick={() => neighbours?.next_unmarked && open(neighbours.next_unmarked)}>
          Next not marked
        </button>
        {neighbours && (
          <span className="muted small">
            {neighbours.position} of {neighbours.total}
          </span>
        )}
      </nav>

      <div className="marking-split">
        <section className="work" aria-label={`Work handed in by ${who}`}>
          <Work submission={submission} />
        </section>

        <aside className="mark-panel" aria-label="Mark and feedback">
          <h2>{who}</h2>
          <p className="chips">
            {submission.is_late && <span className="chip chip-rejected">Late</span>}
            {submission.extended && <span className="chip">Extended</span>}
            {submission.accommodation_applies && <span className="chip chip-waiting">Accommodation applies</span>}
            {submission.group && <span className="chip">Group {submission.group}</span>}
          </p>
          <p className="muted small">
            Handed in {dmyTime(submission.submitted_at)}
            {submission.client_submitted_at && ` (on the device ${dmyTime(submission.client_submitted_at)})`} · due {dmyTime(submission.due_at)} ·{" "}
            {submission.attempts} hand-in{submission.attempts === 1 ? "" : "s"} · receipt {submission.receipt}
          </p>
          {locked && (
            <p className="notice bad" role="note">
              Locked: the coursework was sent to the SRMS on {dmyTime(submission.srms_locked_at!)}. A change now goes through the SRMS correction process.
            </p>
          )}

          <form className="stack" onSubmit={submit} aria-label="Mark">
            {rubric && <RubricMarker rubric={rubric} scores={scores} onChange={setScores} disabled={locked} />}
            {rubric && rubric.kind !== "descriptive" ? (
              <p className="filled" role="status">
                {filled === null ? "Score every criterion to fill the mark." : `The rubric fills the mark: ${filled} out of ${plainMark(assignment.max_mark)}.`}
              </p>
            ) : (
              <label>
                Mark out of {plainMark(assignment.max_mark)}
                <input
                  type="number"
                  min={0}
                  max={max}
                  step="any"
                  inputMode="decimal"
                  value={mark}
                  disabled={locked}
                  onChange={(e) => setMark(e.target.value)}
                  required
                />
              </label>
            )}
            {penalty > 0 && (
              <p className="muted small">
                Handed in late: {penalty}% of the maximum ({plainMark(String(Math.round(max * penalty) / 100))}) is taken
                {counts !== null ? `, so it counts as ${plainMark(String(Math.round(counts * 100) / 100))}` : ""}.
              </p>
            )}
            <label>
              Feedback
              <textarea value={feedback} disabled={locked} onChange={(e) => setFeedback(e.target.value)} rows={5} />
            </label>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            {submission.mark && (
              <p className="muted small">
                {submission.mark.is_released ? "Released" : "Draft, not yet released"}: {plainMark(submission.mark.mark)} out of {plainMark(assignment.max_mark)}
                {Number(submission.mark.penalty) > 0 ? ` after a late penalty of ${plainMark(submission.mark.penalty)}` : ""}.
              </p>
            )}
            {!locked && (
              <div className="actions">
                <button type="submit" className="secondary" disabled={saving || value === ""}>
                  {submission.mark?.is_released ? "Withdraw to draft" : "Save draft"}
                </button>
                <button type="button" disabled={saving || value === ""} onClick={() => save(true)}>
                  {submission.mark?.is_released ? "Save and keep released" : "Save and release"}
                </button>
              </div>
            )}
          </form>

          <FeedbackFiles submission={submission} locked={locked} onChanged={(s) => onSaved(s, "Feedback file returned.")} />
          <SimilarityPanel key={submission.id} submissionId={submission.id} />
          {assignment.is_group && submission.group && <GroupMark assignment={assignment} rows={rows} submission={submission} onSaved={onGroupSaved} />}
          {assignment.moderation !== "none" && (
            <Moderation submission={submission} assignment={assignment} moderation={history?.moderation ?? null} onChanged={(s) => {
              loadHistory();
              if (s) onSaved(s, "The agreed mark is now the mark.");
            }} />
          )}
          {history && (
            <details className="history">
              <summary>History: every hand-in and every version of the mark</summary>
              <ol className="plain small">
                {history.attempts.map((a) => (
                  <li key={`a${a.number}`}>
                    Hand-in {a.number}, {dmyTime(a.submitted_at)}
                    {a.is_late ? " (late)" : ""}: receipt {a.receipt}
                    {a.integrity_accepted ? ", integrity statement accepted" : ""}
                  </li>
                ))}
                {history.marks.map((m, i) => (
                  <li key={`m${i}`}>
                    Mark {plainMark(m.mark)} ({m.is_released ? "released" : "draft"}, {m.source}) by {m.changed_by ?? "someone"} on {dmyTime(m.changed_at)}
                  </li>
                ))}
              </ol>
            </details>
          )}
        </aside>
      </div>
    </>
  );
}

/** The work itself: the typed answer, and each file shown by the browser's own viewer or offered to download. */
function Work({ submission }: { submission: WorkSubmission }) {
  const [chosen, setChosen] = useState(0);
  const files = submission.files;
  const file: StoredFile | undefined = files[Math.min(chosen, files.length - 1)];
  return (
    <>
      {submission.text && <div className="answer">{submission.text}</div>}
      {files.length > 1 && (
        <div className="actions" role="group" aria-label="Files handed in">
          {files.map((f, i) => (
            <button key={f.id} type="button" className="secondary small-button" aria-pressed={i === chosen} onClick={() => setChosen(i)}>
              {f.filename}
            </button>
          ))}
        </div>
      )}
      {file && <Viewer key={file.id} file={file} />}
      {!submission.text && files.length === 0 && <p className="muted">Nothing to show.</p>}
    </>
  );
}

function Viewer({ file }: { file: StoredFile }) {
  const kind = kindOf(file.filename);
  const shown = `${file.download_url}?inline=1`;
  const download = (
    <a className="button" href={file.download_url}>
      Download {file.filename}
    </a>
  );
  if (kind === "pdf")
    return (
      <div className="viewer">
        <object data={shown} type="application/pdf" aria-label={`${file.filename}, as handed in`}>
          <p className="muted">This browser cannot show the PDF here. {download}</p>
        </object>
        <p className="actions">{download}</p>
      </div>
    );
  if (kind === "image")
    return (
      <div className="viewer">
        <img src={shown} alt={`${file.filename}, as handed in`} />
        <p className="actions">{download}</p>
      </div>
    );
  return (
    <div className="viewer other">
      <p className="muted">A {file.filename.split(".").pop()?.toUpperCase()} file cannot be shown in the page.</p>
      {download}
    </div>
  );
}

/** A group's work is marked once: the mark goes to every member, with any member's adjustment (item 2.27). */
function GroupMark({ assignment, rows, submission, onSaved }: { assignment: AssignmentDetail; rows: WorkSubmission[]; submission: WorkSubmission; onSaved: () => void }) {
  const members = rows.filter((r) => r.group === submission.group);
  const [groups, setGroups] = useState<GroupChoice[]>([]);
  const [mark, setMark] = useState("");
  const [feedback, setFeedback] = useState("");
  const [adjust, setAdjust] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<GroupChoice[]>(`/sites/${assignment.site}/my-groups/`)
      .then(setGroups)
      .catch(() => setGroups([]));
  }, [assignment.site]);

  async function save(e: FormEvent) {
    e.preventDefault();
    const group = groups.find((g) => g.name === submission.group);
    if (!group) return;
    setError(null);
    try {
      await post(`/assignments/${assignment.id}/group-mark/`, {
        group: group.id,
        mark,
        feedback,
        is_released: false,
        adjustments: Object.entries(adjust)
          .filter(([, v]) => v !== "" && Number(v) !== 0)
          .map(([student_no, adjustment]) => ({ student_no, adjustment })),
      });
      onSaved();
    } catch (err) {
      setError(errorMessage(err, "Could not save the group's mark."));
    }
  }

  return (
    <details className="history">
      <summary>Mark the whole group: {submission.group}</summary>
      <form className="stack" onSubmit={save}>
        <label>
          The group's mark
          <input type="number" min={0} max={Number(assignment.max_mark)} step="any" value={mark} onChange={(e) => setMark(e.target.value)} required />
        </label>
        <label>
          Feedback for the group
          <textarea value={feedback} onChange={(e) => setFeedback(e.target.value)} />
        </label>
        {members.map((m) => (
          <label key={m.id}>
            Adjustment for {m.student_name || m.student_no} (+ or −)
            <input type="number" step="any" value={adjust[m.student_no] ?? ""} onChange={(e) => setAdjust({ ...adjust, [m.student_no]: e.target.value })} />
          </label>
        ))}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="submit" className="secondary">
            Save for every member, as a draft
          </button>
        </div>
      </form>
    </details>
  );
}

function SampleForSecondMarking({ assignmentId, onDone }: { assignmentId: number; onDone: (words: string) => void }) {
  const [percent, setPercent] = useState("20");
  async function sample(e: FormEvent) {
    e.preventDefault();
    try {
      const r = await post<{ sampled: number[] }>(`/assignments/${assignmentId}/moderation-sample/`, { percent: Number(percent) });
      onDone(`${r.sampled.length} marked submission${r.sampled.length === 1 ? "" : "s"} chosen for a second marker.`);
    } catch (err) {
      onDone(errorMessage(err, "Could not choose the sample."));
    }
  }
  return (
    <form className="form-row" onSubmit={sample}>
      <label>
        Share of the marked work a second marker checks (%)
        <input type="number" min={1} max={100} value={percent} onChange={(e) => setPercent(e.target.value)} />
      </label>
      <div className="actions">
        <button type="submit" className="secondary">
          Choose a sample
        </button>
      </div>
    </form>
  );
}
