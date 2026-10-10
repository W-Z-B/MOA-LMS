import { useCallback, useEffect, useState } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { Takedown } from "../../api/types-content";
import { dmyTime } from "../../app/format";
import { useCrumb, useFrame } from "../../app/frame";
import "../content/content.css";

type Show = "open" | "decided" | "all";
const STATUS: Record<Takedown["status"], string> = { open: "Waiting for review", withdrawn: "Item withdrawn", restored: "Item restored" };

/**
 * Takedown requests (item 2.19): material someone reported as not allowed on a course. A course administrator
 * withdraws the item (it is unpublished, and only they can bring it back) or restores it.
 */
export default function TakedownsScreen() {
  const [show, setShow] = useState<Show>("open");
  const [rows, setRows] = useState<Takedown[] | null>(null);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { decided } = useFrame();
  useCrumb("Takedown requests");

  const load = useCallback(() => {
    get<Paginated<Takedown>>(show === "open" ? "/takedowns/?status=open" : "/takedowns/")
      .then((page) => setRows(show === "decided" ? page.results.filter((r) => r.status !== "open") : page.results))
      .catch((err) => setError(errorMessage(err, "Could not read the takedown requests.")));
  }, [show]);
  useEffect(load, [load]);

  async function review(row: Takedown, decision: "withdraw" | "restore") {
    setError(null);
    try {
      await post(`/takedowns/${row.id}/review/`, { decision, note: notes[row.id] ?? "" });
      setStatus(decision === "withdraw" ? `“${row.item_title}” is withdrawn.` : `“${row.item_title}” is restored.`);
      decided();
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not record the decision."));
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Takedown requests</h1>
      </div>
      <div className="filters" role="group" aria-label="Show">
        {(["open", "decided", "all"] as const).map((s) => (
          <button key={s} type="button" className={show === s ? "small-button" : "secondary small-button"} aria-pressed={show === s} onClick={() => setShow(s)}>
            {s === "open" ? "Waiting" : s === "decided" ? "Decided" : "All"}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p role="status" className={status ? "notice good" : "sr-only"}>
        {status}
      </p>
      {rows === null && !error && <p className="loading">Reading the requests…</p>}
      {rows?.length === 0 && <p className="muted">{show === "open" ? "Nothing is waiting for review." : "No requests."}</p>}
      <ul className="plain takedowns">
        {rows?.map((row) => (
          <li key={row.id} className="panel-card padded">
            <h2 className="item-title">
              <a href={`#/sites/${row.site}`}>{row.item_title}</a>
            </h2>
            <p className="muted small">
              Reported {dmyTime(row.created_at)} · {STATUS[row.status]}
              {row.reviewed_at ? ` ${dmyTime(row.reviewed_at)}` : ""}
            </p>
            <p className="reason">{row.reason}</p>
            {row.review_note && <p className="muted small">Note: {row.review_note}</p>}
            {row.status === "open" && (
              <div className="stack">
                <label>
                  Note on the decision (optional)
                  <input value={notes[row.id] ?? ""} onChange={(e) => setNotes((prev) => ({ ...prev, [row.id]: e.target.value }))} />
                </label>
                <div className="actions">
                  <button type="button" className="secondary" onClick={() => review(row, "restore")}>
                    Restore the item
                  </button>
                  <button type="button" className="danger" onClick={() => review(row, "withdraw")}>
                    Withdraw the item
                  </button>
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
