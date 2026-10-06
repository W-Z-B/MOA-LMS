import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import type { DatedThing } from "../../api/types-content";
import { plural } from "../../app/format";
import { fromLocalInput, toLocalInput } from "./dates";

const KIND: Record<DatedThing["kind"], string> = { module: "Module", item: "Item", assignment: "Assignment" };
const FIELD: Record<DatedThing["field"], string> = { available_from: "Shown from", opens_at: "Opens", due_at: "Due" };
const key = (row: DatedThing) => `${row.kind}-${row.id}-${row.field}`;

/**
 * The date manager (item 2.18): every dated thing on the course in one table. Changes are saved together,
 * all or nothing, so a course is never left half moved; or every date is moved at once by a number of days
 * or to a new start date.
 */
export function DateManager({ siteId }: { siteId: number }) {
  const [rows, setRows] = useState<DatedThing[] | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [how, setHow] = useState<"days" | "start">("days");
  const [days, setDays] = useState("7");
  const [start, setStart] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<DatedThing[]>(`/sites/${siteId}/dates/`)
      .then(setRows)
      .catch((err) => setError(errorMessage(err, "Could not read the course's dates.")));
  }, [siteId]);

  const changes = (rows ?? [])
    .filter((row) => key(row) in edits && edits[key(row)] !== toLocalInput(row.value))
    .map((row) => ({ kind: row.kind, id: row.id, field: row.field, value: fromLocalInput(edits[key(row)]) }));

  async function run(action: () => Promise<DatedThing[]>, done: string) {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      setRows(await action());
      setEdits({});
      setStatus(done);
    } catch (err) {
      setError(errorMessage(err, "Could not change the dates. Nothing was changed."));
    } finally {
      setBusy(false);
    }
  }

  const saveAll = (e: FormEvent) => {
    e.preventDefault();
    void run(() => patch<DatedThing[]>(`/sites/${siteId}/dates/`, { changes }), `Saved ${plural(changes.length, "date", "dates")}.`);
  };
  const shiftAll = (e: FormEvent) => {
    e.preventDefault();
    const body = how === "days" ? { offset_days: Number(days) } : { start_date: start };
    void run(
      () => post<DatedThing[]>(`/sites/${siteId}/shift-dates/`, body),
      how === "days" ? `Moved every date by ${plural(Number(days), "day", "days")}.` : "Moved every date to the new start.",
    );
  };

  return (
    <section className="panel-card padded setup-section" aria-labelledby="dates-title">
      <h2 id="dates-title">Dates</h2>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p role="status" className={status ? "notice good" : "sr-only"}>
        {status}
      </p>
      {rows === null && !error && <p className="loading">Reading the dates…</p>}
      {rows !== null && rows.length === 0 && <p className="muted">Nothing on this course has a date yet.</p>}
      {rows !== null && rows.length > 0 && (
        <form onSubmit={saveAll}>
          <div className="scroll-x" tabIndex={0} role="region" aria-label="Every date on the course">
            <table className="dates">
              <thead>
                <tr>
                  <th scope="col">What</th>
                  <th scope="col">Date</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const k = key(row);
                  const value = k in edits ? edits[k] : toLocalInput(row.value);
                  return (
                    <tr key={k} className={k in edits && value !== toLocalInput(row.value) ? "changed" : undefined}>
                      <td>
                        <span className="muted small block">
                          {KIND[row.kind]} · {FIELD[row.field]}
                        </span>
                        {row.title}
                      </td>
                      <td>
                        <input
                          type="datetime-local"
                          aria-label={`${FIELD[row.field]}: ${row.title}`}
                          value={value}
                          required={row.field === "due_at"}
                          onChange={(e) => setEdits({ ...edits, [k]: e.target.value })}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="actions">
            <button type="button" className="secondary" disabled={busy || changes.length === 0} onClick={() => setEdits({})}>
              Undo changes
            </button>
            <button type="submit" disabled={busy || changes.length === 0}>
              Save {changes.length > 0 ? plural(changes.length, "change", "changes") : "changes"}
            </button>
          </div>
        </form>
      )}
      {rows !== null && rows.length > 0 && (
        <form className="stack shift" onSubmit={shiftAll}>
          <h3>Move every date</h3>
          <fieldset>
            <legend>How</legend>
            <label className="inline">
              <input type="radio" name="shift-how" checked={how === "days"} onChange={() => setHow("days")} /> By a number of days
            </label>
            <label className="inline">
              <input type="radio" name="shift-how" checked={how === "start"} onChange={() => setHow("start")} /> So the first date falls on a new
              start date
            </label>
          </fieldset>
          {how === "days" ? (
            <label>
              Days (a minus number moves them earlier)
              <input id="shift-days" type="number" inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} required />
            </label>
          ) : (
            <label>
              New start date
              <input id="shift-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} required />
            </label>
          )}
          <div className="actions">
            <button type="submit" className="secondary" disabled={busy}>
              Move every date
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
