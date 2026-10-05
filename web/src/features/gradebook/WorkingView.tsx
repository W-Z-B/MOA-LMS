import { useEffect, useState } from "react";
import { errorMessage, get } from "../../api/client";
import type { Working, WorkingItem } from "../../api/types-marking";
import { dmyTime } from "../../app/format";
import { plainMark, STATE_WORDS } from "../assignments/words";
import "../marking/marking.css";

const KIND = { assignment: "Assignment", quiz: "Quiz", practical: "Practical task", forum: "Graded forum" } as const;

function stateOf(item: WorkingItem): string {
  if (item.anonymous) return "Pending (anonymous marking)";
  return STATE_WORDS[item.state];
}

function resultOf(item: WorkingItem): string | null {
  if (item.kind === "assignment" && item.final_mark != null) {
    const max = plainMark(item.max_mark);
    if (item.penalty && Number(item.penalty) > 0)
      return `${plainMark(item.raw_mark)} less a late penalty of ${plainMark(item.penalty)} = ${plainMark(item.final_mark)} out of ${max}`;
    return `${plainMark(item.final_mark)} out of ${max}`;
  }
  return item.percent != null && item.state !== "zero" ? `${item.percent}%` : null;
}

/**
 * How a coursework total was worked out (item 2.30): which items counted, which are pending, which counted as
 * zero, late penalties, extended dates and the categories with their weights. A student sees their own from
 * released marks; teaching staff see any student's (person given).
 */
export function WorkingView({ siteId, personId }: { siteId: number; personId?: number }) {
  const [working, setWorking] = useState<Working | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Working>(`/sites/${siteId}/coursework/working/${personId ? `?person=${personId}` : ""}`)
      .then(setWorking)
      .catch((err) => setError(errorMessage(err, "Could not work out the total.")));
  }, [siteId, personId]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!working) return <p className="loading">Working out the total…</p>;
  const categories = new Map(working.categories.map((c) => [c.id, c.name]));
  return (
    <section className="stack working" aria-label={`How ${personId ? `${working.name}'s` : "your"} coursework total is worked out`}>
      <p>
        <span className="muted">Coursework total{personId ? ` for ${working.name} (${working.student_no})` : ""}: </span>
        <span className="working-total">{working.coursework_percent != null ? `${working.coursework_percent}%` : "nothing counts yet"}</span>
      </p>
      <p className="muted small">
        Items marked (or missed after their due date) count; pending items do not count yet.{" "}
        {working.uses_categories
          ? "Each category's percentage is the weighted mean of its items; the total is the weighted mean of the categories."
          : "The total is the mean of the counted items, weighted by each item's weight."}
      </p>
      {working.uses_categories && (
        <ul className="plain" aria-label="Categories">
          {working.categories.map((c) => (
            <li key={c.id ?? "none"} className="spread">
              <span>
                <strong>{c.name}</strong> <span className="muted small">weight {plainMark(c.weight)}{c.drop_lowest ? `, lowest ${c.drop_lowest} dropped` : ""}</span>
              </span>
              <span>{c.counted ? `${c.percent}%` : "Nothing counted yet"}</span>
            </li>
          ))}
        </ul>
      )}
      <ul className="plain" aria-label="Items">
        {working.items.map((item) => {
          const result = resultOf(item);
          return (
            <li key={`${item.kind}-${item.id}`} className="criterion">
              <div className="spread">
                <span>
                  <strong>{item.title}</strong> <span className="muted small">{KIND[item.kind]} · weight {plainMark(item.weight)}</span>
                </span>
                <span className={item.state === "graded" ? "chip chip-approved" : item.state === "zero" ? "chip chip-rejected" : "chip"}>{stateOf(item)}</span>
              </div>
              {result && <p className="small">{result}</p>}
              {item.kind === "assignment" && item.due_at && (
                <p className="muted small">
                  Due {dmyTime(item.due_at)}
                  {item.extended ? " (extended)" : ""}
                  {item.late ? " · handed in late" : ""}
                  {working.uses_categories ? ` · ${categories.get(item.category) ?? "Not in a category"}` : ""}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
