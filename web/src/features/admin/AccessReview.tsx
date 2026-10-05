import { useState, type FormEvent } from "react";
import { post } from "../../api/client";
import { hasAnyRole, type Me } from "../../api/types";
import { MANAGERS, type AccessReview as Review } from "../../api/types-staff";
import { dmy, dmyTime } from "../../app/format";
import { useAction, useData } from "./data";
import { Said, Section } from "./kit";

const signedIn = (at: string | null) => (at ? `last signed in ${dmy(at)}` : "never signed in");

/**
 * The access review each term (item 1.21): who holds a system role and who teaches which site. Administrators
 * and course administrators take away what is no longer needed, then sign it off; the auditor reads it.
 */
export function AccessReview({ me }: { me: Me }) {
  const { data, error, reload } = useData<Review>("/auth/access-review/", "Could not load the review.");
  const [notes, setNotes] = useState("");
  const action = useAction();
  const signs = hasAnyRole(me, MANAGERS);

  const signOff = (e: FormEvent) => {
    e.preventDefault();
    action.run(async () => {
      await post("/auth/access-review/sign-off/", { notes });
      setNotes("");
      reload();
      return "The review is signed off. The next reminder comes in a term.";
    });
  };

  if (error) return <Said error={error} />;
  if (!data) return <p className="loading">Loading…</p>;
  const last = data.last_review;

  return (
    <>
      <Section title="Last sign-off">
        <p>
          {last
            ? `Signed off ${dmyTime(last.reviewed_at)} by ${last.reviewed_by ?? "someone since gone"}: ${last.role_holders} role grants and ${last.teaching_staff} teaching places.`
            : "The review has not been signed off yet."}
        </p>
        {last?.notes && <p className="muted">{last.notes}</p>}
        {signs && (
          <form className="stack" onSubmit={signOff}>
            <label>
              What was changed or queried
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
            </label>
            <div className="actions">
              <button type="submit" disabled={action.busy}>
                Sign off the review
              </button>
            </div>
          </form>
        )}
        <Said done={action.done} error={action.error} />
      </Section>
      <Section title="Who holds a role" intro="Take away a role that is no longer needed in the Django admin before signing off.">
        <ul className="rows flush" aria-label="Role holders">
          {data.role_holders.map((holder) => (
            <li key={`${holder.username}-${holder.role}-${holder.campus_code}`}>
              <div className="row-head">
                <span className="strong">
                  {holder.name} <span className="muted small">{holder.username}</span>
                </span>
                {!holder.account_active && <span className="chip chip-overdue">Account closed</span>}
              </div>
              <span className="small muted">
                {holder.role_name}
                {holder.campus_code ? `, ${holder.campus_code}` : ""} · since {dmy(holder.given)} · {signedIn(holder.last_sign_in)}
              </span>
            </li>
          ))}
        </ul>
      </Section>
      <Section title="Who teaches which site">
        {data.teaching_staff.length === 0 && <p className="muted">Nobody teaches a site yet.</p>}
        <ul className="rows flush" aria-label="Teaching staff">
          {data.teaching_staff.map((row) => (
            <li key={`${row.site_code}-${row.employee_no}`}>
              <div className="row-head">
                <span className="strong">
                  {row.name} <span className="muted small">{row.employee_no}</span>
                </span>
                {!row.person_active && <span className="chip chip-overdue">No longer on the staff</span>}
              </div>
              <span className="small muted">
                {row.site_role}, {row.site_title} ({row.site_code}, {row.term_code}) · {signedIn(row.last_sign_in)}
              </span>
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}
