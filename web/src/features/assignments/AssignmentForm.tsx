import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import type { Paginated } from "../../api/types";
import { FILE_KINDS, type AssignmentDetail, type GradeCategory, type GroupChoice, type Rubric } from "../../api/types-marking";
import { fromLocalInput, plainMark, toLocalInput } from "./words";

interface Props {
  siteId: number;
  /** The assignment to change; a new one when absent. */
  assignment?: AssignmentDetail;
  onSaved: (saved: AssignmentDetail) => void;
  onCancel: () => void;
}

type Draft = Omit<AssignmentDetail, "id" | "site" | "accepts" | "upload_limit_mb" | "integrity_statement" | "rubric_detail" | "marks_released_at" | "my_due_at" | "my_submission" | "submissions_count">;

function draftOf(a?: AssignmentDetail): Draft {
  return {
    title: a?.title ?? "",
    instructions: a?.instructions ?? "",
    opens_at: toLocalInput(a?.opens_at),
    due_at: toLocalInput(a?.due_at),
    max_mark: a ? plainMark(a.max_mark) : "100",
    weight: a ? plainMark(a.weight) : "1",
    allow_late: a?.allow_late ?? true,
    is_published: a?.is_published ?? true,
    category: a?.category ?? null,
    allow_resubmission: a?.allow_resubmission ?? true,
    accepted_kinds: a?.accepted_kinds ?? [],
    max_files: a?.max_files ?? 5,
    requires_integrity: a?.requires_integrity ?? true,
    late_penalty: a?.late_penalty ?? "none",
    late_penalty_percent: a ? plainMark(a.late_penalty_percent) : "5",
    late_penalty_cap: a?.late_penalty_cap != null ? plainMark(a.late_penalty_cap) : "",
    is_group: a?.is_group ?? false,
    groups: a?.groups ?? [],
    rubric: a?.rubric ?? null,
    anonymous: a?.anonymous ?? false,
    moderation: a?.moderation ?? "none",
  };
}

/**
 * Setting an assignment (items 2.21, 2.22, 2.26, 2.27, 2.35, 3.09, 3.16, 3.17, 3.22): what may be handed in
 * and how often, the integrity statement, the late rule, groups, the rubric, anonymous marking and moderation.
 */
