import { useEffect, useState } from "react";
import { errorMessage, get } from "../../api/client";
import type { WaitingItem } from "../../api/types";
import { dmy, dmyTime, initials } from "../../app/format";

/** "Waiting since 01/10/2026, 4 days · AGR101" or, for work due, "Due 06/10/2026 14:00 · AGR101". */
function waited(item: WaitingItem): string {
  const where = item.site_title ? ` · ${item.site_title}` : "";
  if (item.due_at) return `${item.overdue ? "Was due" : "Due"} ${dmyTime(item.due_at)}${where}`;
  const days = item.waited_days > 0 ? `, ${item.waited_days} ${item.waited_days === 1 ? "day" : "days"}` : "";
  return `Waiting since ${dmy(item.since)}${days}${where}`;
}

/**
 * Everything waiting for this person, oldest first (item 2.07, the HRMS's To do): for teaching staff the
 * work to mark, observations to release and logbook entries to sign off; for course administrators the
 * takedown requests; for administrators and the Data Protection Officer corrections and disposals to
 * approve; for students the work due and logbook entries returned to them. Each opens where it is done.
 */
export function ToDoScreen({ onNavigate }: { onNavigate: (to: string) => void }) {
  const [items, setItems] = useState<WaitingItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<WaitingItem[]>("/to-do/")
      .then(setItems)
      .catch((err) => setError(errorMessage(err, "Could not load what is waiting for you.")));
  }, []);

  const waiting = items?.length ?? 0;
  const late = items?.filter((item) => item.overdue).length ?? 0;

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>To do</h1>
          {items !== null && (
            <p className="muted lead">
              {waiting === 0
                ? "Nothing is waiting for you."
                : `${waiting} ${waiting === 1 ? "thing waits" : "things wait"} for you, oldest first${late ? `; ${late} overdue` : ""}.`}
            </p>
          )}
        </div>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {items === null && !error && <p className="loading">Loading…</p>}
      {items !== null && items.length === 0 && (
        <section className="panel-card padded">
          <h2>Nothing is waiting for you</h2>
          <p className="muted">When something needs you, such as work to hand in or to mark, it appears here and on Home.</p>
        </section>
      )}
      {items !== null && items.length > 0 && (
        <section className="panel-card">
          <ul className="rows" aria-label="Waiting for you">
            {items.map((item) => (
              <li key={`${item.kind}:${item.link}:${item.title}`} className={item.overdue ? "todo-item overdue-item" : "todo-item"}>
                <div className="decision-meta">
                  <span className="todo-kind">{item.kind_name}</span>{" "}
                  <span className={item.overdue ? "todo-since late" : "todo-since"}>{waited(item)}</span>{" "}
                  {item.overdue && <span className="chip chip-rejected">Overdue</span>}
                </div>
                <div className="todo-body">
                  <span className="initials" aria-hidden="true">
                    {initials(item.site_title || item.kind_name)}
                  </span>
                  <span className="strong grow">{item.title}</span>
                  <button onClick={() => onNavigate(item.link)} aria-label={`Open: ${item.title}`}>
                    Open it
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
