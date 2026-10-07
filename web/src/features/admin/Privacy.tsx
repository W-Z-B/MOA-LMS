import { useState, type FormEvent } from "react";
import { patch, post } from "../../api/client";
import { hasAnyRole, type Me, type Paginated } from "../../api/types";
import { KEEPERS, MANAGERS, type CorrectionRequest, type NoticeVersion } from "../../api/types-staff";
import { dmy, dmyTime } from "../../app/format";
import { Refusal, rows, useAction, useData } from "./data";
import { Said, Section } from "./kit";

/** A draft of the notice: a new version, or the words of one not yet published. */
function DraftForm({ start, onSave, label }: { start: { title: string; body: string }; onSave: (draft: { title: string; body: string }) => Promise<string | null>; label: string }) {
  const [draft, setDraft] = useState(start);
  const action = useAction();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    action.run(() => onSave(draft));
  };
  return (
    <form className="stack sub-form" onSubmit={submit}>
      <label>
        Title
        <input required maxLength={200} value={draft.title} onChange={(e) => setDraft((prev) => ({ ...prev, title: e.target.value }))} />
      </label>
      <label>
        Text (Markdown)
        <textarea required rows={10} value={draft.body} onChange={(e) => setDraft((prev) => ({ ...prev, body: e.target.value }))} />
      </label>
      <div className="actions">
        <button type="submit" disabled={action.busy}>
          {label}
        </button>
      </div>
      <Said done={action.done} error={action.error} />
    </form>
  );
}

/**
 * The privacy notice (item 1.18): its versions, a draft written and published by an administrator or the
 * DPO. A published version never changes; everyone reads the new one at their next sign-in.
 */
export function Notices({ me }: { me: Me }) {
  const { data, error, reload } = useData<Paginated<NoticeVersion>>("/privacy/notices/", "Could not load the notices.");
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const action = useAction();
  const writes = hasAnyRole(me, KEEPERS);
  const versions = data ? [...rows(data)].sort((a, b) => b.version - a.version) : null;

  const publish = (notice: NoticeVersion) =>
    action.run(async () => {
      await post(`/privacy/notices/${notice.id}/publish/`);
      reload();
      return `Version ${notice.version} is in force. Everyone reads it at their next sign-in.`;
    });

  return (
    <Section title="Versions" intro="A published version never changes: write a new version instead.">
      <Said error={error} done={said} />
      <Said done={action.done} error={action.error} />
      {versions && (
        <ul className="rows flush" aria-label="Notice versions">
          {versions.map((notice) => (
            <li key={notice.id}>
              <div className="row-head">
                <span className="strong">
                  Version {notice.version}: {notice.title}
                </span>
                {notice.published_at ? (
                  <span className="chip chip-done">Published {dmy(notice.published_at)}</span>
                ) : (
                  <span className="chip chip-draft">Draft</span>
                )}
              </div>
              {notice.published_by && <span className="small muted">Published by {notice.published_by}</span>}
              {writes && !notice.published_at && (
                <div className="row-actions">
                  <button type="button" disabled={action.busy} onClick={() => publish(notice)} aria-label={`Publish version ${notice.version}`}>
                    Publish
                  </button>
                  <button type="button" className="secondary" onClick={() => setEditing(notice.id)} aria-label={`Edit version ${notice.version}`}>
                    Edit
                  </button>
                </div>
              )}
              {editing === notice.id && (
                <DraftForm
                  start={{ title: notice.title, body: notice.body }}
                  label="Save the draft"
                  onSave={async (draft) => {
                    await patch(`/privacy/notices/${notice.id}/`, draft);
                    setEditing(null);
                    setSaid(`Version ${notice.version} is saved.`);
                    reload();
                    return null;
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
      {writes && editing !== "new" && (
        <div className="actions">
          <button type="button" className="secondary" onClick={() => setEditing("new")}>
            Write a new version
          </button>
        </div>
      )}
      {editing === "new" && (
        <DraftForm
          start={{ title: versions?.[0]?.title ?? "", body: versions?.[0]?.body ?? "" }}
          label="Save as a draft"
          onSave={async (draft) => {
            const made = await post<NoticeVersion>("/privacy/notices/", draft);
            setEditing(null);
            setSaid(`Version ${made.version} is saved as a draft.`);
            reload();
            return null;
          }}
        />
      )}
    </Section>
  );
}

/** Answer one correction request: corrected, or not changed with the reason. */
function Answer({ request, onDone }: { request: CorrectionRequest; onDone: (message: string) => void }) {
  const [note, setNote] = useState("");
  const action = useAction();
  const decide = (outcome: "corrected" | "declined") =>
    action.run(async () => {
      if (outcome === "declined" && !note.trim()) throw new Refusal("Say why the record is not changed.");
      await post(`/privacy/corrections/${request.id}/decide/`, { outcome, note });
      onDone(`${request.person_name}: ${outcome === "corrected" ? "corrected" : "not changed"}. They are told.`);
      return null;
    });
  const id = `note-${request.id}`;
  return (
    <>
      <label htmlFor={id}>
        Answer (needed when the record is not changed)
        <textarea id={id} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <div className="row-actions">
        <button type="button" disabled={action.busy} onClick={() => decide("corrected")} aria-label={`Corrected: ${request.person_name}`}>
          Corrected
        </button>
        <button type="button" className="secondary" disabled={action.busy} onClick={() => decide("declined")} aria-label={`Not changed: ${request.person_name}`}>
          Not changed
        </button>
      </div>
      <Said error={action.error} />
    </>
  );
}

/**
 * Correction requests (item 1.18): what people asked to have corrected, oldest due first. Course
 * administrators and administrators answer them; the DPO and the auditor read them.
 */
export function Corrections({ me }: { me: Me }) {
  const [state, setState] = useState("open");
  const { data, error, reload } = useData<Paginated<CorrectionRequest>>(
    `/privacy/corrections/${state ? `?state=${state}` : ""}`,
    "Could not load the requests.",
  );
  const [said, setSaid] = useState<string | null>(null);
  const answers = hasAnyRole(me, MANAGERS);
  const list = data ? rows(data) : null;

  return (
    <Section title="Requests" intro="Names, numbers and class lists come from the HRMS and the SRMS: those are corrected there.">
      <div className="filters">
        <label>
          Show
          <select value={state} onChange={(e) => setState(e.target.value)}>
            <option value="open">Waiting for an answer</option>
            <option value="corrected">Corrected</option>
            <option value="declined">Not changed</option>
            <option value="">Every request</option>
          </select>
        </label>
      </div>
      <Said error={error} done={said} />
      {list !== null && list.length === 0 && <p className="muted">No requests here.</p>}
      {list !== null && list.length > 0 && (
        <ul className="rows flush" aria-label="Correction requests">
          {list.map((request) => (
            <li key={request.id}>
              <div className="row-head">
                <span className="strong">
                  {request.person_name} <span className="muted small">{request.person_number}</span>: {request.subject_name}
                </span>
                <span className={request.overdue ? "chip chip-overdue" : `chip chip-correction-${request.state}`}>
                  {request.state === "open" ? `Answer by ${dmy(request.due_by)}` : request.state_name}
                </span>
              </div>
              <p className="small-gap">Wrong: {request.wrong}</p>
              <p className="small-gap">Should be: {request.should_be}</p>
              <span className="small muted">Asked {dmyTime(request.created_at)}</span>
              {request.decision_note && <p className="small-gap">Answer: {request.decision_note}</p>}
              {answers && request.state === "open" && !request.is_mine && (
                <Answer
                  request={request}
                  onDone={(message) => {
                    setSaid(message);
                    reload();
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
