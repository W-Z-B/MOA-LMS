import { useEffect, useState, type FormEvent } from "react";
import { ApiError, post } from "../../api/client";
import type { PasswordLink } from "../../api/types-staff";
import { AuthFrame } from "./AuthFrame";

interface Props {
  uid: string;
  token: string;
  /** The password is saved: back to sign-in, with the username to sign in as. */
  onDone: (username: string) => void;
  /** The link no longer works: ask for a new one. */
  onAskAgain: () => void;
}

/** The password policy (AUTH_PASSWORD_VALIDATORS), in words. */
export const PASSWORD_RULES =
  "At least 12 characters. Not a common password, not only numbers, and not close to your name or username.";

/**
 * The page an emailed link opens (item 1.22, as in the HRMS): an invitation to a new account, or a reset. The
 * link is checked first; then the person chooses their own password, which nobody else ever sees.
 */
export function SetPasswordScreen({ uid, token, onDone, onAskAgain }: Props) {
  const [link, setLink] = useState<PasswordLink | null>(null);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [visible, setVisible] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let current = true;
    post<PasswordLink>("/auth/password/check/", { uid, token })
      .then((answer) => current && setLink(answer))
      .catch((err) => current && setInvalid(err instanceof ApiError ? err.detail : "Could not reach the server."));
    return () => {
      current = false;
    };
  }, [uid, token]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (password !== repeat) {
      setProblems(["The two passwords are not the same."]);
      return;
    }
    setBusy(true);
    setProblems([]);
    try {
      const done = await post<PasswordLink>("/auth/password/set/", { uid, token, password });
      onDone(done.username);
    } catch (err) {
      if (err instanceof ApiError && err.code === "invalid_link") setInvalid(err.detail);
      else if (err instanceof ApiError) setProblems(err.fields ? Object.values(err.fields).flat() : [err.detail]);
      else setProblems(["Could not reach the server."]);
    } finally {
      setBusy(false);
    }
  }

  const type = visible ? "text" : "password";

  return (
    <AuthFrame>
      <form className="card" onSubmit={submit} aria-labelledby="set-heading">
        <h1 className="card-eyebrow">GSA LMS</h1>
        <h2 id="set-heading">{link?.kind === "invitation" ? "Welcome: choose your password" : "Choose a new password"}</h2>
        {link === null && invalid === null && <p className="loading">Checking your link…</p>}
        {invalid !== null && (
          <>
            <p role="alert" className="error">
              {invalid}
            </p>
            <button type="button" onClick={onAskAgain}>
              Ask for a new link
            </button>
          </>
        )}
        {link !== null && invalid === null && (
          <>
            <p>
              Your username is <strong>{link.username}</strong>.
            </p>
            <p className="muted" id="password-rules">
              {PASSWORD_RULES}
            </p>
            <label>
              New password
              <input
                id="new-password"
                type={type}
                autoComplete="new-password"
                aria-describedby="password-rules"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={12}
                autoFocus
                required
              />
            </label>
            <label>
              New password again
              <input
                id="new-password-again"
                type={type}
                autoComplete="new-password"
                value={repeat}
                onChange={(e) => setRepeat(e.target.value)}
                required
              />
            </label>
            <label className="inline">
              <input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} /> Show the password
            </label>
            {problems.length > 0 && (
              <div role="alert" className="error">
                {problems.map((problem) => (
                  <p key={problem}>{problem}</p>
                ))}
              </div>
            )}
            <button type="submit" className="wide" disabled={busy}>
              Save my password
            </button>
          </>
        )}
      </form>
    </AuthFrame>
  );
}
