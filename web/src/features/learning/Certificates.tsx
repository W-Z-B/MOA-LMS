import { useState, type FormEvent } from "react";
import { post } from "../../api/client";
import { hasAnyRole, type Me, type Paginated } from "../../api/types";
import { OVERSEERS, type Certificate } from "../../api/types-staff";
import { dmy } from "../../app/format";
import { rows, useAction, useData } from "../admin/data";
import { Said, Section } from "../admin/kit";

const STATUS: Record<Certificate["status"], string> = { valid: "Valid", expired: "Past its date", withdrawn: "Withdrawn" };

/** Withdraw a certificate issued in error, saying why (item 5.11): course administrators only. */
function Withdraw({ certificate, onDone }: { certificate: Certificate; onDone: (message: string) => void }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const action = useAction();
  if (!open)
    return (
      <button type="button" className="secondary danger-text" onClick={() => setOpen(true)} aria-label={`Withdraw ${certificate.reference}`}>
        Withdraw
      </button>
    );
  const submit = (e: FormEvent) => {
    e.preventDefault();
    action.run(async () => {
      await post(`/certificates/${certificate.id}/withdraw/`, { reason });
      onDone(`${certificate.reference} is withdrawn. The public check now says so.`);
      return null;
    });
  };
  return (
    <form className="stack grow" onSubmit={submit}>
      <label>
        Why it was issued in error
        <textarea required maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <div className="actions">
        <button type="submit" className="danger" disabled={action.busy}>
          Withdraw {certificate.reference}
        </button>
        <button type="button" className="secondary" onClick={() => setOpen(false)}>
          Keep it
        </button>
      </div>
      <Said error={action.error} />
    </form>
  );
}

/**
 * Certificates (items 5.08 to 5.11): my own, each to download; course administrators and the auditor see
 * every certificate, and a course administrator withdraws one issued in error.
 */
export function Certificates({ me }: { me: Me }) {
  const { data, error, reload } = useData<Paginated<Certificate>>("/certificates/", "Could not load the certificates.");
  const [said, setSaid] = useState<string | null>(null);
  const everyone = hasAnyRole(me, OVERSEERS);
  const withdraws = hasAnyRole(me, ["course_admin"]);
  const list = data ? rows(data) : null;

  return (
    <Section
      title={everyone ? "Certificates issued" : "My certificates"}
      intro={
        <>
          Each certificate has a reference and a code printed at its foot. Anyone you show it to can check it is genuine at{" "}
          <a href="/api/check-certificate/">the certificate check page</a>.
        </>
      }
    >
      <Said error={error} done={said} />
      {list === null && !error && <p className="loading">Loading…</p>}
      {list !== null && list.length === 0 && <p className="muted">No certificates yet. You earn one when you complete a course.</p>}
      {list !== null && list.length > 0 && (
        <ul className="rows flush" aria-label="Certificates">
          {list.map((c) => (
            <li key={c.id}>
              <div className="row-head">
                <span className="strong">{c.course}</span>
                <span className={`chip chip-${c.status}`}>{STATUS[c.status]}</span>
              </div>
              <span className="small muted">
                {[everyone ? c.holder : "", c.reference, `completed ${dmy(c.completed_on)}`, c.expires_on ? `valid until ${dmy(c.expires_on)}` : ""]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
              {c.withdrawal_reason && <p className="small-gap">Withdrawn: {c.withdrawal_reason}</p>}
              <div className="row-actions">
                {c.status !== "withdrawn" && (
                  <a className="button" href={`/api/v1/certificates/${c.id}/download/`} aria-label={`Download (PDF): ${c.reference}`}>
                    Download (PDF)
                  </a>
                )}
                {c.badge_url && (
                  <a className="button secondary" href={c.badge_url} aria-label={`Download the digital badge: ${c.reference}`}>
                    Digital badge (for a wallet)
                  </a>
                )}
                {withdraws && c.status !== "withdrawn" && (
                  <Withdraw
                    certificate={c}
                    onDone={(message) => {
                      setSaid(message);
                      reload();
                    }}
                  />
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
