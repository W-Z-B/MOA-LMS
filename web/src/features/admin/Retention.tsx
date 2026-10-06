import { useState, type FormEvent } from "react";
import { patch, post } from "../../api/client";
import { hasAnyRole, type Me, type Paginated } from "../../api/types";
import { KEEPERS, type Breach, type DisposalRun, type RetentionRule } from "../../api/types-staff";
import { dmy, dmyTime, plural } from "../../app/format";
import { rows, useAction, useData } from "./data";
import { Said, Section } from "./kit";

/** One rule: its period, confirming it, and finding what is due under it. */
function RuleRow({ rule, writes, onChanged }: { rule: RetentionRule; writes: boolean; onChanged: () => void }) {
  const [months, setMonths] = useState(rule.keep_months === null ? "" : String(rule.keep_months));
  const action = useAction();
  const save = (e: FormEvent) => {
    e.preventDefault();
    action.run(async () => {
      await patch(`/privacy/retention-rules/${rule.id}/`, { keep_months: Number(months) });
      onChanged();
      return "Saved. A changed period is confirmed again.";
    });
  };
  const confirm = () =>
    action.run(async () => {
      await post(`/privacy/retention-rules/${rule.id}/confirm/`);
      onChanged();
      return "Confirmed as agreed by GSA.";
    });
  const find = () =>
    action.run(async () => {
      const found = await post<{ detail: string }>(`/privacy/retention-rules/${rule.id}/find/`);
      onChanged();
      return found.detail;
    });
  const proposes = writes && !rule.automatic && rule.action === "delete" && rule.open_run === null;
  return (
    <li>
      <div className="row-head">
        <span className="strong">{rule.name}</span>
        <span className={rule.confirmed ? "chip chip-done" : "chip chip-due"}>{rule.confirmed ? "Confirmed" : "Proposed"}</span>
      </div>
      <span className="small muted">
        {rule.keep_months === null ? "Each record's own date" : `Kept ${plural(rule.keep_months, "month", "months")}`} from {rule.counted_from} ·{" "}
        {rule.automatic ? "removed every night" : rule.action_name}
        {rule.confirmed_by_name ? ` · confirmed by ${rule.confirmed_by_name}` : ""}
      </span>
      {rule.note && <p className="small muted small-gap">{rule.note}</p>}
      {writes && (
        <div className="row-actions">
          {rule.keep_months !== null && (
            <form className="actions" onSubmit={save}>
              <label className="inline">
                Months
                <input type="number" min={1} required value={months} onChange={(e) => setMonths(e.target.value)} className="months" />
              </label>
              <button type="submit" className="secondary" disabled={action.busy} aria-label={`Save the period: ${rule.name}`}>
                Save
              </button>
            </form>
          )}
          {!rule.confirmed && (
            <button type="button" className="secondary" disabled={action.busy} onClick={confirm} aria-label={`Confirm: ${rule.name}`}>
              Confirm
            </button>
          )}
          {proposes && (
            <button type="button" disabled={action.busy} onClick={find} aria-label={`Find what is due: ${rule.name}`}>
              Find what is due
            </button>
          )}
        </div>
      )}
      <Said done={action.done} error={action.error} />
    </li>
  );
}

