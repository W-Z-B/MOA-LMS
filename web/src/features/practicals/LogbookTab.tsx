/**
 * A site's Logbook tab (item 3.14). Students write entries on the phone, with or without signal (the
 * offline queue keeps the entry, IndexedDB its photos), see each entry's state and their hours by kind of
 * place, and correct what comes back. The site's teaching staff sign entries off or return them with a
 * comment; a signed entry is locked.
 */

import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import type { Paginated } from "../../api/types";
import {
  LOGBOOK_STATUS,
  UNIT_TYPES,
  unitLabel,
  type HoursRow,
  type LogbookEntry,
  type LogbookTotals,
  type UnitType,
} from "../../api/types-practicals";
import { dmy, dmyTime } from "../../app/format";
import { sendPracticalWrite, usePending, type Sent } from "../../app/offlineQueue";
import { useHashRoute } from "../../app/router";
import { SendState } from "../../app/SendState";
import { Gallery, LocationButton, PhotoPicker, PhotoState, type Place } from "./FieldWidgets";
import { localDate } from "./helpers";
import { attachPhotos, startPhotoOutbox } from "./photoOutbox";
import { FieldWaiting } from "./PracticalsTab";
import { logbookPath, logbookView } from "./routes";

export function LogbookTab({ siteId, teaching }: { siteId: number; teaching: boolean }) {
  const [path, navigate] = useHashRoute();
  const view = logbookView(path);
  useEffect(startPhotoOutbox, []);
  if (teaching) return <SignOffQueue siteId={siteId} />;
  return (
    <div className="practicals">
      <FieldWaiting />
      {view.view === "list" ? (
        <MyLogbook siteId={siteId} onNavigate={navigate} />
      ) : (
        <EntryForm siteId={siteId} entryId={view.view === "edit" ? view.entryId : null} onNavigate={navigate} />
      )}
    </div>
  );
}

export function HoursList({ hours }: { hours: HoursRow[] }) {
  if (hours.length === 0) return <p className="muted small">No hours yet.</p>;
  const sum = (key: "signed_hours" | "waiting_hours") => hours.reduce((n, h) => n + Number(h[key]), 0);
  return (
    <ul className="plain hours">
      {hours.map((h) => (
        <li key={h.unit_type} className="spread">
          <span>{h.label}</span>
          <span className="num">
            <strong>{h.signed_hours} h signed</strong>
            {Number(h.waiting_hours) > 0 && <span className="muted"> · {h.waiting_hours} h waiting</span>}
          </span>
        </li>
      ))}
      <li className="spread total">
        <span>All work</span>
        <span className="num">
          <strong>{sum("signed_hours").toFixed(2)} h signed</strong>
          {sum("waiting_hours") > 0 && <span className="muted"> · {sum("waiting_hours").toFixed(2)} h waiting</span>}
        </span>
      </li>
    </ul>
  );
}

function EntryCard({ entry: e, children }: { entry: LogbookEntry; children?: ReactNode }) {
  return (
    <article className="module" aria-label={`${dmy(e.work_date)}: ${e.task}`}>
      <div className="panel-head wrap-head">
        <div>
          <h3>{e.task}</h3>
          <p className="muted small">
            {dmy(e.work_date)} · {unitLabel(e.unit_type)}
            {e.unit_text && `, ${e.unit_text}`} · {e.hours} h{e.student_name && ` · ${e.student_name} (${e.student_no})`}
          </p>
        </div>
        <span className={`chip chip-logbook-${e.status}`}>{LOGBOOK_STATUS[e.status]}</span>
      </div>
      {e.notes && <p className="pre">{e.notes}</p>}
      {e.latitude && (
        <p className="muted small">
          Place: {e.latitude}, {e.longitude}
        </p>
      )}
      <Gallery photos={e.photo_files} label={`Photos of ${e.task}`} />
      {e.status !== "pending" && e.reviewed_at && (
        <p className={e.status === "returned" ? "notice bad" : "notice good"}>
          {e.status === "returned" ? "Returned" : "Signed off"} by {e.supervisor_name} on {dmyTime(e.reviewed_at)}
          {e.review_comment && `: ${e.review_comment}`}
        </p>
      )}
      {children}
    </article>
  );
}

