import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, errorMessage, get, post } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { AttendancePolicy, ClassSession, SiteGroup, SrmsAnswer, TotalsRow } from "../../api/types-talk";
import { dmy, dmyTime, plural } from "../../app/format";
import { classAddress, useHashRoute } from "../../app/router";
import { clock, fromLocalInput, rows } from "../forums/shared";
import { CheckInForm, CodeScreen } from "./CheckIn";
import { checkInOpen, localDay, sessionWhen, STATUS_LABEL } from "./labels";
import { Register } from "./Register";
import "../talk.css";

interface Props {
  siteId: number;
  teaching: boolean;
}

function Where({ session }: { session: ClassSession }) {
  return (
    <>
      {session.location && <span>{session.location}</span>}
      {session.meeting_url && (
        <a href={session.meeting_url} target="_blank" rel="noopener noreferrer">
          Join online
        </a>
      )}
      {session.recording_url && (
        <a href={session.recording_url} target="_blank" rel="noopener noreferrer">
          Recording
        </a>
      )}
    </>
  );
}

/** One class (#/sites/4/classes/9): the register for teaching staff, check-in for a student. */
function ClassView({ siteId, sessionId, code, teaching }: { siteId: number; sessionId: number; code: boolean; teaching: boolean }) {
  const [session, setSession] = useState<ClassSession | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<ClassSession>(`/class-sessions/${sessionId}/`)
      .then(setSession)
      .catch((err) => setError(errorMessage(err, "Could not open this class.")));
  }, [sessionId]);

  useEffect(load, [load]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!session) return <p className="loading">Opening the class…</p>;
  const base = `#/sites/${siteId}/classes`;

  return (
    <>
      <p>
        <a href={code ? `${base}/${session.id}` : base}>{code ? "Back to the register" : "All classes"}</a>
      </p>
      {!code && (
        <div className="module">
          <h2 className="talk-form-title">{session.title}</h2>
          <p className="muted">{sessionWhen(session)}</p>
          <p className="talk-where">
            <Where session={session} />
          </p>
        </div>
      )}
      {teaching && code && <CodeScreen session={session} />}
      {teaching && !code && session.takes_attendance && (
        <>
          {checkInOpen(session) && (
            <p>
              <a className="button" href={`${base}/${session.id}/code`}>
                Show the check-in code in the room
              </a>
            </p>
          )}
          <Register session={session} />
        </>
      )}
      {!teaching && session.takes_attendance && (
        <section aria-labelledby="check-in-title">
          <h2 id="check-in-title">Check in</h2>
          {session.my_status ? (
            <p className="notice good">Your attendance: {STATUS_LABEL[session.my_status].toLowerCase()}.</p>
          ) : checkInOpen(session) ? (
            <CheckInForm session={session} onDone={load} />
          ) : (
            <p className="muted">Check-in opens 15 minutes before the class and closes when it ends.</p>
          )}
        </section>
      )}
      {!session.takes_attendance && <p className="muted">Attendance is not taken at this class.</p>}
    </>
  );
}

interface Draft {
  title: string;
  starts: string;
  ends: string;
  location: string;
  meeting_url: string;
  group: string;
  takes_attendance: boolean;
}

