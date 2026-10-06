import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { SignInEmail } from "../../api/types-staff";
import { dmyTime } from "../../app/format";

/**
 * The sign-in email address, where links to choose a password go (item 1.10, as in the HRMS). A new one is used
 * only once the link sent to it is followed, and the old one is told, so nobody can quietly take the account.
 */
export function EmailSection() {
  const [current, setCurrent] = useState<SignInEmail | null>(null);
  const [address, setAddress] = useState("");
  const [password, setPassword] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    get<SignInEmail>("/auth/email/")
      .then(setCurrent)
      .catch((err) => setError(errorMessage(err, "Could not load your sign-in email address.")));
  }, []);
  useEffect(load, [load]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setNotice((await post<{ detail: string }>("/auth/email/change/", { email: address, password })).detail);
      setAddress("");
      setPassword("");
      load();
    } catch (err) {
      setError(errorMessage(err, "The address was not changed. Try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card-block" aria-labelledby="email-heading">
      <h2 id="email-heading">Your sign-in email address</h2>
      <form className="stack" onSubmit={submit} aria-label="Change your sign-in email">
        <p className="muted small">
          Links to choose a password are sent here. A new address is used only once you follow the link we send to it, and
          the old one is told.
        </p>
        {current && (
          <p className="wrap">
            {current.email ? <strong>{current.email}</strong> : <span className="muted">No address yet: ask the course administrator.</span>}
            {current.pending && (
              <span className="muted small">
                <br />
                Waiting for you to follow the link sent to {current.pending.new_email}, until {dmyTime(current.pending.expires_at)}.
              </span>
            )}
          </p>
        )}
        <label>
          New email address
          <input type="email" autoComplete="email" value={address} onChange={(e) => setAddress(e.target.value)} required />
        </label>
        <label>
          Your password
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="notice good">
            {notice}
          </p>
        )}
        <div className="actions">
          <button type="submit" disabled={busy}>
            Send the link
          </button>
        </div>
      </form>
    </section>
  );
}
