import { useId, useState, type FormEvent } from "react";
import { post } from "../../api/client";
import { hasAnyRole, type Me, type Paginated } from "../../api/types";
import { MANAGERS, type CertificateTemplate } from "../../api/types-staff";
import { dmy } from "../../app/format";
import { rows, useAction, useData } from "../admin/data";
import { Said, Section } from "../admin/kit";

type Wording = Pick<CertificateTemplate, "name" | "heading" | "body" | "signatory_name" | "signatory_title" | "is_active">;

const HELP = "Paragraphs apart by a blank line, **bold**, and fields in double braces such as {{full_name}}, {{course}}, {{completed_on}}, {{expires_on}} or {{reference}}.";

/** The wording of a template, for a new template or the next version of one. */
function WordingForm({
  start,
  withCode,
  submitLabel,
  onSave,
  onCancel,
}: {
  start: Wording;
  withCode: boolean;
  submitLabel: string;
  onSave: (wording: Wording & { code?: string }) => Promise<string | null>;
  onCancel?: () => void;
}) {
  const [form, setForm] = useState<Wording & { code: string }>({ ...start, code: "" });
  const action = useAction();
  const helpId = useId();
  const set = (field: keyof Wording | "code") => (e: { target: { value: string } }) => setForm((prev) => ({ ...prev, [field]: e.target.value }));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const { code, ...wording } = form;
    action.run(() => onSave(withCode ? { ...wording, code } : wording));
  };
  return (
    <form className="stack sub-form" onSubmit={submit}>
      <div className="grid2">
        {withCode && (
          <label>
            Code (letters, numbers and dashes)
            <input required pattern="[a-z0-9-]+" maxLength={40} value={form.code} onChange={set("code")} />
          </label>
        )}
        <label>
          Name
          <input required maxLength={120} value={form.name} onChange={set("name")} />
        </label>
        <label className="span2">
          Heading
          <input maxLength={160} value={form.heading} onChange={set("heading")} />
        </label>
        <label className="span2">
          Wording
          <textarea required rows={6} value={form.body} onChange={set("body")} aria-describedby={helpId} />
        </label>
        <p id={helpId} className="muted small span2">
          {HELP}
        </p>
        <label>
          Signed by
          <input maxLength={120} value={form.signatory_name} onChange={set("signatory_name")} />
        </label>
        <label>
          Their title
          <input maxLength={120} value={form.signatory_title} onChange={set("signatory_title")} />
        </label>
        <label className="inline span2">
          <input type="checkbox" checked={form.is_active} onChange={(e) => setForm((prev) => ({ ...prev, is_active: e.target.checked }))} /> In use
        </label>
      </div>
      <div className="actions">
        <button type="submit" disabled={action.busy}>
          {submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="secondary" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
      <Said done={action.done} error={action.error} />
    </form>
  );
}

/**
 * Certificate templates (item 5.08): the wording of each kind of certificate. A change is saved as the
 * template's next version, so a certificate already issued keeps the wording it was issued with.
 */
export function Templates({ me }: { me: Me }) {
  const [all, setAll] = useState(false);
  const { data, error, reload } = useData<Paginated<CertificateTemplate>>(
    `/certificate-templates/${all ? "?versions=all" : ""}`,
    "Could not load the templates.",
  );
  const [editing, setEditing] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const manages = hasAnyRole(me, MANAGERS);

  return (
    <Section title="Certificate templates" intro="A change is saved as a new version; certificates already issued keep theirs.">
      <label className="inline">
        <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show every version
      </label>
      <Said error={error} done={said} />
      {data && (
        <ul className="rows flush" aria-label="Templates">
          {rows(data).map((t) => (
            <li key={t.id}>
              <div className="row-head">
                <span className="strong">
                  {t.name} <span className="muted small">{t.code}, version {t.version}</span>
                </span>
                {!t.is_active && <span className="chip chip-draft">Not in use</span>}
              </div>
              <span className="small muted">
                {t.heading} · saved {dmy(t.created_at)}
                {t.fields_used.length > 0 ? ` · uses ${t.fields_used.join(", ")}` : ""}
              </span>
              {manages && !all && editing !== t.id && (
                <div className="row-actions">
                  <button type="button" className="secondary" onClick={() => setEditing(t.id)} aria-label={`Change: ${t.name}`}>
                    Change
                  </button>
                </div>
              )}
              {editing === t.id && (
                <WordingForm
                  start={{ name: t.name, heading: t.heading, body: t.body, signatory_name: t.signatory_name, signatory_title: t.signatory_title, is_active: t.is_active }}
                  withCode={false}
                  submitLabel="Save as a new version"
                  onCancel={() => setEditing(null)}
                  onSave={async (wording) => {
                    const made = await post<CertificateTemplate>(`/certificate-templates/${t.id}/new-version/`, wording);
                    setEditing(null);
                    setSaid(`${made.name} is saved as version ${made.version}.`);
                    reload();
                    return null;
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
      {manages && !adding && (
        <div className="actions">
          <button type="button" className="secondary" onClick={() => setAdding(true)}>
            New template
          </button>
        </div>
      )}
      {adding && (
        <WordingForm
          start={{ name: "", heading: "Certificate of Completion", body: "", signatory_name: "", signatory_title: "Principal", is_active: true }}
          withCode
          submitLabel="Save the template"
          onCancel={() => setAdding(false)}
          onSave={async (wording) => {
            const made = await post<CertificateTemplate>("/certificate-templates/", wording);
            setAdding(false);
            setSaid(`${made.name} is saved.`);
            reload();
            return null;
          }}
        />
      )}
    </Section>
  );
}
