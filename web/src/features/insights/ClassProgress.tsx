import { useState } from "react";
import type { ProgressRow, StudentProgress } from "../../api/types-insights";
import { dmy } from "../../app/format";
import { ProgressDetail } from "./ProgressDetail";
import { Waiting } from "./shared";
import { percent, seen, useLoad } from "./words";

/** Every student's progress on the course, for teaching staff (item 6.02); a name opens the student's detail. */
export function ClassProgress({ siteId }: { siteId: number }) {
  const { data, error } = useLoad<ProgressRow[]>(`/sites/${siteId}/progress/`, "Could not load the class's progress.");
  const [open, setOpen] = useState<ProgressRow | null>(null);
  if (!data) return <Waiting error={error} />;
  if (data.length === 0) return <p className="muted">No students in this course.</p>;
  return (
    <>
      <p className="muted">
        Last activity is the latest thing recorded on the course: an item first opened, work handed in, a quiz, a post,
        a message or a class attended.
      </p>
      <div className="scroll-x" tabIndex={0} role="region" aria-label="Progress of each student">
        <table>
          <thead>
            <tr>
              <th>Student</th>
              <th className="num">Items done</th>
              <th className="num">Handed in</th>
              <th className="num">Missed</th>
              <th className="num">Coursework</th>
              <th>Last activity</th>
              <th>Last signed in</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.person_id} className={open?.person_id === row.person_id ? "selected" : undefined}>
                <td>
                  <button
                    type="button"
                    className="link accent"
                    aria-expanded={open?.person_id === row.person_id}
                    onClick={() => setOpen(open?.person_id === row.person_id ? null : row)}
                  >
                    {row.student_no} {row.name}
                  </button>
                  {(row.open_alerts ?? 0) > 0 && (
                    <span className="chip chip-waiting">{row.open_alerts === 1 ? "1 alert" : `${row.open_alerts} alerts`}</span>
                  )}
                </td>
                <td className="num">
                  {row.items_done} of {row.items_total}
                </td>
                <td className="num">{row.work_done}</td>
                <td className="num">{row.work_missed}</td>
                <td className="num">{percent(row.coursework_percent)}</td>
                <td>{seen(row.last_seen)}</td>
                <td>{row.last_signed_in ? dmy(row.last_signed_in) : "Not yet"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {open && <StudentPanel key={open.person_id} siteId={siteId} row={open} onClose={() => setOpen(null)} />}
    </>
  );
}

function StudentPanel({ siteId, row, onClose }: { siteId: number; row: ProgressRow; onClose: () => void }) {
  const { data, error } = useLoad<StudentProgress>(`/sites/${siteId}/progress/${row.person_id}/`, "Could not load this student's progress.");
  return (
    <section className="panel-card padded student-panel" aria-label={`Progress of ${row.name}`}>
      <div className="panel-head">
        <h2>
          {row.name} ({row.student_no})
        </h2>
        <button type="button" className="secondary" onClick={onClose}>
          Close
        </button>
      </div>
      {data ? <ProgressDetail data={data} own={false} /> : <Waiting error={error} />}
    </section>
  );
}
