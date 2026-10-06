import { useState, type FormEvent } from "react";
import { ApiError, post } from "../../api/client";
import type { Me } from "../../api/types";
import { AuthFrame } from "./AuthFrame";

interface Props {
  onSignedIn: (me: Me) => void;
  /** Why the server ended the last session, if it did, or that a password was just saved. */
  notice?: string | null;
  /** The username to start with, after choosing a password from an emailed link. */
  knownUsername?: string;
  /** Opens the page that emails a link to choose a new password (item 1.22). */
  onForgot?: () => void;
}

/** Login, then the authenticator code for lecturers and administrators (with first-time enrolment). */
export function LoginScreen({ onSignedIn, notice, knownUsername = "", onForgot }: Props) {
  const [username, setUsername] = useState(knownUsername);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<"credentials" | "mfa">("credentials");
  const [provisioning, setProvisioning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitCredentials(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await post<Me>("/auth/login/", { username, password });
      if (me.mfa_required && !me.mfa_verified) {
        setStage("mfa");
        try {
          const enrol = await post<{ provisioning_uri: string }>("/auth/mfa/enrol/");
          setProvisioning(enrol.provisioning_uri);
        } catch (err) {
          if (!(err instanceof ApiError && err.code === "already_enrolled")) throw err;
        }
      } else {
        onSignedIn(me);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await post<Me>("/auth/mfa/verify/", { code }));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame>
      <form className="card" onSubmit={stage === "credentials" ? submitCredentials : submitCode}>
        <h1 className="card-eyebrow">GSA LMS</h1>
        <div className="stacked">
          <h2>{stage === "credentials" ? "Sign in" : "Authenticator code"}</h2>
          <p className="muted">
            {stage === "credentials"
              ? "Use your GSA account: staff and students alike."
              : "Open the authenticator app on your phone and type the 6-digit code it shows for GSA LMS."}
          </p>
        </div>
        {notice && stage === "credentials" && (
          <p role="status" className="notice">
            {notice}
          </p>
        )}
        {stage === "credentials" ? (
          <>
            <label>
              Username
              <input id="username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
            </label>
            <label>
              Password
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
          </>
        ) : (
          <>
            {provisioning && (
              <p className="notice">
                First sign-in with a role that needs an authenticator code: add this account to your authenticator app, then enter the
                six-digit code. <code className="wrap">{provisioning}</code>
              </p>
            )}
            <label>
              Authenticator code
              <input
                id="mfa-code"
                className="code-input"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]*"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                autoFocus
                required
              />
            </label>
          </>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <button type="submit" className="wide" disabled={busy}>
          {stage === "credentials" ? "Sign in" : "Verify"}
        </button>
        {stage === "credentials" && onForgot && (
          <button type="button" className="link accent" onClick={onForgot}>
            Forgot your password?
          </button>
        )}
      </form>
    </AuthFrame>
  );
}
