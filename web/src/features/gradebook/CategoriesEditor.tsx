import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post, remove } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { GradeCategory } from "../../api/types-marking";
import { plainMark } from "../assignments/words";

type Row = { name: string; weight: string; drop_lowest: string };

/**
 * Gradebook categories with their weights and the rule to drop the lowest (item 2.28). Assignments, quizzes,
 * practical tasks and graded forums are placed in a category where each is set.
 */
export function CategoriesEditor({ siteId, onChanged }: { siteId: number; onChanged: () => void }) {
  const [rows, setRows] = useState<GradeCategory[]>([]);
  const [edits, setEdits] = useState<Record<number, Row>>({});
  const [draft, setDraft] = useState<Row>({ name: "", weight: "", drop_lowest: "0" });
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<GradeCategory>>(`/grade-categories/?site=${siteId}`)
      .then((r) => {
        setRows(r.results);
        setEdits(Object.fromEntries(r.results.map((c) => [c.id, { name: c.name, weight: plainMark(c.weight), drop_lowest: String(c.drop_lowest) }])));
      })
      .catch((err) => setError(errorMessage(err, "Could not load the categories.")));
  }, [siteId]);

  useEffect(load, [load]);

  async function run(work: () => Promise<unknown>, fallback: string) {
    setError(null);
    try {
      await work();
      load();
      onChanged();
    } catch (err) {
      setError(errorMessage(err, fallback));
    }
  }

  function add(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      await post("/grade-categories/", { site: siteId, ...draft, drop_lowest: Number(draft.drop_lowest), position: rows.length + 1 });
      setDraft({ name: "", weight: "", drop_lowest: "0" });
    }, "Could not add the category.");
  }

  const total = rows.reduce((sum, c) => sum + Number(c.weight), 0);

  return (
    <section className="stack sub-form" aria-label="Categories and weights">
      <h3>Categories and weights</h3>
      <p className="muted small">
        {rows.length
          ? `Weights are relative: they add up to ${plainMark(String(total))} now. Items in no category count together as one more category.`
          : "No categories: the total is the weighted mean of every item. Add categories to weight the parts of the coursework."}
      </p>
      {rows.map((c) => {
        const row = edits[c.id] ?? { name: c.name, weight: c.weight, drop_lowest: String(c.drop_lowest) };
        const put = (change: Partial<Row>) => setEdits((prev) => ({ ...prev, [c.id]: { ...(prev[c.id] ?? row), ...change } }));
        return (
          <form
            key={c.id}
            className="category-row"
            aria-label={`Category ${c.name}`}
            onSubmit={(e) => {
              e.preventDefault();
              void run(() => patch(`/grade-categories/${c.id}/`, { ...row, drop_lowest: Number(row.drop_lowest) }), "Could not save the category.");
            }}
          >
            <label className="name">
              Name
              <input value={row.name} onChange={(e) => put({ name: e.target.value })} required maxLength={80} />
            </label>
            <label>
              Weight
              <input type="number" min={0.01} step="any" value={row.weight} onChange={(e) => put({ weight: e.target.value })} required />
            </label>
            <label>
              Drop lowest
              <input type="number" min={0} max={10} value={row.drop_lowest} onChange={(e) => put({ drop_lowest: e.target.value })} />
            </label>
            <div className="actions">
              <button type="submit" className="secondary">
                Save
              </button>
              <button type="button" className="secondary danger-text" onClick={() => run(() => remove(`/grade-categories/${c.id}/`), "Could not remove the category.")}>
                Remove
              </button>
            </div>
          </form>
        );
      })}
      <form className="category-row" onSubmit={add} aria-label="New category">
        <label className="name">
          New category
          <input value={draft.name} onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))} placeholder="Practicals" required maxLength={80} />
        </label>
        <label>
          Weight
          <input type="number" min={0.01} step="any" value={draft.weight} onChange={(e) => setDraft((prev) => ({ ...prev, weight: e.target.value }))} required />
        </label>
        <label>
          Drop lowest
          <input type="number" min={0} max={10} value={draft.drop_lowest} onChange={(e) => setDraft((prev) => ({ ...prev, drop_lowest: e.target.value }))} />
        </label>
        <div className="actions">
          <button type="submit">Add</button>
        </div>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
