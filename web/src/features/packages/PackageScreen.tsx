import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import { canTeach, type Paginated, type SiteContents } from "../../api/types";
import {
  COMPLETION_WORDS,
  STANDARD_NAME,
  SUCCESS_WORDS,
  type ContentPackage,
  type Launched,
  type PackageAttempt,
  type Statement,
} from "../../api/types-packages";
import { useCrumb } from "../../app/frame";
import { dmyTime } from "../../app/format";
import { connect, scormRuntime } from "./player";
import "./packages.css";

interface Props {
  siteId: number;
  itemId: number;
}

function result(attempt: PackageAttempt): string {
  const parts = [COMPLETION_WORDS[attempt.completion], SUCCESS_WORDS[attempt.success]];
  if (attempt.score_percent !== null) parts.push(`${attempt.score_percent}%`);
  return parts.filter(Boolean).join(" · ");
}

/**
 * A SCORM package or an H5P exercise (items 5.12, 5.13): opened in a sandboxed player, in an attempt. Students
 * see their attempts and what counts; teaching staff try it in a preview, set how it counts, and see every
 * learner's attempts and the statements the package reported (item 6.09).
 */
export default function PackageScreen({ siteId, itemId }: Props) {
  const [pkg, setPkg] = useState<ContentPackage | null>(null);
  const [site, setSite] = useState<SiteContents["site"] | null>(null);
  const [launched, setLaunched] = useState<Launched | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [sco, setSco] = useState("");
  const frame = useRef<HTMLIFrameElement | null>(null);
  useCrumb(pkg?.title);

  const load = useCallback(() => {
    Promise.all([get<Paginated<ContentPackage>>(`/packages/?item=${itemId}`), get<SiteContents>(`/sites/${siteId}/contents/`)])
      .then(([found, contents]) => {
        if (found.results.length === 0) throw new Error("missing");
        setPkg(found.results[0]);
        setSite(contents.site);
      })
      .catch((err) => setError(errorMessage(err, "Could not open this package.")));
  }, [siteId, itemId]);
  useEffect(load, [load]);

  // While the player is open, the frame's SCORM calls and H5P statements are answered here.
  useEffect(() => {
    if (!launched) return;
    let stop = () => undefined as void;
    let cancelled = false;
    const saved = () => window.setTimeout(load, 300);
    const start = async () => {
      const api = launched.standard === "h5p" ? null : await scormRuntime(launched);
      if (!cancelled) stop = connect(() => frame.current, launched, api, saved);
    };
    start().catch(() => setError("The package's player could not be started. Reload the page and try again."));
    return () => {
      cancelled = true;
      stop();
    };
  }, [launched, load]);

  async function open(newAttempt: boolean) {
    if (!pkg) return;
    setError(null);
    try {
      const answer = await post<Launched>(`/packages/${pkg.id}/launch/`, { sco, new_attempt: newAttempt });
      setLaunched(answer);
      setStatus(answer.attempt.is_preview ? `Preview attempt ${answer.attempt.number}: it never counts.` : `Attempt ${answer.attempt.number}.`);
    } catch (err) {
      setError(errorMessage(err, "Could not open the package."));
    }
  }

  if (error && !pkg)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!pkg || !site) return <p className="loading">Opening the package…</p>;
  const teaching = canTeach(site.my_role);
  const latest = pkg.my_attempts[pkg.my_attempts.length - 1];
  const finished = latest && (latest.completion === "completed" || latest.success !== "unknown");
  const mayStartAgain = finished && (pkg.attempts_left === null || pkg.attempts_left > 0);

  return (
    <article className="package-view">
      <p className="back-link">
        <a href={`#/sites/${siteId}`}>Back to {site.title}</a>
      </p>
      <div className="page-head">
        <h1>{pkg.title}</h1>
      </div>
      <p className="muted">
        {STANDARD_NAME[pkg.standard]}
        {pkg.version_label && pkg.version_label !== STANDARD_NAME[pkg.standard] ? ` (${pkg.version_label})` : ""}
        {Number(pkg.weight) > 0 ? ` · counts in coursework (weight ${pkg.weight})` : " · does not count in coursework"}
        {pkg.max_attempts ? ` · ${pkg.max_attempts} attempts allowed` : ""}
      </p>
      {!pkg.is_published && <p className="notice">A draft: students do not see it until it is published.</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p role="status" className={status ? "notice" : "sr-only"}>
        {status}
      </p>
      {!launched && (
        <div className="package-start">
          {pkg.scos.length > 1 && (
            <label>
              Part
              <select value={sco} onChange={(e) => setSco(e.target.value)}>
                {pkg.scos.map((part) => (
                  <option key={part.id} value={part.id}>
                    {part.title}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="actions">
            <button type="button" onClick={() => open(false)}>
              {teaching ? "Try it (preview)" : latest && !finished ? "Continue" : latest ? "Review your last attempt" : "Start"}
            </button>
            {!teaching && mayStartAgain && (
              <button type="button" className="secondary" onClick={() => open(true)}>
                Start a new attempt
              </button>
            )}
          </div>
        </div>
      )}
      {launched && (
        <div className="player">
          <iframe
            ref={frame}
            title={`${pkg.title}: the package`}
            src={launched.play_url}
            sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals allow-downloads"
            referrerPolicy="no-referrer"
            allow="fullscreen"
          />
          <div className="actions">
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setLaunched(null);
                setStatus("The package is closed. What you did has been saved.");
                load();
              }}
            >
              Close the package
            </button>
          </div>
        </div>
      )}
      {!teaching && pkg.my_attempts.length > 0 && <MyAttempts pkg={pkg} />}
      {teaching && <Teaching pkg={pkg} onChanged={load} />}
    </article>
  );
}

function MyAttempts({ pkg }: { pkg: ContentPackage }) {
  return (
    <section className="panel-card padded" aria-labelledby="my-attempts">
      <h2 id="my-attempts">Your attempts</h2>
      <ul className="rows flush">
        {pkg.my_attempts.map((a) => (
          <li key={a.id}>
            <span className="strong">Attempt {a.number}</span> <span className="muted">{result(a)}</span>
          </li>
        ))}
      </ul>
      {Number(pkg.weight) > 0 && (
        <p className="muted small">
          {pkg.my_result.fraction === null
            ? "Nothing counts in your coursework yet."
            : `${(Number(pkg.my_result.fraction) * 100).toFixed(1)}% counts in your coursework (your best attempt).`}
        </p>
      )}
    </section>
  );
}

function Teaching({ pkg, onChanged }: { pkg: ContentPackage; onChanged: () => void }) {
  const [weight, setWeight] = useState(pkg.weight);
  const [attempts, setAttempts] = useState(String(pkg.max_attempts));
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<PackageAttempt[] | null>(null);
  const [statements, setStatements] = useState<Statement[] | null>(null);

  useEffect(() => {
    get<PackageAttempt[]>(`/packages/${pkg.id}/attempts/`)
      .then(setRows)
      .catch(() => setRows([]));
  }, [pkg]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await patch(`/packages/${pkg.id}/`, { weight, max_attempts: Number(attempts) });
      setSaved("Saved how the package counts.");
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not save."));
    }
  }

  async function showStatements() {
    try {
      const answer = await get<{ statements: Statement[] }>(`/xapi/statements/?site=${pkg.site}&related_activities=true&activity=${encodeURIComponent(pkg.activity)}`);
      setStatements(answer.statements);
    } catch (err) {
      setError(errorMessage(err, "Could not load the statements."));
    }
  }

  return (
    <>
      <section className="panel-card padded" aria-labelledby="package-counts">
        <h2 id="package-counts">How it counts</h2>
        <form className="form-row" onSubmit={save}>
          <label>
            Weight in coursework
            <input type="number" inputMode="decimal" min="0" step="0.5" value={weight} onChange={(e) => setWeight(e.target.value)} />
          </label>
          <label>
            Attempts allowed (0: no limit)
            <input type="number" inputMode="numeric" min="0" max="100" value={attempts} onChange={(e) => setAttempts(e.target.value)} />
          </label>
          <div className="actions">
            <button type="submit">Save</button>
          </div>
        </form>
        {saved && (
          <p role="status" className="notice good">
            {saved}
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
      </section>
      <section className="panel-card padded" aria-labelledby="package-results">
        <h2 id="package-results">Learners' attempts</h2>
        {rows === null && <p className="loading">Loading…</p>}
        {rows !== null && rows.length === 0 && <p className="muted">No learner has opened it yet.</p>}
        {rows !== null && rows.length > 0 && (
          <div className="package-table" tabIndex={0} role="region" aria-label="Attempts, scrolls sideways on a narrow screen">
            <table>
              <caption className="sr-only">Every learner's attempts</caption>
              <thead>
                <tr>
                  <th scope="col">Learner</th>
                  <th scope="col">Attempt</th>
                  <th scope="col">Result</th>
                  <th scope="col">Last saved</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.id}>
                    <td>
                      {a.learner} <span className="muted small">{a.student_no}</span>
                    </td>
                    <td>{a.number}</td>
                    <td>{result(a)}</td>
                    <td>{a.last_commit_at ? dmyTime(a.last_commit_at) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="actions">
          <button type="button" className="secondary" onClick={showStatements}>
            Show what the package reported
          </button>
          <a className="button secondary" href={`/api/v1/content/${pkg.item}/download/`}>
            Download the package
          </a>
        </div>
        {statements !== null && (
          <ul className="rows flush" aria-label="Statements the package reported">
            {statements.length === 0 && <li className="muted">Nothing reported yet.</li>}
            {statements.map((s) => (
              <li key={s.id}>
                <span className="strong">{s.actor.account?.name ?? "?"}</span> {s.verb.display?.["en-GB"] ?? s.verb.id.split("/").pop()}{" "}
                {s.result?.score?.scaled !== undefined ? `${Math.round(s.result.score.scaled * 100)}%` : ""}{" "}
                <span className="muted small">{dmyTime(s.stored)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
