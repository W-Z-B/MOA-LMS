import { lazy, Suspense, useEffect, useState } from "react";
import { api, errorMessage, get } from "../../api/client";
import type { EmailChoice, NotificationPreference } from "../../api/types-marking";

const PushSection = lazy(() => import("../media/PushSection"));

const CHOICES: { value: EmailChoice; label: string }[] = [
  { value: "instant", label: "An email now" },
  { value: "daily", label: "In a daily summary email" },
  { value: "off", label: "No email" },
];

/**
 * Notification settings (item 2.33): for each kind of notification, an email at once, a place in the daily
 * summary, or no email, and whether it is also pushed to the installed app (item 4.04). Every notification
 * still arrives in the app.
 */
export function NotificationSettingsScreen() {
  const [rows, setRows] = useState<NotificationPreference[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    get<NotificationPreference[]>("/notifications/preferences/")
      .then(setRows)
      .catch((err) => setError(errorMessage(err, "Could not load your settings.")));
  }, []);

  async function save(row: NotificationPreference, email: EmailChoice, push: boolean) {
    setError(null);
    setSaved(null);
    try {
      const body = JSON.stringify([{ kind: row.kind, email, push }]);
      setRows(await api<NotificationPreference[]>("/notifications/preferences/", { method: "PUT", body }));
      setSaved(`Saved: ${row.label}.`);
    } catch (err) {
      setError(errorMessage(err, "Could not save the setting."));
    }
  }

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>Notification settings</h1>
          <p className="muted">Everything arrives in the app. Choose, for each kind, whether it also comes by email or as a push notice.</p>
        </div>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p role="status" className={saved ? "notice good" : "sr-only"}>
        {saved}
      </p>
      <Suspense fallback={null}>
        <PushSection />
      </Suspense>
      {rows?.map((row) => (
        <fieldset className="module" key={row.kind}>
          <legend className="strong">{row.label}</legend>
          <div className="kind-choices">
            {CHOICES.map((c) => (
              <label className="inline" key={c.value}>
                <input type="radio" name={`email-${row.kind}`} checked={row.email === c.value} onChange={() => save(row, c.value, row.push)} />
                {c.label}
              </label>
            ))}
            <label className="inline">
              <input type="checkbox" checked={row.push} onChange={(e) => save(row, row.email, e.target.checked)} />
              Also a push notice
            </label>
          </div>
        </fieldset>
      ))}
    </>
  );
}
