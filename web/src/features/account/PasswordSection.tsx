import { useState, type FormEvent } from "react";
import { ApiError, errorMessage, post } from "../../api/client";
import { PASSWORD_RULES } from "../auth/SetPasswordScreen";

/** Change the password, knowing the current one (item 1.22). The other devices are signed out; this one stays. */
export function PasswordSection({ onChanged }: { onChanged: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [problems, setProblems] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setNotice(null);
    if (next !== repeat) {
      setProblems(["The two new passwords are not the same."]);
      return;
    }
    setBusy(true);
    setProblems([]);
    try {
      const { ended } = await post<{ ended: number }>("/auth/password/change/", { current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setRepeat("");
      setNotice(
        ended === 0
          ? "Your password is changed."
          : `Your password is changed. You were signed out on ${ended === 1 ? "1 other device" : `${ended} other devices`}.`,
      );
      onChanged();
    } catch (err) {
      setProblems(
        err instanceof ApiError && err.fields
          ? Object.values(err.fields).flat()
          : [errorMessage(err, "Your password was not changed. Try again.")],
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card-block" aria-labelledby="password-heading">
      <h2 id="password-heading">Your password</h2>
      <form className="stack" onSubmit={submit}>
        <p className="muted small" id="change-rules">
          {PASSWORD_RULES} Changing it signs you out on your other devices.
        </p>
        <label>
          Current password
          <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
        </label>
        <label>
          New password
          <input
            type="password"
            autoComplete="new-password"
            aria-describedby="change-rules"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            minLength={12}
            required
          />
        </label>
        <label>
          New password again
          <input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} required />
        </label>
        {problems.length > 0 && (
          <div role="alert" className="error">
            {problems.map((problem) => (
              <p key={problem}>{problem}</p>
            ))}
          </div>
        )}
        {notice && (
          <p role="status" className="notice good">
            {notice}
          </p>
        )}
        <div className="actions">
          <button type="submit" disabled={busy}>
            Change password
          </button>
        </div>
      </form>
    </section>
  );
}
