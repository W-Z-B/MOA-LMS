import { useState, type FormEvent } from "react";
import { patch, post } from "../../api/client";
import { hasAnyRole, type Me, type Paginated } from "../../api/types";
import { MANAGERS, type CatalogueCourse, type RequiredTraining as Rule, type TrainingAssignment } from "../../api/types-staff";
import { dmy } from "../../app/format";
import { rows, useAction, useData } from "../admin/data";
import { Said, Section } from "../admin/kit";

const EMPTY = { site: "", campus_code: "", unit_code: "", post_title: "", due_days: "30", renewal_months: "", notes: "" };

/** A new requirement: the course, whom it applies to, and how long they have. */
function NewRule({ onMade }: { onMade: (message: string) => void }) {
  const courses = useData<Paginated<CatalogueCourse>>("/staff-development/catalogue/");
  const [form, setForm] = useState(EMPTY);
  const action = useAction();
  const set = (field: keyof typeof EMPTY) => (e: { target: { value: string } }) => setForm({ ...form, [field]: e.target.value });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    action.run(async () => {
      const made = await post<Rule>("/staff-development/required/", {
        ...form,
        site: Number(form.site),
        due_days: Number(form.due_days),
        renewal_months: form.renewal_months ? Number(form.renewal_months) : null,
      });
      setForm(EMPTY);
      onMade(`${made.site_title} is required of ${made.applies_to}: ${made.assigned} assigned.`);
      return null;
    });
  };

  return (
    <form className="stack sub-form" onSubmit={submit}>
      <h3>Require a course</h3>
      <div className="grid2">
        <label className="span2">
          Course
          <select required value={form.site} onChange={set("site")}>
            <option value="">Choose a course</option>
            {(courses.data ? rows(courses.data) : []).map((c) => (
              <option key={c.site} value={c.site}>
                {c.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Campus code (empty: every campus)
          <input value={form.campus_code} maxLength={10} onChange={set("campus_code")} />
        </label>
        <label>
          Unit code (empty: every unit)
          <input value={form.unit_code} maxLength={20} onChange={set("unit_code")} />
        </label>
        <label>
          Post (empty: every post)
          <input value={form.post_title} maxLength={160} onChange={set("post_title")} />
        </label>
        <label>
          Days to complete it
          <input type="number" min={1} required value={form.due_days} onChange={set("due_days")} />
        </label>
        <label>
          Taken again every (months; empty: once)
          <input type="number" min={1} value={form.renewal_months} onChange={set("renewal_months")} />
        </label>
        <label className="span2">
          Notes
          <textarea value={form.notes} onChange={set("notes")} />
        </label>
      </div>
      <div className="actions">
        <button type="submit" disabled={action.busy}>
          Require it
        </button>
      </div>
      <Said error={action.error} />
    </form>
  );
}

/**
 * Required training (item 5.05): what is required of whom, assigning it now, and who is overdue. The auditor
 * reads it. Course administrators keep their own requirements here; those the HRMS keeps (decision D13) are
 * shown as such and are changed in the HRMS, not here.
 */
export function RequiredTraining({ me }: { me: Me }) {
  const rules = useData<Paginated<Rule>>("/staff-development/required/", "Could not load the requirements.");
  const [campus, setCampus] = useState("");
  const overdue = useData<Paginated<TrainingAssignment>>(
    `/staff-development/required/overdue/${campus ? `?campus_code=${encodeURIComponent(campus)}` : ""}`,
    "Could not load the overdue report.",
  );
  const action = useAction();
  const manages = hasAnyRole(me, MANAGERS);

  const assign = (rule: Rule) =>
    action.run(async () => {
      const { assigned } = await post<{ assigned: number }>(`/staff-development/required/${rule.id}/assign/`);
      rules.reload();
      return assigned === 0 ? "Everyone it covers has it already." : `${rule.site_title}: assigned to ${assigned} more.`;
    });

  const toggle = (rule: Rule) =>
    action.run(async () => {
      await patch<Rule>(`/staff-development/required/${rule.id}/`, { is_active: !rule.is_active });
      rules.reload();
      overdue.reload();
      return rule.is_active ? `${rule.site_title}: no longer required.` : `${rule.site_title}: required again.`;
    });

  return (
    <>
      <Section title="Required training" intro="Courses staff must take, by campus, unit and post as the HRMS records them.">
        <Said error={rules.error} />
        <Said done={action.done} error={action.error} />
        {rules.data && rows(rules.data).length === 0 && <p className="muted">Nothing is required yet.</p>}
        {rules.data && rows(rules.data).length > 0 && (
          <ul className="rows flush" aria-label="Requirements">
            {rows(rules.data).map((rule) => (
              <li key={rule.id}>
                <div className="row-head">
                  <span className="strong">{rule.site_title}</span>
                  {!rule.is_active && <span className="chip chip-draft">Not in force</span>}
                  <span className="chip">{rule.source === "hrms" ? "From the HRMS" : "Kept in the LMS"}</span>
                </div>
                <span className="small muted">
                  For {rule.applies_to} · within {rule.due_days} days
                  {rule.renewal_months ? ` · again every ${rule.renewal_months} months` : ""} · {rule.assigned} assigned
                </span>
                {manages && !rule.editable && <span className="small muted">Kept in the HRMS: change it there.</span>}
                {manages && (rule.is_active || rule.editable) && (
                  <div className="row-actions">
                    {rule.is_active && (
                      <button type="button" className="secondary" disabled={action.busy} onClick={() => assign(rule)} aria-label={`Assign now: ${rule.site_title}`}>
                        Assign now
                      </button>
                    )}
                    {rule.editable && (
                      <button
                        type="button"
                        className="secondary"
                        disabled={action.busy}
                        onClick={() => toggle(rule)}
                        aria-label={`${rule.is_active ? "Stop requiring" : "Require again"}: ${rule.site_title}`}
                      >
                        {rule.is_active ? "Stop requiring" : "Require again"}
                      </button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {manages && (
          <NewRule
            onMade={(message) => {
              rules.reload();
              overdue.reload();
              action.run(async () => message);
            }}
          />
        )}
      </Section>

      <Section title="Overdue" intro="Who has not completed required training by its due date.">
        <div className="filters">
          <label>
            Campus code
            <input value={campus} maxLength={10} onChange={(e) => setCampus(e.target.value.toUpperCase())} />
          </label>
        </div>
        <Said error={overdue.error} />
        {overdue.data && rows(overdue.data).length === 0 && <p className="muted">Nobody is overdue.</p>}
        {overdue.data && rows(overdue.data).length > 0 && (
          <ul className="rows flush" aria-label="Overdue required training">
            {rows(overdue.data).map((row) => (
              <li key={row.id}>
                <div className="row-head">
                  <span className="strong">
                    {row.person_name} <span className="muted small">{row.employee_no}</span>
                  </span>
                  <span className="chip chip-overdue">Due {dmy(row.due_on)}</span>
                </div>
                <span className="small muted">
                  {row.site_title}
                  {row.campus_code ? ` · ${row.campus_code}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}