function MyLogbook({ siteId, onNavigate }: { siteId: number; onNavigate: (to: string) => void }) {
  const [entries, setEntries] = useState<LogbookEntry[] | null>(null);
  const [hours, setHours] = useState<HoursRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const waiting = usePending().filter((q) => q.path === "/logbook/" && (q.body as { site?: number }).site === siteId);

  const load = useCallback(() => {
    get<Paginated<LogbookEntry>>(`/logbook/?site=${siteId}`)
      .then((r) => {
        setEntries(r.results);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load your logbook.")));
    get<LogbookTotals>(`/sites/${siteId}/logbook-totals/`)
      .then((t) => setHours(t.rows[0]?.hours ?? []))
      .catch(() => setHours([]));
  }, [siteId]);

  useEffect(load, [load]);
  // When an entry kept on the phone is sent, show it in the list.
  const waitingCount = waiting.length;
  const before = useRef(waitingCount);
  useEffect(() => {
    if (waitingCount < before.current) load();
    before.current = waitingCount;
  }, [waitingCount, load]);

  return (
    <>
      <div className="big-buttons">
        <button className="big" onClick={() => onNavigate(logbookPath(siteId, "new"))}>
          Add an entry
        </button>
      </div>
      <h3>Hours by kind of place</h3>
      <HoursList hours={hours} />
      {waiting.length > 0 && (
        <>
          <h3>Waiting on this phone</h3>
          <ul className="plain">
            {waiting.map((q) => (
              <li key={q.id} className="module">
                {q.label} <SendState id={q.id} />
              </li>
            ))}
          </ul>
        </>
      )}
      <h3>Entries</h3>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {entries?.length === 0 && <p className="muted">No entries yet.</p>}
      {entries?.map((e) => (
        <EntryCard key={e.id} entry={e}>
          {e.status !== "signed" && (
            <div className="actions">
              <button className={e.status === "returned" ? "" : "secondary"} onClick={() => onNavigate(logbookPath(siteId, e.id))}>
                {e.status === "returned" ? "Correct and send again" : "Edit"}
              </button>
            </div>
          )}
        </EntryCard>
      ))}
    </>
  );
}

const blank = (): Draft => ({ work_date: localDate(), unit_type: "crop_plot", unit_text: "", task: "", hours: "", notes: "" });

interface Draft {
  work_date: string;
  unit_type: UnitType;
  unit_text: string;
  task: string;
  hours: string;
  notes: string;
}

function EntryForm({ siteId, entryId, onNavigate }: { siteId: number; entryId: number | null; onNavigate: (to: string) => void }) {
  const [draft, setDraft] = useState<Draft>(blank);
  const [existing, setExisting] = useState<LogbookEntry | null>(null);
  const [photos, setPhotos] = useState<File[]>([]);
  const [place, setPlace] = useState<Place | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<{ queueId: string | null; photoId: string | null } | null>(null);
  const savedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (entryId === null) return;
    get<LogbookEntry>(`/logbook/${entryId}/`)
      .then((e) => {
        setExisting(e);
        setDraft({ work_date: e.work_date, unit_type: e.unit_type, unit_text: e.unit_text, task: e.task, hours: e.hours, notes: e.notes });
      })
      .catch((err) => setError(errorMessage(err, "Could not open the entry.")));
  }, [entryId]);

  useEffect(() => {
    if (saved) savedRef.current?.focus();
  }, [saved]);

  async function save(ev: FormEvent) {
    ev.preventDefault();
    setSaving(true);
    setError(null);
    const body: Record<string, unknown> = { ...draft, client_recorded_at: new Date().toISOString() };
    if (place) Object.assign(body, { latitude: place.latitude, longitude: place.longitude });
    const label = `Logbook entry for ${dmy(draft.work_date)}: ${draft.task}`;
    try {
      let sent: Sent<LogbookEntry>;
      if (entryId === null) sent = await sendPracticalWrite<LogbookEntry>("/logbook/", { site: siteId, ...body }, label);
      else sent = { queued: false as const, result: await patch<LogbookEntry>(`/logbook/${entryId}/`, body) };
      let photoId: string | null = null;
      try {
        photoId = await attachPhotos(sent, photos, { photosPath: "/logbook/{id}/photos/", label: `Photos for ${label}` });
      } catch (err) {
        setError(`The entry is saved, but the photos were not taken: ${errorMessage(err)}`);
      }
      setSaved({ queueId: sent.queued ? sent.item.id : null, photoId });
    } catch (err) {
      setError(
        err instanceof TypeError ? "No signal. A correction needs signal: send it again when you have it." : errorMessage(err, "Could not save the entry."),
      );
    } finally {
      setSaving(false);
    }
  }

  if (saved)
    return (
      <div className="card-block saved-panel" tabIndex={-1} ref={savedRef} aria-labelledby="entry-saved">
        <h2 id="entry-saved">{entryId === null ? "Entry saved" : "Correction sent"}</h2>
        <p>{saved.queueId ? <SendState id={saved.queueId} /> : <span role="status">Sent to your supervisor for sign-off.</span>}</p>
        <p>
          <PhotoState id={saved.photoId} />
        </p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="big-buttons">
          <button
            className="big"
            onClick={() => {
              setSaved(null);
              setDraft(blank());
              setPhotos([]);
              setPlace(null);
              onNavigate(logbookPath(siteId, "new"));
            }}
          >
            Add another entry
          </button>
          <button className="big secondary" onClick={() => onNavigate(logbookPath(siteId))}>
            Back to my logbook
          </button>
        </div>
      </div>
    );

  return (
    <form className="stack field" onSubmit={save}>
      <p>
        <button type="button" className="link accent" onClick={() => onNavigate(logbookPath(siteId))}>
          ← My logbook
        </button>
      </p>
      <h2>{entryId === null ? "New logbook entry" : "Correct the entry"}</h2>
      {existing?.status === "returned" && <p className="notice bad">Returned by {existing.supervisor_name}: {existing.review_comment}</p>}
      {entryId !== null && <p className="muted small">A correction needs signal. Saving it sends the entry for sign-off again.</p>}
      <div className="grid2">
        <label>
          Date of the work
          <input type="date" value={draft.work_date} max={localDate()} onChange={(e) => setDraft({ ...draft, work_date: e.target.value })} required />
        </label>
        <label>
          Hours
          <input
            type="number"
            inputMode="decimal"
            min={0.25}
            max={24}
            step="0.25"
            value={draft.hours}
            onChange={(e) => setDraft({ ...draft, hours: e.target.value })}
            required
          />
        </label>
        <label>
          Where
          <select value={draft.unit_type} onChange={(e) => setDraft({ ...draft, unit_type: e.target.value as UnitType })}>
            {UNIT_TYPES.map((u) => (
              <option key={u.value} value={u.value}>
                {u.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Which unit
          <input value={draft.unit_text} maxLength={160} placeholder="Pen 3, broilers" onChange={(e) => setDraft({ ...draft, unit_text: e.target.value })} />
        </label>
        <label className="span2">
          What you did
          <input value={draft.task} maxLength={300} onChange={(e) => setDraft({ ...draft, task: e.target.value })} required />
        </label>
        <label className="span2">
          Notes
          <textarea value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} />
        </label>
      </div>
      {existing && existing.photo_files.length > 0 && <Gallery photos={existing.photo_files} label="Photos already sent" />}
      <PhotoPicker files={photos} onChange={setPhotos} idPrefix="logbook" />
      <LocationButton place={place} onChange={setPlace} />
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="sticky-save">
        <button type="submit" className="big" disabled={saving}>
          {saving ? "Saving…" : entryId === null ? "Save entry" : "Send the correction"}
        </button>
      </div>
    </form>
  );
}

/** Teaching staff: entries waiting for sign-off, oldest first, and each student's hours. */
function SignOffQueue({ siteId }: { siteId: number }) {
  const [entries, setEntries] = useState<LogbookEntry[] | null>(null);
  const [totals, setTotals] = useState<LogbookTotals | null>(null);
  const [returning, setReturning] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<LogbookEntry>>(`/logbook/?site=${siteId}&status=pending`)
      .then((r) => {
        setEntries([...r.results].reverse());
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load the logbook entries.")));
    get<LogbookTotals>(`/sites/${siteId}/logbook-totals/`)
      .then(setTotals)
      .catch(() => setTotals(null));
  }, [siteId]);

  useEffect(load, [load]);

  async function review(entry: LogbookEntry, decision: "sign" | "return") {
    try {
      await post(`/logbook/${entry.id}/review/`, { decision, comment: decision === "return" ? comment : "", client_recorded_at: new Date().toISOString() });
      setNotice(decision === "sign" ? `Signed off: ${entry.student_name}, ${dmy(entry.work_date)}.` : `Returned to ${entry.student_name} with your comment.`);
      setReturning(null);
      setComment("");
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not record the decision."));
    }
  }

  return (
    <div className="practicals">
      <h3>Waiting for sign-off</h3>
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {entries?.length === 0 && <p className="muted">Nothing waits for sign-off.</p>}
      {entries?.map((e) => (
        <EntryCard key={e.id} entry={e}>
          {returning === e.id ? (
            <form
              className="stack sub-form"
              onSubmit={(ev) => {
                ev.preventDefault();
                void review(e, "return");
              }}
            >
              <label>
                What needs correcting
                <textarea value={comment} onChange={(ev) => setComment(ev.target.value)} required />
              </label>
              <div className="actions">
                <button type="button" className="secondary" onClick={() => setReturning(null)}>
                  Cancel
                </button>
                <button type="submit">Return to {e.student_name}</button>
              </div>
            </form>
          ) : (
            <div className="actions">
              <button onClick={() => review(e, "sign")} aria-label={`Sign off ${e.student_name}'s entry for ${dmy(e.work_date)}`}>
                Sign off
              </button>
              <button className="secondary" onClick={() => setReturning(e.id)} aria-label={`Return ${e.student_name}'s entry for ${dmy(e.work_date)}`}>
                Return with a comment
              </button>
            </div>
          )}
        </EntryCard>
      ))}
      <h3>Hours by student</h3>
      {totals?.rows.map((r) => (
        <section key={r.person_id} className="module" aria-label={`Hours of ${r.name}`}>
          <strong>{r.name}</strong> <span className="muted">{r.student_no}</span>
          <HoursList hours={r.hours} />
        </section>
      ))}
    </div>
  );
}
