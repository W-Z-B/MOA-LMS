import { useState, type FormEvent } from "react";
import { get, post } from "../../api/client";
import { hasAnyRole, type Me, type Paginated } from "../../api/types";
import type { Delegation, EnrolmentRequest } from "../../api/types-staff";
import { dmy, dmyTime } from "../../app/format";
import { useFrame } from "../../app/frame";
import { Refusal, rows, useAction, useData } from "../admin/data";
import { Said, Section } from "../admin/kit";

/** One request to decide: approve it, or turn it down saying why. */
function Decide({ request, onDecided }: { request: EnrolmentRequest; onDecided: (message: string) => void }) {
  const [comment, setComment] = useState("");
  const action = useAction();
  const decide = (how: "approve" | "reject") =>
    action.run(async () => {
      if (how === "reject" && !comment.trim()) throw new Refusal("Say why the request is turned down.");
      await post(`/staff-development/requests/${request.id}/${how}/`, { comment });
      onDecided(
        how === "approve"
          ? `${request.person_name} is on ${request.site_title}.`
          : `${request.person_name}'s request to join ${request.site_title} is turned down.`,
      );
      return null;
    });
  const id = `comment-${request.id}`;
  return (
    <>
      <label htmlFor={id}>
        Comment (needed to turn it down)
        <textarea id={id} maxLength={2000} value={comment} onChange={(e) => setComment(e.target.value)} />
      </label>
      <div className="row-actions">
        <button type="button" disabled={action.busy} onClick={() => decide("approve")} aria-label={`Approve: ${request.person_name}, ${request.site_title}`}>
          Approve
        </button>
        <button
          type="button"
          className="secondary"
          disabled={action.busy}
          onClick={() => decide("reject")}
          aria-label={`Turn down: ${request.person_name}, ${request.site_title}`}
        >
          Turn down
        </button>
      </div>
      <Said error={action.error ?? null} />
    </>
  );
}

interface Colleague {
  id: number;
  name: string;
  employee_no: string;
}

/** Name a stand-in: find the colleague, then the days they decide in your place. */
function NewStandIn({ onMade }: { onMade: (message: string) => void }) {
  const [words, setWords] = useState("");
  const [found, setFound] = useState<Colleague[] | null>(null);
  const [chosen, setChosen] = useState<Colleague | null>(null);
  const [form, setForm] = useState({ starts: "", ends: "", reason: "" });
  const action = useAction();

  const find = (e: FormEvent) => {
    e.preventDefault();
    action.run(async () => {
      setFound(await get<Colleague[]>(`/approvals/colleagues/?q=${encodeURIComponent(words.trim())}`));
      return null;
    });
  };
  const save = (e: FormEvent) => {
    e.preventDefault();
    if (!chosen) return;
    action.run(async () => {
      await post("/approvals/delegations/", { delegate: chosen.id, ...form });
      onMade(`${chosen.name} stands in for you from ${dmy(form.starts)} to ${dmy(form.ends)}.`);
      setChosen(null);
      setFound(null);
      setWords("");
      setForm({ starts: "", ends: "", reason: "" });
      return null;
    });
  };

  return (
    <div className="stack">
      <h3>Name a stand-in</h3>
      {!chosen && (
        <form className="filters" role="search" onSubmit={find}>
          <label className="grow">
            Colleague's name or employee number
            <input value={words} minLength={2} required onChange={(e) => setWords(e.target.value)} />
          </label>
          <button type="submit" disabled={action.busy}>
            Find
          </button>
        </form>
      )}
      {!chosen && found !== null && found.length === 0 && <p className="muted">Nobody on the staff matches.</p>}
      {!chosen && found !== null && found.length > 0 && (
        <ul className="rows flush" aria-label="Colleagues found">
          {found.map((person) => (
            <li key={person.id} className="row-head">
              <span>
                {person.name} <span className="muted small">{person.employee_no}</span>
              </span>
              <button type="button" className="secondary" onClick={() => setChosen(person)} aria-label={`Choose ${person.name}`}>
                Choose
              </button>
            </li>
          ))}
        </ul>
      )}
      {chosen && (
        <form className="stack" onSubmit={save}>
          <p>
            Stand-in: <strong>{chosen.name}</strong>{" "}
            <button type="button" className="link accent" onClick={() => setChosen(null)}>
              Choose someone else
            </button>
          </p>
          <div className="grid2">
            <label>
              From
              <input type="date" required value={form.starts} onChange={(e) => setForm({ ...form, starts: e.target.value })} />
            </label>
            <label>
              To
              <input type="date" required value={form.ends} onChange={(e) => setForm({ ...form, ends: e.target.value })} />
            </label>
            <label className="span2">
              Why (leave, travel)
              <input value={form.reason} maxLength={200} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
            </label>
          </div>
          <div className="actions">
            <button type="submit" disabled={action.busy}>
              Name the stand-in
            </button>
          </div>
        </form>
      )}
      <Said error={action.error} />
    </div>
  );
}

