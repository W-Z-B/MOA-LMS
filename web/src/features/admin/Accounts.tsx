import { useState, type FormEvent } from "react";
import { get, post } from "../../api/client";
import type { Campus } from "../../api/types";
import type { Invited, Uninvited } from "../../api/types-staff";
import { plural } from "../../app/format";
import { Refusal, useAction, useData } from "./data";
import { Said, Section } from "./kit";

/**
 * People to invite (item 1.22): everyone on a campus or in a term who has no account in use yet. First see how
 * many would be invited (nothing is sent), then send the invitations; each person chooses their own password.
 */
export function Accounts() {
  const campuses = useData<Campus[]>("/reference/campuses/");
  const [scope, setScope] = useState({ campus_code: "", term_code: "" });
  const [counted, setCounted] = useState<(Uninvited & { for: string }) | null>(null);
  const action = useAction();
  const query = new URLSearchParams(Object.entries(scope).filter(([, v]) => v)).toString();
  const words = [scope.campus_code && `campus ${scope.campus_code}`, scope.term_code && `term ${scope.term_code}`].filter(Boolean).join(", ");

  const count = (e: FormEvent) => {
    e.preventDefault();
    action.run(async () => {
      if (!query) throw new Refusal("Name a campus, a term, or both.");
      setCounted({ ...(await get<Uninvited>(`/auth/accounts/uninvited/?${query}`)), for: query });
      return null;
    });
  };
  const send = () =>
    action.run(async () => {
      const sent = await post<Invited>("/auth/accounts/invite/", scope);
      setCounted(null);
      const failed = sent.invited - sent.emailed;
      return `${plural(sent.invited, "invitation", "invitations")} sent for ${words}.${failed ? ` ${failed} could not be emailed: check the addresses.` : ""}`;
    });

  return (
    <Section title="People to invite" intro="Accounts are opened from the records the HRMS and the SRMS send. Each person chooses their own password from the emailed link.">
      <form className="filters" onSubmit={count}>
        <label>
          Campus
          <select value={scope.campus_code} onChange={(e) => setScope((prev) => ({ ...prev, campus_code: e.target.value }))}>
            <option value="">Any campus</option>
            {(campuses.data ?? []).map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Term code
          <input value={scope.term_code} maxLength={16} placeholder="2026-27-S1" onChange={(e) => setScope((prev) => ({ ...prev, term_code: e.target.value.trim() }))} />
        </label>
        <button type="submit" className="secondary" disabled={action.busy}>
          See who would be invited
        </button>
      </form>
      {counted && counted.for === query && (
        <div className="stack" role="status">
          <p>
            <strong>{plural(counted.count, "person", "people")}</strong> on {words} {counted.count === 1 ? "has" : "have"} not been invited yet.
            {counted.without_email > 0 && ` ${plural(counted.without_email, "record has", "records have")} no email address and cannot be invited.`}
          </p>
          {counted.count > 0 && (
            <div className="actions">
              <button type="button" disabled={action.busy} onClick={send}>
                Send {plural(counted.count, "invitation", "invitations")}
              </button>
            </div>
          )}
        </div>
      )}
      <Said done={action.done} error={action.error} />
    </Section>
  );
}