export function AssignmentForm({ siteId, assignment, onSaved, onCancel }: Props) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(assignment));
  const [categories, setCategories] = useState<GradeCategory[]>([]);
  const [rubrics, setRubrics] = useState<Rubric[]>([]);
  const [groups, setGroups] = useState<GroupChoice[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const handedIn = (assignment?.submissions_count ?? 0) > 0;
  const prefix = assignment ? `asg-${assignment.id}` : "asg-new";

  useEffect(() => {
    get<Paginated<GradeCategory>>(`/grade-categories/?site=${siteId}`)
      .then((r) => setCategories(r.results))
      .catch(() => setCategories([]));
    get<Paginated<Rubric>>(`/rubrics/?site=${siteId}`)
      .then((r) => setRubrics(r.results))
      .catch(() => setRubrics([]));
    get<GroupChoice[]>(`/sites/${siteId}/my-groups/`)
      .then(setGroups)
      .catch(() => setGroups([]));
  }, [siteId]);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const body = {
      ...draft,
      site: siteId,
      opens_at: fromLocalInput(draft.opens_at ?? ""),
      due_at: fromLocalInput(draft.due_at),
      late_penalty_percent: draft.late_penalty === "none" ? "0" : draft.late_penalty_percent,
      late_penalty_cap: draft.late_penalty === "none" || draft.late_penalty_cap === "" ? null : draft.late_penalty_cap,
      groups: draft.is_group ? draft.groups : [],
    };
    try {
      const saved = assignment
        ? await patch<AssignmentDetail>(`/assignments/${assignment.id}/`, body)
        : await post<AssignmentDetail>("/assignments/", body);
      onSaved(saved);
    } catch (err) {
      setError(errorMessage(err, "Could not save the assignment."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="stack sub-form" onSubmit={save} aria-label={assignment ? `Change ${assignment.title}` : "New assignment"}>
      <h3>{assignment ? `Change “${assignment.title}”` : "New assignment"}</h3>
      <div className="grid2">
        <label className="span2">
          Title
          <input id={`${prefix}-title`} value={draft.title} onChange={(e) => set("title", e.target.value)} required />
        </label>
        <label>
          Opens
          <input id={`${prefix}-opens`} type="datetime-local" value={draft.opens_at ?? ""} onChange={(e) => set("opens_at", e.target.value)} />
        </label>
        <label>
          Due
          <input id={`${prefix}-due`} type="datetime-local" value={draft.due_at} onChange={(e) => set("due_at", e.target.value)} required />
        </label>
        <label>
          Maximum mark
          <input id={`${prefix}-max`} type="number" min={1} step="0.5" value={draft.max_mark} onChange={(e) => set("max_mark", e.target.value)} required />
        </label>
        <label>
          Weight
          <input id={`${prefix}-weight`} type="number" min={0.1} step="0.1" value={draft.weight} onChange={(e) => set("weight", e.target.value)} required />
        </label>
        <label className="span2">
          Gradebook category
          <select id={`${prefix}-category`} value={draft.category ?? ""} onChange={(e) => set("category", e.target.value ? Number(e.target.value) : null)}>
            <option value="">Not in a category</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} (weight {plainMark(c.weight)})
              </option>
            ))}
          </select>
        </label>
        <label className="span2">
          Instructions
          <textarea id={`${prefix}-instructions`} value={draft.instructions} onChange={(e) => set("instructions", e.target.value)} />
        </label>
      </div>

      <fieldset>
        <legend>Handing in</legend>
        <div className="stack">
          <div className="kind-choices" role="group" aria-label="File kinds accepted">
            {FILE_KINDS.map(([kind, label]) => (
              <label className="inline" key={kind}>
                <input
                  type="checkbox"
                  checked={draft.accepted_kinds.includes(kind)}
                  onChange={(e) =>
                    set("accepted_kinds", e.target.checked ? [...draft.accepted_kinds, kind] : draft.accepted_kinds.filter((k) => k !== kind))
                  }
                />
                {label}
              </label>
            ))}
          </div>
          <p className="muted small">No kind ticked accepts every kind: PDF, photographs, Word, Excel and PowerPoint.</p>
          <label>
            Files in one hand-in (0 for typed answers only)
            <input id={`${prefix}-max-files`} type="number" min={0} max={20} value={draft.max_files} onChange={(e) => set("max_files", Number(e.target.value))} />
          </label>
          <label className="inline">
            <input type="checkbox" checked={draft.allow_resubmission} onChange={(e) => set("allow_resubmission", e.target.checked)} />
            Students may hand in again until the due date, while the work is not marked
          </label>
          <label className="inline">
            <input type="checkbox" checked={draft.requires_integrity} onChange={(e) => set("requires_integrity", e.target.checked)} />
            Students accept the academic integrity statement with each hand-in
          </label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Late work</legend>
        <div className="stack">
          <label className="inline">
            <input type="checkbox" checked={draft.allow_late} onChange={(e) => set("allow_late", e.target.checked)} />
            Accept work after the due date
          </label>
          {draft.allow_late && (
            <div className="grid2">
              <label>
                Late penalty
                <select id={`${prefix}-penalty`} value={draft.late_penalty} onChange={(e) => set("late_penalty", e.target.value as Draft["late_penalty"])}>
                  <option value="none">No penalty</option>
                  <option value="per_day">A percentage for each day late</option>
                  <option value="per_hour">A percentage for each hour late</option>
                </select>
              </label>
              {draft.late_penalty !== "none" && (
                <>
                  <label>
                    Percentage of the maximum taken each time
                    <input id={`${prefix}-rate`} type="number" min={0.5} max={100} step="0.5" value={draft.late_penalty_percent} onChange={(e) => set("late_penalty_percent", e.target.value)} required />
                  </label>
                  <label>
                    The most taken in all, in percent (optional)
                    <input id={`${prefix}-cap`} type="number" min={0} max={100} step="0.5" value={draft.late_penalty_cap ?? ""} onChange={(e) => set("late_penalty_cap", e.target.value)} />
                  </label>
                </>
              )}
            </div>
          )}
        </div>
      </fieldset>

      <fieldset>
        <legend>Marking</legend>
        <div className="stack">
          <label>
            Rubric or marking guide
            <select id={`${prefix}-rubric`} value={draft.rubric ?? ""} onChange={(e) => set("rubric", e.target.value ? Number(e.target.value) : null)}>
              <option value="">None: give the mark directly</option>
              {rubrics.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title}
                </option>
              ))}
            </select>
          </label>
          <p className="muted small">A rubric from the GSA library is copied to this course first, from Rubrics.</p>
          <label className="inline">
            <input type="checkbox" checked={draft.anonymous} disabled={handedIn} onChange={(e) => set("anonymous", e.target.checked)} />
            Anonymous marking: names hidden from markers until the marks are released
          </label>
          <label>
            Second marking
            <select id={`${prefix}-moderation`} value={draft.moderation} onChange={(e) => set("moderation", e.target.value as Draft["moderation"])}>
              <option value="none">None</option>
              <option value="sample">A second marker checks a sample</option>
              <option value="double">Every submission is marked twice</option>
            </select>
          </label>
          <label className="inline">
            <input type="checkbox" checked={draft.is_group} disabled={handedIn} onChange={(e) => set("is_group", e.target.checked)} />
            Group assignment: one hand-in for each group, one mark for its members
          </label>
          {handedIn && <p className="muted small">Work has been handed in, so anonymous marking and groups cannot change now.</p>}
          {draft.is_group && (
            <div className="kind-choices" role="group" aria-label="Groups that take part">
              {groups.length === 0 && <p className="muted small">This course has no groups yet.</p>}
              {groups.map((g) => (
                <label className="inline" key={g.id}>
                  <input
                    type="checkbox"
                    checked={draft.groups.includes(g.id)}
                    onChange={(e) => set("groups", e.target.checked ? [...draft.groups, g.id] : draft.groups.filter((id) => id !== g.id))}
                  />
                  {g.name}
                </label>
              ))}
              {groups.length > 0 && <p className="muted small">None ticked: every group takes part.</p>}
            </div>
          )}
        </div>
      </fieldset>

      <label className="inline">
        <input type="checkbox" checked={draft.is_published} onChange={(e) => set("is_published", e.target.checked)} />
        Published to students
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" disabled={saving}>
          {saving ? "Saving…" : assignment ? "Save changes" : "Create assignment"}
        </button>
      </div>
    </form>
  );
}