/**
 * Approvals (item 5.02, the approvals engine): requests to join a course waiting for my decision, as
 * supervisor, stand-in or course administrator; and stand-ins who decide while I am away (the same list is
 * under To do).
 */
export function Approvals({ me, highlight }: { me: Me; highlight: number | null }) {
  const waiting = useData<Paginated<EnrolmentRequest>>("/staff-development/requests/?state=submitted", "Could not load the requests.");
  const standIns = useData<Paginated<Delegation>>("/approvals/delegations/", "Could not load the stand-ins.");
  const frame = useFrame();
  const [said, setSaid] = useState<string | null>(null);
  const action = useAction();
  const mayEnd = (d: Delegation) => (d.delegator === me.person_id || hasAnyRole(me, ["course_admin"])) && !d.cancelled && d.ends >= new Date().toISOString().slice(0, 10);

  const decided = (message: string) => {
    setSaid(message);
    waiting.reload();
    frame.decided();
  };
  const toDecide = waiting.data
    ? rows(waiting.data)
        .filter((r) => r.allowed_actions.includes("approve"))
        .sort((a, b) => Number(b.id === highlight) - Number(a.id === highlight))
    : null;
  const end = (d: Delegation) =>
    action.run(async () => {
      await post(`/approvals/delegations/${d.id}/end/`);
      standIns.reload();
      return `${d.delegate_name} no longer stands in for ${d.delegator_name}.`;
    });

  return (
    <>
      <Section title="Waiting for your decision" intro="Requests to join a course that need approval. They are also under To do.">
        <Said error={waiting.error} done={said} />
        {toDecide === null && !waiting.error && <p className="loading">Loading…</p>}
        {toDecide !== null && toDecide.length === 0 && <p className="muted">Nothing is waiting for your decision.</p>}
        {toDecide !== null && toDecide.length > 0 && (
          <ul className="rows flush" aria-label="Requests to decide">
            {toDecide.map((request) => (
              <li key={request.id} aria-current={request.id === highlight ? "true" : undefined}>
                <div className="row-head">
                  <span className="strong">
                    {request.person_name}: {request.site_title}
                  </span>
                  <span className="small muted">Waiting since {dmyTime(request.waiting_since ?? request.created_at)}</span>
                </div>
                <p className="small-gap">{request.reason || "No reason given."}</p>
                {request.approver_name && request.approver !== me.person_id && (
                  <p className="small muted small-gap">Sent to {request.approver_name}; you decide as their stand-in.</p>
                )}
                <Decide request={request} onDecided={decided} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Stand-ins" intro="While you are away, a colleague you name decides what is sent to you.">
        <Said error={standIns.error ?? action.error} done={action.done} />
        {standIns.data && rows(standIns.data).length === 0 && <p className="muted">No stand-ins named.</p>}
        {standIns.data && rows(standIns.data).length > 0 && (
          <ul className="rows flush" aria-label="Stand-ins">
            {rows(standIns.data).map((d) => (
              <li key={d.id}>
                <div className="row-head">
                  <span>
                    <strong>{d.delegate_name}</strong> for {d.delegator_name}
                  </span>
                  {d.cancelled ? <span className="chip">Ended</span> : d.in_force && <span className="chip chip-done">In force</span>}
                </div>
                <span className="small muted">
                  {dmy(d.starts)} to {dmy(d.ends)}
                  {d.reason ? ` · ${d.reason}` : ""}
                </span>
                {mayEnd(d) && (
                  <div className="row-actions">
                    <button type="button" className="secondary" disabled={action.busy} onClick={() => end(d)} aria-label={`End: ${d.delegate_name} for ${d.delegator_name}`}>
                      End
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {me.person_kind === "staff" && (
          <NewStandIn
            onMade={(message) => {
              setSaid(null);
              standIns.reload();
              action.run(async () => message);
            }}
          />
        )}
      </Section>
    </>
  );
}