/** A proposed disposal: keep a record (a legal hold), approve it as the second person, or cancel it. */
function RunRow({ run, writes, onChanged }: { run: DisposalRun; writes: boolean; onChanged: () => void }) {
  const [keeping, setKeeping] = useState<{ item: number; reason: string } | null>(null);
  const action = useAction();
  const act = (how: "approve" | "cancel") =>
    action.run(async () => {
      await post(`/privacy/disposal-runs/${run.id}/${how}/`);
      onChanged();
      return how === "approve" ? "Approved: every record not kept is destroyed, and each is recorded." : "Cancelled.";
    });
  const keep = (e: FormEvent) => {
    e.preventDefault();
    if (!keeping) return;
    action.run(async () => {
      await post(`/privacy/disposal-runs/${run.id}/keep/`, keeping);
      setKeeping(null);
      onChanged();
      return "Kept.";
    });
  };
  const open = run.state === "proposed";
  return (
    <li>
      <div className="row-head">
        <span className="strong">{run.rule_name}</span>
        <span className={open ? "chip chip-due" : "chip"}>{run.state_name}</span>
      </div>
      <span className="small muted">
        Proposed {dmyTime(run.created_at)} by {run.proposed_by ?? "the system"}
        {run.approved_by_name ? ` · approved by ${run.approved_by_name}` : ""} · {plural(run.items.length, "record", "records")}
      </span>
      <ul className="small">
        {run.items.map((item) => (
          <li key={item.id}>
            {item.description} (due since {dmy(item.due_since)})
            {item.keep_reason ? ` · kept: ${item.keep_reason}` : ""}
            {item.disposed_at ? " · destroyed" : ""}
            {writes && open && !item.keep_reason && keeping?.item !== item.id && (
              <>
                {" "}
                <button type="button" className="link accent" onClick={() => setKeeping({ item: item.id, reason: "" })} aria-label={`Keep: ${item.description}`}>
                  Keep
                </button>
              </>
            )}
            {keeping?.item === item.id && (
              <form className="actions" onSubmit={keep}>
                <label className="grow">
                  Why it is kept
                  <input required maxLength={300} value={keeping.reason} onChange={(e) => setKeeping((prev) => prev && ({ ...prev, reason: e.target.value }))} />
                </label>
                <button type="submit" className="secondary" disabled={action.busy}>
                  Keep it
                </button>
              </form>
            )}
          </li>
        ))}
      </ul>
      {writes && open && (
        <div className="row-actions">
          {run.proposed_by_me ? (
            <p className="muted small-gap">You proposed this run: a second person approves it.</p>
          ) : (
            <button type="button" className="danger" disabled={action.busy} onClick={() => act("approve")}>
              Approve the disposal
            </button>
          )}
          <button type="button" className="secondary" disabled={action.busy} onClick={() => act("cancel")}>
            Cancel the run
          </button>
        </div>
      )}
      <Said done={action.done} error={action.error} />
    </li>
  );
}

/**
 * Retention and disposal (item 1.19): how long each kind of record is kept, and disposal runs proposed by one
 * person and approved by a second. Administrators and the DPO act; the auditor reads.
 */
