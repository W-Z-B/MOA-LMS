import { useState, type FormEvent } from "react";
import { errorMessage, post } from "../../api/client";
import type { AlertRule, EarlyAlert } from "../../api/types-insights";
import { dmy, dmyTime } from "../../app/format";
import { Waiting } from "./shared";
import { useLoad } from "./words";

/**
 * Early alerts (item 6.05, decision D5): students a visible rule picked out, each with its evidence. Nothing is
 * decided or sent by the LMS: a person marks an alert seen, writes to the student and records it, or dismisses it
 * with the reason. Students never see these.
 */
export function AlertsView({ siteId }: { siteId: number }) {
  const [all, setAll] = useState(false);
  const alerts = useLoad<EarlyAlert[]>(`/sites/${siteId}/alerts/${all ? "?state=all" : ""}`, "Could not load the alerts.");
  const rules = useLoad<AlertRule[]>("/alert-rules/", "Could not load the rules.");
  return (
    <>
      <p className="muted">
        The rules below are checked each night. An alert is a reason to look, not a judgement: you decide what, if
        anything, to do. Students do not see alerts.
      </p>
      <label className="inline">
        <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show alerts already dealt with
      </label>
      {alerts.data ? (
        alerts.data.length === 0 ? (
          <p className="muted">{all ? "No alerts on this course." : "No alerts waiting."}</p>
        ) : (
          <ul className="rows flush alert-list" aria-label="Early alerts">
            {alerts.data.map((alert) => (
              <AlertCard key={alert.id} siteId={siteId} alert={alert} onChanged={alerts.reload} />
            ))}
          </ul>
        )
      ) : (
        <Waiting error={alerts.error} />
      )}
      <h2 id="alert-rules">The rules</h2>
      {rules.data ? (
        <ul className="plain" aria-labelledby="alert-rules">
          {rules.data.map((rule) => (
            <li key={rule.id}>
              <strong>{rule.label}:</strong> {rule.description}
              {!rule.is_active && <span className="muted"> (switched off)</span>}
            </li>
          ))}
        </ul>
      ) : (
        <Waiting error={rules.error} />
      )}
      <p className="muted small">Course administrators set the thresholds, in Admin.</p>
    </>
  );
}

type Doing = null | "write" | "record" | "dismiss";

function AlertCard({ siteId, alert, onChanged }: { siteId: number; alert: EarlyAlert; onChanged: () => void }) {
  const [doing, setDoing] = useState<Doing>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const open = alert.state === "open" || alert.state === "acknowledged";

  async function run(work: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await work();
      setDoing(null);
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "That did not go through. Check the connection and try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li>
      <div className="alert-head">
        <strong>
          {alert.student_name} ({alert.student_no})
        </strong>
        <span className="chip chip-waiting">{alert.kind_label}</span>
        <span className={alert.state === "open" ? "chip chip-submitted" : "chip"}>{alert.state_label}</span>
      </div>
      <p>{alert.summary}</p>
      <ul className="plain small evidence" aria-label={`Evidence for ${alert.student_name}`}>
        {alert.evidence.map((e, at) => (
          <li key={at}>
            {e.what}
            {e.when && <span className="muted"> · {dmy(e.when)}</span>}
          </li>
        ))}
      </ul>
      <p className="muted small">
        Raised {dmyTime(alert.raised_at)}
        {alert.handled_by_name && alert.handled_at && ` · ${alert.state_label.toLowerCase()} by ${alert.handled_by_name}, ${dmy(alert.handled_at)}`}
        {alert.note && ` · ${alert.note}`}
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {open && doing === null && (
        <div className="actions">
          {alert.state === "open" && (
            <button type="button" className="secondary" disabled={busy} onClick={() => run(() => post(`/alerts/${alert.id}/acknowledge/`))}>
              Mark as seen
            </button>
          )}
          <button type="button" onClick={() => setDoing("write")}>
            Write to the student
          </button>
          <button type="button" className="secondary" onClick={() => setDoing("record")}>
            Record what was done
          </button>
          <button type="button" className="secondary" onClick={() => setDoing("dismiss")}>
            Dismiss
          </button>
        </div>
      )}
      {doing === "write" && <WriteForm siteId={siteId} alert={alert} busy={busy} run={run} onCancel={() => setDoing(null)} />}
      {doing === "record" && (
        <NoteForm
          label="What was done"
          button="Record"
          busy={busy}
          onCancel={() => setDoing(null)}
          onSave={(note) => run(() => post(`/alerts/${alert.id}/act/`, { note }))}
        />
      )}
      {doing === "dismiss" && (
        <NoteForm
          label="Why nothing needs doing"
          button="Dismiss"
          busy={busy}
          onCancel={() => setDoing(null)}
          onSave={(reason) => run(() => post(`/alerts/${alert.id}/dismiss/`, { reason }))}
        />
      )}
    </li>
  );
}

function NoteForm({
  label,
  button,
  busy,
  onSave,
  onCancel,
}: {
  label: string;
  button: string;
  busy: boolean;
  onSave: (text: string) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState("");
  return (
    <form
      className="stack sub-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(text);
      }}
    >
      <label>
        {label}
        <textarea value={text} onChange={(e) => setText(e.target.value)} required maxLength={2000} />
      </label>
      <div className="actions">
        <button type="submit" disabled={busy || !text.trim()}>
          {button}
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** A message to the student through Messages, recorded with the alert as what was done. */
function WriteForm({
  siteId,
  alert,
  busy,
  run,
  onCancel,
}: {
  siteId: number;
  alert: EarlyAlert;
  busy: boolean;
  run: (work: () => Promise<unknown>) => Promise<void>;
  onCancel: () => void;
}) {
  const [subject, setSubject] = useState("Checking in about your course work");
  const [body, setBody] = useState("");

  function send(e: FormEvent) {
    e.preventDefault();
    run(async () => {
      const conversation = await post<{ id: number }>("/conversations/", {
        site: siteId,
        audience: "direct",
        subject,
        body,
        body_format: "text",
        recipients: [alert.student],
      });
      await post(`/alerts/${alert.id}/act/`, { note: `Wrote to the student in Messages: ${subject}`, conversation: conversation.id });
    });
  }

  return (
    <form className="stack sub-form" onSubmit={send} aria-label={`Write to ${alert.student_name}`}>
      <label>
        Subject
        <input value={subject} onChange={(e) => setSubject(e.target.value)} required maxLength={200} />
      </label>
      <label>
        Message
        <textarea value={body} onChange={(e) => setBody(e.target.value)} required />
      </label>
      <p className="muted small">It goes to the student in Messages, as any message from you. The alert itself is not mentioned.</p>
      <div className="actions">
        <button type="submit" disabled={busy || !body.trim()}>
          Send and record
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
