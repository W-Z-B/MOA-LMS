import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post, remove } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { AssignmentDetail, Extension, GroupChoice, Member } from "../../api/types-marking";
import { studentsOf } from "./classList";
import { dmyTime } from "../../app/format";
import { fromLocalInput } from "./words";

/**
 * Extensions for one student or one group, with the reason recorded (item 2.26). The late flag, the
 * penalty, closing and the zero for missing work all follow the extended date.
 */
export function Extensions({ assignment }: { assignment: AssignmentDetail }) {
  const [rows, setRows] = useState<Extension[]>([]);
  const [students, setStudents] = useState<Member[]>([]);
  const [groups, setGroups] = useState<GroupChoice[]>([]);
  const [who, setWho] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<Extension>>(`/extensions/?assignment=${assignment.id}`)
      .then((r) => setRows(r.results))
      .catch((err) => setError(errorMessage(err, "Could not load the extensions.")));
  }, [assignment.id]);

  useEffect(() => {
    load();
    studentsOf(assignment.site)
      .then(setStudents)
      .catch(() => setStudents([]));
    get<GroupChoice[]>(`/sites/${assignment.site}/my-groups/`)
      .then(setGroups)
      .catch(() => setGroups([]));
  }, [assignment.site, load]);

  async function grant(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const [kind, id] = who.split(":");
    try {
      await post("/extensions/", {
        assignment: assignment.id,
        student: kind === "student" ? Number(id) : null,
        group: kind === "group" ? Number(id) : null,
        due_at: fromLocalInput(dueAt),
        reason,
      });
      setWho("");
      setDueAt("");
      setReason("");
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not grant the extension."));
    }
  }

  async function withdraw(row: Extension) {
    try {
      await remove(`/extensions/${row.id}/`);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not withdraw the extension."));
    }
  }

  const nameOf = (row: Extension) =>
    row.group != null
      ? `Group ${groups.find((g) => g.id === row.group)?.name ?? row.group}`
      : (students.find((s) => s.person_id === row.student)?.name ?? row.student_no ?? "");

  return (
    <section className="stack sub-form" aria-label={`Extensions for ${assignment.title}`}>
      <h3>Extensions</h3>
      {rows.length === 0 && <p className="muted">No extensions. Everyone is due {dmyTime(assignment.due_at)}.</p>}
      {rows.length > 0 && (
        <ul className="plain">
          {rows.map((row) => (
            <li key={row.id} className="spread">
              <span>
                <strong>{nameOf(row)}</strong>: due {dmyTime(row.due_at)}
                <span className="muted small" style={{ display: "block" }}>
                  {row.reason}
                </span>
              </span>
              <button type="button" className="secondary small-button" onClick={() => withdraw(row)}>
                Withdraw
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="grid2" onSubmit={grant}>
        <label>
          For
          <select id={`ext-who-${assignment.id}`} value={who} onChange={(e) => setWho(e.target.value)} required>
            <option value="" disabled>
              Choose a student or a group…
            </option>
            {students.map((s) => (
              <option key={`s${s.person_id}`} value={`student:${s.person_id}`}>
                {s.external_id} {s.name}
              </option>
            ))}
            {groups.map((g) => (
              <option key={`g${g.id}`} value={`group:${g.id}`}>
                Group: {g.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          New due date
          <input id={`ext-due-${assignment.id}`} type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} required />
        </label>
        <label className="span2">
          Reason
          <input id={`ext-reason-${assignment.id}`} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} required />
        </label>
        {error && (
          <p role="alert" className="error span2">
            {error}
          </p>
        )}
        <div className="actions span2">
          <button type="submit">Grant the extension</button>
        </div>
      </form>
    </section>
  );
}
