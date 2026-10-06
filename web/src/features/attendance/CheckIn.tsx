import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import type { CheckInCode, ClassSession } from "../../api/types-talk";
import { STATUS_LABEL } from "./labels";
import "../talk.css";

/**
 * The check-in code on the lecturer's screen in the room (item 4.15): six characters, as large as the screen
 * allows, read from the back of the room. The server makes a new one each minute; the screen asks for it as
 * the minute turns, and a code stays good for its minute and the next.
 */
export function CodeScreen({ session }: { session: ClassSession }) {
  const [code, setCode] = useState<CheckInCode | null>(null);
  const [left, setLeft] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    const fetchCode = () => {
      get<CheckInCode>(`/class-sessions/${session.id}/check-in-code/`)
        .then((c) => {
          if (stopped) return;
          setCode(c);
          setError(null);
          setLeft(c.refresh_seconds);
          timer = setTimeout(fetchCode, Math.min(c.refresh_seconds, 60) * 1000);
        })
        .catch((err) => {
          if (stopped) return;
          setError(errorMessage(err, "Could not get a code. Check the connection."));
          timer = setTimeout(fetchCode, 15_000);
        });
    };
    fetchCode();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [session.id]);

  useEffect(() => {
    const tick = setInterval(() => setLeft((s) => Math.max(s - 1, 0)), 1000);
    return () => clearInterval(tick);
  }, []);

  return (
    <section className="code-screen" aria-labelledby="code-title">
      <h2 id="code-title">Check in to {session.title}</h2>
      <p className="code-how">
        On your phone: GSA LMS, this course, <strong>Classes</strong>, <strong>Check in</strong>, and type
      </p>
      {code && (
        <p className="check-code">
          <span aria-hidden="true" data-code>
            {code.short_code}
          </span>
          <span className="sr-only">Code: {code.short_code.split("").join(" ")}</span>
        </p>
      )}
      {code && (
        <p className="muted" role="timer" aria-live="off">
          A new code in {left} seconds. Each code works for two minutes.
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}

/** A student types the code from the screen to check in (item 4.15). Once per class. */
export function CheckInForm({ session, onDone }: { session: ClassSession; onDone: () => void }) {
  const [code, setCode] = useState("");
  const [done, setDone] = useState<string | null>(session.my_status);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (done)
    return (
      <p role="status" className="notice good">
        You are checked in: {STATUS_LABEL[done as keyof typeof STATUS_LABEL]?.toLowerCase() ?? done}.
      </p>
    );

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const answer = await post<{ status: string }>(`/class-sessions/${session.id}/check-in/`, { code });
      setDone(answer.status);
      setError(null);
      onDone();
    } catch (err) {
      setError(errorMessage(err, "Checking in needs a connection. Try again in a moment."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack check-in" onSubmit={submit}>
      <label>
        Code on the screen
        <input
          className="code-input"
          value={code}
          required
          maxLength={8}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          inputMode="text"
          onChange={(e) => setCode(e.target.value.toUpperCase())}
        />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button type="submit" className="wide" disabled={busy || code.trim().length < 6}>
        Check in
      </button>
    </form>
  );
}
