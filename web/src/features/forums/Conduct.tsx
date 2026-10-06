import { useEffect, useState, type ReactNode } from "react";
import { useConduct } from "./conductStatement";

interface Props {
  /** "post" or "send a message": what the person is about to do. */
  doing: string;
  children: ReactNode;
  /** Bumped by the page when the server refuses for want of acceptance (a new version was published). */
  recheckKey?: number;
}

/**
 * Before anyone first posts or sends a message (item 4.09): the conduct statement in force, read and accepted.
 * A new version must be accepted again. Until then the composer is not shown.
 */
export function ConductGate({ doing, children, recheckKey = 0 }: Props) {
  const { current, error, recheck, accept } = useConduct();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (recheckKey > 0) recheck();
  }, [recheckKey, recheck]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!current) return <p className="loading">Checking the conduct statement…</p>;
  if (current.accepted) return <>{children}</>;
  if (!current.statement)
    return <p className="notice">No conduct statement is in force yet, so nobody can {doing} here. A course administrator publishes it.</p>;

  const paragraphs = current.statement.body.split(/\n\s*\n/).filter((p) => p.trim());
  return (
    <section className="conduct" aria-labelledby="conduct-title">
      <h2 id="conduct-title">Rules for forums and messages</h2>
      <p className="muted small">
        Version {current.statement.version}. Read and accept them before you {doing}.
      </p>
      <div className="conduct-body" tabIndex={0} role="region" aria-label="The rules">
        {paragraphs.map((p, at) => (
          <p key={at}>{p}</p>
        ))}
      </div>
      <button
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          await accept();
          setBusy(false);
        }}
      >
        I accept these rules
      </button>
    </section>
  );
}