function NewClass({ siteId, onMade }: { siteId: number; onMade: () => void }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [groups, setGroups] = useState<SiteGroup[]>([]);
  const [error, setError] = useState<string | null>(null);

  const opened = draft !== null;
  useEffect(() => {
    if (!opened) return;
    get<Paginated<SiteGroup> | SiteGroup[]>(`/groups/?site=${siteId}`)
      .then((answer) => setGroups(rows(answer)))
      .catch(() => setGroups([]));
  }, [opened, siteId]);

  if (!draft)
    return (
      <button className="secondary" onClick={() => setDraft({ title: "", starts: "", ends: "", location: "", meeting_url: "", group: "", takes_attendance: true })}>
        Add a class
      </button>
    );

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!draft) return;
    try {
      await post("/class-sessions/", {
        site: siteId,
        title: draft.title,
        starts_at: fromLocalInput(draft.starts),
        ends_at: fromLocalInput(draft.ends),
        location: draft.location,
        meeting_url: draft.meeting_url,
        group: draft.group ? Number(draft.group) : null,
        takes_attendance: draft.takes_attendance,
      });
      setDraft(null);
      setError(null);
      onMade();
    } catch (err) {
      setError(errorMessage(err, "Could not add the class."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={save}>
      <h3>Add a class</h3>
      <label>
        Title
        <input required maxLength={160} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
      </label>
      <div className="grid2">
        <label>
          Starts
          <input required type="datetime-local" value={draft.starts} onChange={(e) => setDraft({ ...draft, starts: e.target.value })} />
        </label>
        <label>
          Ends
          <input required type="datetime-local" value={draft.ends} onChange={(e) => setDraft({ ...draft, ends: e.target.value })} />
        </label>
        <label>
          Room or place
          <input maxLength={160} value={draft.location} onChange={(e) => setDraft({ ...draft, location: e.target.value })} />
        </label>
        <label>
          Meeting link (https)
          <input type="url" placeholder="https://" value={draft.meeting_url} onChange={(e) => setDraft({ ...draft, meeting_url: e.target.value })} />
        </label>
        <label>
          For
          <select value={draft.group} onChange={(e) => setDraft({ ...draft, group: e.target.value })}>
            <option value="">The whole class</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="inline">
        <input type="checkbox" checked={draft.takes_attendance} onChange={(e) => setDraft({ ...draft, takes_attendance: e.target.checked })} />
        Take attendance at this class
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="button" className="secondary" onClick={() => setDraft(null)}>
          Cancel
        </button>
        <button type="submit">Add class</button>
      </div>
    </form>
  );
}

/** Totals per student; for teaching staff, sending them to the SRMS (item 4.15). */
function Totals({ siteId, teaching }: Props) {
  const [totals, setTotals] = useState<TotalsRow[] | null>(null);
  const [policy, setPolicy] = useState<AttendancePolicy | null>(null);
  const [sent, setSent] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<TotalsRow[]>(`/attendance/sites/${siteId}/totals/`)
      .then(setTotals)
      .catch(() => setTotals([]));
    if (teaching)
      get<AttendancePolicy>(`/attendance/sites/${siteId}/policy/`)
        .then(setPolicy)
        .catch(() => setPolicy(null));
  }, [siteId, teaching]);

  async function send() {
    setBusy(true);
    try {
      const answer = await post<SrmsAnswer>(`/attendance/sites/${siteId}/send-to-srms/`);
      if (answer.skipped) setSent({ ok: false, text: `Nothing was sent: ${answer.skipped}` });
      else {
        const parts = [
          `The SRMS took ${plural(answer.accepted?.length ?? 0, "student's total", "students' totals")}`,
          answer.locked?.length ? `${answer.locked.length} locked there` : "",
          answer.unknown?.length ? `${answer.unknown.length} not known to it: ${answer.unknown.join(", ")}` : "",
        ];
        setSent({ ok: true, text: `${parts.filter(Boolean).join("; ")}.` });
      }
    } catch (err) {
      setSent({ ok: false, text: err instanceof ApiError ? err.detail : "No connection: nothing was sent." });
    } finally {
      setBusy(false);
    }
  }

  if (totals === null) return null;
  return (
    <section aria-labelledby="totals-title">
      <h2 id="totals-title">{teaching ? "Attendance totals" : "Your attendance"}</h2>
      {totals.length === 0 ? (
        <p className="muted">No attendance yet.</p>
      ) : (
        <div className="scroll-x" tabIndex={0} role="region" aria-label="Attendance totals">
          <table>
            <thead>
              <tr>
                <th>Student</th>
                <th className="num">Classes</th>
                <th className="num">Present</th>
                <th className="num">Late</th>
                <th className="num">Excused</th>
                <th className="num">Absent</th>
                <th className="num">Not recorded</th>
                <th className="num">Attended</th>
              </tr>
            </thead>
            <tbody>
              {totals.map((t) => (
                <tr key={t.person_id}>
                  <td>
                    {t.name} <span className="muted small">{t.student_no}</span>
                  </td>
                  <td className="num">{t.sessions}</td>
                  <td className="num">{t.present}</td>
                  <td className="num">{t.late}</td>
                  <td className="num">{t.excused}</td>
                  <td className="num">{t.absent}</td>
                  <td className="num">{t.not_recorded}</td>
                  <td className="num">{t.percent === null ? "–" : `${t.percent}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">Attended counts present and late, out of present, late and absent; excused classes are left out.</p>
      {teaching && (
        <div className="module">
          <p>
            {policy?.send_to_srms
              ? `This course's programme makes attendance a condition${policy.minimum_percent ? ` (at least ${policy.minimum_percent}%)` : ""}, so its totals go to the SRMS.`
              : "Attendance is not a condition of this course's programme, so the SRMS may not take its totals. A course administrator sets this."}
            {policy?.last_sent_at ? ` Last sent ${dmyTime(policy.last_sent_at)}.` : ""}
          </p>
          <button onClick={send} disabled={busy}>
            Send to the SRMS
          </button>
          {sent && (
            <p role={sent.ok ? "status" : "alert"} className={sent.ok ? "notice good" : "notice bad"}>
              {sent.text}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

/** A course site's Classes tab (items 4.14, 4.15): class sessions with their links, registers and check-in. */
export function ClassesTab({ siteId, teaching }: Props) {
  const [path] = useHashRoute();
  const open = classAddress(path);
  const [sessions, setSessions] = useState<ClassSession[] | null>(null);
  // The moment the list was read: what is past and what is open for check-in is judged by it.
  const [now, setNow] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<ClassSession> | ClassSession[]>(`/class-sessions/?site=${siteId}`)
      .then((answer) => {
        setNow(Date.now());
        setSessions(rows(answer));
      })
      .catch((err) => setError(errorMessage(err, "Could not load the classes.")));
  }, [siteId]);

  const listing = open === null;
  useEffect(() => {
    if (listing) load();
  }, [load, listing]);

  if (open) return <ClassView siteId={siteId} sessionId={open.session} code={open.code} teaching={teaching} />;

  const upcoming = (sessions ?? []).filter((s) => new Date(s.ends_at).getTime() >= now);
  const past = (sessions ?? []).filter((s) => new Date(s.ends_at).getTime() < now).reverse();

  const list = (items: ClassSession[], label: string) => (
    <ul className="talk-list" aria-label={label}>
      {items.map((s) => (
        <li key={s.id} className="talk-row class-row">
          <span className="talk-row-main">
            <a className="talk-title" href={`#/sites/${siteId}/classes/${s.id}`}>
              {s.title}
            </a>
            <span className="muted small">
              {dmy(localDay(s.starts_at))} {clock(s.starts_at)} to {clock(s.ends_at)}
            </span>
            <span className="talk-where small">
              <Where session={s} />
            </span>
          </span>
          {s.my_status && <span className={`pill att-${s.my_status}`}>{STATUS_LABEL[s.my_status]}</span>}
          {checkInOpen(s, now) && !s.my_status && (
            <a className="button" href={`#/sites/${siteId}/classes/${s.id}`}>
              {teaching ? "Register" : "Check in"}
            </a>
          )}
        </li>
      ))}
    </ul>
  );

  return (
    <>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {sessions === null && !error && <p className="loading">Loading classes…</p>}
      {sessions !== null && (
        <>
          <h2>Coming classes</h2>
          {upcoming.length === 0 ? <p className="muted">No classes coming up.</p> : list(upcoming, "Coming classes")}
          {teaching && (
            <div className="talk-foot">
              <NewClass siteId={siteId} onMade={load} />
            </div>
          )}
          {past.length > 0 && (
            <>
              <h2>Past classes</h2>
              {list(past, "Past classes")}
            </>
          )}
        </>
      )}
      <Totals siteId={siteId} teaching={teaching} />
    </>
  );
}
