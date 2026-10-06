import { useEffect, useState } from "react";
import { errorMessage, get } from "../../api/client";
import type { PushState } from "../../api/types-media";
import { currentSubscription, pushSupported, PushRefused, turnOff, turnOn } from "./pushDevice";

/**
 * Push notices on this device (item 4.04), in the notification settings: turned on here, after the browser
 * asks; the kinds below then each say whether they are pushed.
 */
export default function PushSection({ onChange }: { onChange?: (on: boolean) => void }) {
  const [state, setState] = useState<PushState | null>(null);
  const [here, setHere] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<PushState>("/notifications/push/")
      .then(setState)
      .catch(() => setState(null));
    currentSubscription()
      .then((s) => setHere(Boolean(s)))
      .catch(() => setHere(false));
  }, []);

  useEffect(() => onChange?.(here), [here, onChange]);

  if (!state) return null;

  async function change(on: boolean) {
    setBusy(true);
    setError(null);
    try {
      setState(on ? await turnOn(state!) : await turnOff());
      setHere(on);
    } catch (err) {
      setError(err instanceof PushRefused ? err.message : errorMessage(err, "Could not change push notices on this device."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="module push-section" aria-labelledby="push-title">
      <h2 id="push-title">Push notices on this device</h2>
      {!state.available ? (
        <p className="muted">This LMS does not send push notices yet.</p>
      ) : !pushSupported() ? (
        <p className="muted">This browser cannot receive push notices. On an iPhone, add the LMS to the home screen first, then open it from there.</p>
      ) : (
        <>
          <p className="muted small">
            {here ? "On for this device." : "Off for this device."} Push notices say only what arrived and open the LMS when tapped; signing out turns them off here.
            {state.devices > 0 && ` Your devices with push on: ${state.devices}.`}
          </p>
          <button type="button" className={here ? "secondary" : undefined} disabled={busy} onClick={() => change(!here)}>
            {here ? "Turn push off on this device" : "Turn push on for this device"}
          </button>
        </>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
