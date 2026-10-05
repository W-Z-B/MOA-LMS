import { useState } from "react";
import { ApiError, post } from "../../api/client";
import { AuthFrame } from "./AuthFrame";

/**
 * Opened from the link sent to a new sign-in email address (item 1.10, as in the HRMS). The change is made
 * only when the button is pressed, so a mail program that opens links to check them changes nothing.
 */
export function ConfirmEmailScreen({ token, onDone }: { token: string; onDone: () => void }) {
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      setDone((await post<{ detail: string }>("/auth/email/confirm/", { token })).detail);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <section className="card" aria-labelledby="confirm-email-heading">
        <h1 className="card-eyebrow">GSA LMS</h1>
        <h2 id="confirm-email-heading">Confirm your new sign-in email address</h2>
        {done ? (
          <p role="status" className="notice good">
            {done} Links to choose a password will come there from now on.
          </p>
        ) : (
          <>
            <p className="muted">Confirm that this address, where the link came, is to be your sign-in email address.</p>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <button type="button" className="wide" disabled={busy} onClick={confirm}>
              Confirm the new address
            </button>
          </>
        )}
        <button type="button" className="link accent" onClick={onDone}>
          Go to the GSA LMS
        </button>
      </section>
    </AuthFrame>
  );
}
