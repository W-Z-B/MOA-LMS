import { useState } from "react";
import { errorMessage, patch } from "../../api/client";
import type { AlertRule } from "../../api/types-insights";
import { Waiting } from "./shared";
import { useLoad } from "./words";
import "./insights.css";

/**
 * The early-alert rules (item 6.05) for course administrators: each rule's threshold, its window and whether it
 * is used. The rules are visible to teaching staff and stated in the privacy notice; every change is audited.
 */
export default function AlertRulesSection() {
  const { data, error, reload } = useLoad<AlertRule[]>("/alert-rules/", "Could not load the rules.");
  if (!data) return <Waiting error={error} />;
  return (
    <ul className="rows flush reports" aria-label="Early-alert rules">
      {data.map((rule) => (
        <RuleRow key={rule.id} rule={rule} onSaved={reload} />
      ))}
    </ul>
  );
}

function RuleRow({ rule, onSaved }: { rule: AlertRule; onSaved: () => void }) {
  const [threshold, setThreshold] = useState(String(rule.threshold));
  const [windowDays, setWindowDays] = useState(String(rule.window_days));
  const [active, setActive] = useState(rule.is_active);
  const [said, setSaid] = useState<{ ok: boolean; text: string } | null>(null);
  const usesWindow = rule.kind !== "no_visits";
  const unit = { missed_work: "pieces of work", falling_marks: "percentage points", no_visits: "days" }[rule.kind];

  async function save() {
    setSaid(null);
    try {
      await patch(`/alert-rules/${rule.id}/`, {
        threshold: Number(threshold),
        ...(usesWindow ? { window_days: Number(windowDays) } : {}),
        is_active: active,
      });
      setSaid({ ok: true, text: "Saved." });
      onSaved();
    } catch (err) {
      setSaid({ ok: false, text: errorMessage(err, "Could not save the rule.") });
    }
  }

  return (
    <li>
      <h3>{rule.label}</h3>
      <p className="muted">Now: {rule.description}.</p>
      <form
        className="rule-form"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <label>
          Threshold ({unit})
          <input type="number" min={1} max={365} value={threshold} onChange={(e) => setThreshold(e.target.value)} required />
        </label>
        {usesWindow && (
          <label>
            Window (days)
            <input type="number" min={0} max={365} value={windowDays} onChange={(e) => setWindowDays(e.target.value)} required />
          </label>
        )}
        <label className="inline">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Used
        </label>
        <button type="submit">Save {rule.label.toLowerCase()}</button>
      </form>
      {said && (
        <p role={said.ok ? "status" : "alert"} className={said.ok ? "notice good" : "error"}>
          {said.text}
        </p>
      )}
    </li>
  );
}
