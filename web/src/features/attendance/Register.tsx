import { useEffect, useState } from "react";
import { ApiError, errorMessage, get, post } from "../../api/client";
import type { AttendanceStatus, ClassSession, RegisterRow, RegisterSaved } from "../../api/types-talk";
import { plural } from "../../app/format";
import { isNetworkError, sendOrQueue } from "../../app/offlineQueue";
import { SendState } from "../../app/SendState";
import "../talk.css";

import { STATUS_LABEL } from "./labels";

const STATUSES = Object.keys(STATUS_LABEL) as AttendanceStatus[];

/** The register as last read on this device, so a lecturer without signal can still open it and take it. */
const cacheKey = (session: number) => `gsa-lms.register.${session}`;

function cached(session: number): RegisterRow[] | null {
  try {
    return JSON.parse(localStorage.getItem(cacheKey(session)) ?? "null");
  } catch {
    return null;
  }
}

function keep(session: number, register: RegisterRow[]) {
  try {
    localStorage.setItem(cacheKey(session), JSON.stringify(register));
  } catch {
    /* a convenience only: without storage the register needs a connection to open */
  }
}

/**
 * The lecturer's register on a phone (items 4.14, 4.15): a row a student, four choices each, all present at
 * one tap. It is sent with the phone's time and an Idempotency-Key, through the offline queue when there is no
 * signal; a student's own check-in made later than the register is kept by the server.
 */
export function Register({ session }: { session: ClassSession }) {
  const [rows, setRows] = useState<RegisterRow[] | null>(null);
  const [marks, setMarks] = useState<Record<number, AttendanceStatus>>({});
  const [fromDevice, setFromDevice] = useState(false);
  const [queued, setQueued] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function show(register: RegisterRow[]) {
    setRows(register);
    setMarks(Object.fromEntries(register.filter((r) => r.status).map((r) => [r.person_id, r.status as AttendanceStatus])));
  }

  useEffect(() => {
    get<RegisterRow[]>(`/class-sessions/${session.id}/register/`)
      .then((register) => {
        keep(session.id, register);
        show(register);
      })
      .catch((err) => {
        const kept = isNetworkError(err) ? cached(session.id) : null;
        if (kept) {
          setFromDevice(true);
          show(kept);
        } else setError(errorMessage(err, "No connection, and this register has not been opened on this device before."));
      });
  }, [session.id]);

  if (!rows) return error ? <p role="alert" className="error">{error}</p> : <p className="loading">Opening the register…</p>;

  const changed = rows.filter((r) => marks[r.person_id] && marks[r.person_id] !== r.status);
  const counts = STATUSES.map((s) => `${Object.values(marks).filter((m) => m === s).length} ${STATUS_LABEL[s].toLowerCase()}`).join(", ");

  function markRest(status: AttendanceStatus) {
    const next = { ...marks };
    rows!.forEach((r) => {
      if (!next[r.person_id]) next[r.person_id] = status;
    });
    setMarks(next);
  }

  async function save() {
    setBusy(true);
    try {
      const sent = await sendOrQueue<RegisterSaved>({
        kind: "register",
        method: "POST",
        path: `/class-sessions/${session.id}/register/`,
        body: {
          records: changed.map((r) => ({ student: r.person_id, status: marks[r.person_id] })),
          client_recorded_at: new Date().toISOString(),
        },
        label: `Register for ${session.title}`,
      });
      setError(null);
      if (sent.queued) {
        setQueued(sent.item.id);
        setNotice(null);
        // Shown as taken on this device; the server settles it when the register is sent.
        const taken = rows!.map((r) => ({ ...r, status: marks[r.person_id] ?? r.status }));
        keep(session.id, taken);
        setRows(taken);
      } else {
        keep(session.id, sent.result.register);
        show(sent.result.register);
        const kept = sent.result.kept.length;
        setNotice(
          `Register saved: ${plural(sent.result.saved, "student", "students")}.` +
            (kept ? ` ${plural(kept, "student", "students")} checked in after you took it, so their own record stands.` : ""),
        );
      }
    } catch (err) {
      setError(errorMessage(err, "Could not save the register."));
    } finally {
      setBusy(false);
    }
  }

  async function close() {
    try {
      const answer = await post<{ marked_absent: number }>(`/class-sessions/${session.id}/close-register/`);
      setNotice(`Register closed: ${plural(answer.marked_absent, "student", "students")} with no record marked absent.`);
      const register = await get<RegisterRow[]>(`/class-sessions/${session.id}/register/`);
      keep(session.id, register);
      show(register);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Closing the register needs a connection.");
    }
  }

  return (
    <section aria-labelledby="register-title">
      <h2 id="register-title">Register</h2>
      {fromDevice && <p className="notice">No connection: this is the register as last opened on this phone. Take it; it is sent when the connection returns.</p>}
      <p className="muted small">{rows.length === 0 ? "No students are expected at this class." : counts}</p>
      {rows.length > 0 && (
        <div className="actions">
          <button className="secondary" onClick={() => markRest("present")}>
            Mark the rest present
          </button>
          <button className="secondary" onClick={() => markRest("absent")}>
            Mark the rest absent
          </button>
        </div>
      )}
      <ul className="register" aria-label="Students">
        {rows.map((r) => (
          <li key={r.person_id}>
            <span className="register-name">
              {r.name} <span className="muted small">{r.student_no}</span>
              {r.how === "check_in" && <span className="muted small"> · checked in</span>}
            </span>
            <div className="segmented" role="radiogroup" aria-label={`${r.name}`}>
              {STATUSES.map((s) => (
                <label key={s} className={marks[r.person_id] === s ? `seg on seg-${s}` : "seg"}>
                  <input
                    type="radio"
                    name={`att-${r.person_id}`}
                    value={s}
                    checked={marks[r.person_id] === s}
                    onChange={() => setMarks((prev) => ({ ...prev, [r.person_id]: s }))}
                  />
                  {STATUS_LABEL[s]}
                </label>
              ))}
            </div>
          </li>
        ))}
      </ul>
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}
      {error && rows && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {rows.length > 0 && (
        <div className="actions talk-foot register-foot">
          <button className="wide" disabled={busy || changed.length === 0} onClick={save}>
            {changed.length === 0 ? "No changes to save" : `Save register (${plural(changed.length, "change", "changes")})`}
          </button>
          <SendState id={queued} />
          <button className="secondary" onClick={close}>
            Close register: no record means absent
          </button>
        </div>
      )}
    </section>
  );
}