export function Retention({ me }: { me: Me }) {
  const rules = useData<RetentionRule[]>("/privacy/retention-rules/", "Could not load the schedule.");
  const runs = useData<Paginated<DisposalRun>>("/privacy/disposal-runs/", "Could not load the disposal runs.");
  const writes = hasAnyRole(me, KEEPERS);
  const changed = () => {
    rules.reload();
    runs.reload();
  };
  return (
    <>
      <Section title="Retention schedule" intro="The periods start as the impact assessment proposed them, until GSA confirms each.">
        <Said error={rules.error} />
        {rules.data && (
          <ul className="rows flush" aria-label="Retention rules">
            {rules.data.map((rule) => (
              <RuleRow key={rule.id} rule={rule} writes={writes} onChanged={changed} />
            ))}
          </ul>
        )}
      </Section>
      <Section title="Disposal runs">
        <Said error={runs.error} />
        {runs.data && rows(runs.data).length === 0 && <p className="muted">No disposal has been proposed.</p>}
        {runs.data && rows(runs.data).length > 0 && (
          <ul className="rows flush" aria-label="Disposal runs">
            {rows(runs.data).map((run) => (
              <RunRow key={run.id} run={run} writes={writes} onChanged={changed} />
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}

const NEW_BREACH = { discovered_at: "", happened: "", summary: "", data_affected: "", people_affected: "", minors_affected: false, risk: "medium", actions: "" };

/** Record a breach: what happened, whose data, and how serious. The administrators and the DPO are alerted at once. */
function NewBreach({ onMade }: { onMade: (message: string) => void }) {
  const [form, setForm] = useState(NEW_BREACH);
  const action = useAction();
  const set = (field: keyof typeof NEW_BREACH) => (e: { target: { value: string } }) => setForm((prev) => ({ ...prev, [field]: e.target.value }));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    action.run(async () => {
      const made = await post<Breach>("/privacy/breaches/", {
        ...form,
        discovered_at: new Date(form.discovered_at).toISOString(),
        people_affected: form.people_affected ? Number(form.people_affected) : null,
      });
      setForm(NEW_BREACH);
      onMade(`${made.reference} is recorded. The administrators and the DPO are alerted.`);
      return null;
    });
  };
  return (
    <form className="stack sub-form" onSubmit={submit}>
      <h3>Record a breach</h3>
      <div className="grid2">
        <label>
          Discovered
          <input type="datetime-local" required value={form.discovered_at} onChange={set("discovered_at")} />
        </label>
        <label>
          When it happened, if known
          <input maxLength={160} value={form.happened} onChange={set("happened")} />
        </label>
        <label className="span2">
          What happened
          <textarea required value={form.summary} onChange={set("summary")} />
        </label>
        <label className="span2">
          What personal data, and whose
          <textarea required value={form.data_affected} onChange={set("data_affected")} />
        </label>
        <label>
          How many people, if known
          <input type="number" min={0} value={form.people_affected} onChange={set("people_affected")} />
        </label>
        <label>
          Risk
          <select value={form.risk} onChange={set("risk")}>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </label>
        <label className="inline span2">
          <input type="checkbox" checked={form.minors_affected} onChange={(e) => setForm((prev) => ({ ...prev, minors_affected: e.target.checked }))} /> Students
          under 18 are among them
        </label>
        <label className="span2">
          What has been done, and what will be
          <textarea value={form.actions} onChange={set("actions")} />
        </label>
      </div>
      <div className="actions">
        <button type="submit" disabled={action.busy}>
          Record the breach
        </button>
      </div>
      <Said error={action.error} />
    </form>
  );
}

const STEPS: [keyof Breach, string][] = [
  ["contained_at", "Contained"],
  ["commissioner_told_at", "Commissioner told"],
  ["people_told_at", "People told"],
];

/** The breach register (item 1.19): each breach, its steps as they are taken, and closing it. */
export function Breaches({ me }: { me: Me }) {
  const { data, error, reload } = useData<Paginated<Breach>>("/privacy/breaches/", "Could not load the register.");
  const action = useAction();
  const writes = hasAnyRole(me, KEEPERS);
  const mark = (breach: Breach, field: keyof Breach, label: string) =>
    action.run(async () => {
      await patch(`/privacy/breaches/${breach.id}/`, { [field]: new Date().toISOString() });
      reload();
      return `${breach.reference}: ${label.toLowerCase()} now.`;
    });
  const close = (breach: Breach) =>
    action.run(async () => {
      await post(`/privacy/breaches/${breach.id}/close/`);
      reload();
      return `${breach.reference} is closed.`;
    });

  return (
    <Section title="Breaches">
      <Said error={error} />
      <Said done={action.done} error={action.error} />
      {data && rows(data).length === 0 && <p className="muted">No breach has been recorded.</p>}
      {data && rows(data).length > 0 && (
        <ul className="rows flush" aria-label="Breaches">
          {rows(data).map((breach) => (
            <li key={breach.id}>
              <div className="row-head">
                <span className="strong">
                  {breach.reference}: {breach.summary}
                </span>
                <span className={`chip chip-risk-${breach.risk}`}>{breach.closed_at ? "Closed" : `${breach.risk_name} risk`}</span>
              </div>
              <span className="small muted">
                Discovered {dmyTime(breach.discovered_at)}
                {breach.people_affected !== null ? ` · ${plural(breach.people_affected, "person", "people")}` : ""}
                {breach.minors_affected ? " · students under 18" : ""}
                {STEPS.filter(([field]) => breach[field]).map(([field, label]) => ` · ${label.toLowerCase()} ${dmy(String(breach[field]))}`)}
              </span>
              <p className="small-gap">Data: {breach.data_affected}</p>
              {breach.actions && <p className="small-gap">Done: {breach.actions}</p>}
              {writes && !breach.closed_at && (
                <div className="row-actions">
                  {STEPS.filter(([field]) => !breach[field]).map(([field, label]) => (
                    <button key={field} type="button" className="secondary" disabled={action.busy} onClick={() => mark(breach, field, label)} aria-label={`${label} now: ${breach.reference}`}>
                      {label} now
                    </button>
                  ))}
                  {breach.contained_at && (
                    <button type="button" disabled={action.busy} onClick={() => close(breach)} aria-label={`Close ${breach.reference}`}>
                      Close
                    </button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {writes && (
        <NewBreach
          onMade={(message) => {
            reload();
            action.run(async () => message);
          }}
        />
      )}
    </Section>
  );
}
