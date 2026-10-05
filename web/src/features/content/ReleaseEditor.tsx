import { useState, type FormEvent } from "react";
import { errorMessage, patch } from "../../api/client";
import type { CourseModule, Item, Released, SiteGroup } from "../../api/types-content";
import { fromLocalInput, toLocalInput } from "./dates";

interface Props {
  /** What the conditions are for: a module or an item of the course. */
  target: { kind: "module"; record: CourseModule } | { kind: "item"; record: Item };
  modules: CourseModule[];
  groups: SiteGroup[];
  onSaved: () => void;
  onClose: () => void;
}

/**
 * Release conditions (item 2.16): shown from a date, once another item is complete, to some groups only.
 * After saving, the server's sentence for the conditions is shown, as students' access is decided by it.
 */
export function ReleaseEditor({ target, modules, groups, onSaved, onClose }: Props) {
  const record: Released & { id: number; title: string } = target.record;
  const [from, setFrom] = useState(toLocalInput(record.available_from));
  const [requires, setRequires] = useState<string>(record.requires_item ? String(record.requires_item) : "");
  const [chosen, setChosen] = useState<number[]>(record.groups);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // An item cannot wait for itself, and a module cannot wait for one of its own items.
  const choices = modules
    .map((m) => ({
      module: m,
      items: m.items.filter((i) => (target.kind === "item" ? i.id !== record.id : m.id !== record.id)),
    }))
    .filter((m) => m.items.length > 0);

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const path = target.kind === "module" ? `/modules/${record.id}/` : `/content/${record.id}/`;
      const after = await patch<Released>(path, {
        available_from: fromLocalInput(from),
        requires_item: requires ? Number(requires) : null,
        groups: chosen,
      });
      setSaved(after.conditions ?? "No conditions: every student sees it once it is published.");
      onSaved();
    } catch (err) {
      setError(errorMessage(err, "Could not save the conditions."));
    } finally {
      setSaving(false);
    }
  }

  const id = `${target.kind}-${record.id}`;
  return (
    <form className="stack sub-form release-editor" onSubmit={save} aria-label={`When students see “${record.title}”`}>
      <h4>When students see “{record.title}”</h4>
      <label>
        Shown from (leave empty to show it straight away)
        <input id={`release-from-${id}`} type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} />
      </label>
      <label>
        Only once this item is complete
        <select id={`release-after-${id}`} value={requires} onChange={(e) => setRequires(e.target.value)}>
          <option value="">No item needs to be complete first</option>
          {choices.map(({ module, items }) => (
            <optgroup key={module.id} label={module.title}>
              {items.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.title}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>
      <fieldset>
        <legend>Only to these groups</legend>
        {groups.length === 0 && <p className="muted small">This course has no groups, so everyone in the class sees it.</p>}
        {groups.map((g) => (
          <label key={g.id} className="inline">
            <input
              type="checkbox"
              checked={chosen.includes(g.id)}
              onChange={(e) => setChosen(e.target.checked ? [...chosen, g.id] : chosen.filter((x) => x !== g.id))}
            />{" "}
            {g.name}
          </label>
        ))}
      </fieldset>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {saved && (
        <p role="status" className="notice">
          Saved. {saved}
        </p>
      )}
      <div className="actions">
        <button type="button" className="secondary" onClick={onClose}>
          Close
        </button>
        <button type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save conditions"}
        </button>
      </div>
    </form>
  );
}
