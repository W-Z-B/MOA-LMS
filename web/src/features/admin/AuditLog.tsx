import { useState, type FormEvent } from "react";
import { post } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { AuditChain, AuditEntry, Choice } from "../../api/types-staff";
import { dmyTime, plural } from "../../app/format";
import { rows, useAction, useData } from "./data";
import { Said, Section } from "./kit";

const EMPTY = { action: "", record: "", who: "", person: "", since: "", until: "", q: "" };

const shown = (value: unknown) => (value === null || value === undefined || value === "" ? "blank" : typeof value === "object" ? JSON.stringify(value) : String(value));

/** Whether the log is intact: the latest check, and a check now (item 1.17). */
function Chain() {
  const { data, error, setData } = useData<AuditChain>("/audit/chain/", "Could not load the state of the log.");
  const action = useAction();
  const check = () =>
    action.run(async () => {
      const state = await post<AuditChain>("/audit/chain/");
      setData(state);
      return state.latest_check?.intact ? `Every entry matches its fingerprint: ${plural(state.latest_check.rows, "entry", "entries")} checked.` : "The check found a break: see below.";
    });
  const last = data?.latest_check;
  return (
    <Section title="Is the log intact?" intro="Each entry carries a fingerprint of the one before it, so an entry changed or removed breaks the chain.">
      <Said error={error} />
      {data && (
        <p>
          {plural(data.entries, "entry", "entries")} in the log.{" "}
          {last ? (
            <>
              Last checked {dmyTime(last.checked_at)} by {last.checked_by}:{" "}
              <span className={last.intact ? "chip chip-intact" : "chip chip-broken"}>{last.intact ? "Intact" : "Broken"}</span>
              {!last.intact && <span className="error"> {last.detail || `From entry ${last.first_broken_id}.`}</span>}
            </>
          ) : (
            "It has not been checked yet."
          )}
        </p>
      )}
      <div className="actions">
        <button type="button" disabled={action.busy} onClick={check}>
          Check the chain now
        </button>
      </div>
      <Said done={action.done} error={action.error} />
    </Section>
  );
}

/**
 * The audit log (item 1.17): every entry, newest first, with filters, a CSV export of what matches, and the
 * check of the chain. For the auditor and administrators; exports and checks are audited too.
 */
export function AuditLog() {
  const choices = useData<{ actions: Choice[]; records: Choice[] }>("/audit/choices/");
  const [form, setForm] = useState(EMPTY);
  const [filters, setFilters] = useState(EMPTY);
  const [page, setPage] = useState(1);
  const query = new URLSearchParams(Object.entries(filters).filter(([, v]) => v)).toString();
  const { data, error } = useData<Paginated<AuditEntry>>(
    `/audit/?${query}${query ? "&" : ""}page=${page}`,
    "Could not load the audit log.",
  );
  const set = (field: keyof typeof EMPTY) => (e: { target: { value: string } }) => setForm({ ...form, [field]: e.target.value });
  const apply = (e: FormEvent) => {
    e.preventDefault();
    setPage(1);
    setFilters(form);
  };

  return (
    <>
      <Chain />
      <Section title="Entries">
        <form className="stack" onSubmit={apply} aria-label="Filter the audit log">
          <div className="grid2">
            <label>
              What was done
              <select value={form.action} onChange={set("action")}>
                <option value="">Anything</option>
                {(choices.data?.actions ?? []).map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Kind of record
              <select value={form.record} onChange={set("record")}>
                <option value="">Any</option>
                {(choices.data?.records ?? []).map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Who did it (name or username)
              <input value={form.who} onChange={set("who")} />
            </label>
            <label>
              About the person (employee or student number)
              <input value={form.person} onChange={set("person")} />
            </label>
            <label>
              From
              <input type="date" value={form.since} onChange={set("since")} />
            </label>
            <label>
              To
              <input type="date" value={form.until} onChange={set("until")} />
            </label>
            <label className="span2">
              Words in the reason given
              <input value={form.q} onChange={set("q")} />
            </label>
          </div>
          <div className="actions">
            <button type="submit">Show the entries</button>
            <a className="button" href={`/api/v1/audit/export/${query ? `?${query}` : ""}`}>
              Export to a spreadsheet (CSV)
            </a>
          </div>
        </form>
        <Said error={error} />
        {data && <p className="muted">{plural(data.count, "entry matches", "entries match")}.</p>}
        {data && (
          <ul className="rows flush" aria-label="Audit entries">
            {rows(data).map((entry) => (
              <li key={entry.id}>
                <div className="row-head">
                  <span className="strong">
                    {entry.action_name}: {entry.record}
                    {entry.entity_id !== null ? ` ${entry.entity_id}` : ""}
                  </span>
                  <span className="small muted">
                    {dmyTime(entry.at)} · entry {entry.id}
                  </span>
                </div>
                <span className="small muted">
                  {entry.actor}
                  {entry.person_number ? ` · about ${entry.person_number}` : ""}
                  {entry.source_ip ? ` · from ${entry.source_ip}` : ""}
                </span>
                {entry.reason && <p className="small-gap">Reason: {entry.reason}</p>}
                {entry.changes.length > 0 && (
                  <ul className="small">
                    {entry.changes.map((c) => (
                      <li key={c.field}>
                        {c.field}: {shown(c.before)} → {shown(c.after)}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
        {data && (data.previous || data.next) && (
          <div className="actions">
            <button type="button" className="secondary" disabled={!data.previous} onClick={() => setPage(page - 1)}>
              Newer entries
            </button>
            <button type="button" className="secondary" disabled={!data.next} onClick={() => setPage(page + 1)}>
              Older entries
            </button>
          </div>
        )}
      </Section>
    </>
  );
}
