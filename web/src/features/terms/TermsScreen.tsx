import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post, remove } from "../../api/client";
import type { Paginated } from "../../api/types";
import { sizeInWords } from "../../api/types-content";
import { SITE_PHASE, TERM_PHASE, type MissingTerm, type Term, type TermSite } from "../../api/types-terms";
import { useCrumb } from "../../app/frame";
import { dmy, plural } from "../../app/format";
import "../content/content.css";
import "./terms.css";

interface Draft {
  id: number | null;
  srms: boolean;
  code: string;
  name: string;
  starts_on: string;
  ends_on: string;
  closes_on: string;
  grace_days: string;
}

const blank = (code = ""): Draft => ({ id: null, srms: false, code, name: "", starts_on: "", ends_on: "", closes_on: "", grace_days: "" });

const draftOf = (t: Term): Draft => ({
  id: t.id,
  srms: t.source === "srms",
  code: t.code,
  name: t.name,
  starts_on: t.starts_on,
  ends_on: t.ends_on,
  closes_on: t.closes_on,
  grace_days: t.grace_days === null ? "" : String(t.grace_days),
});

/** The sites of one term, each with its phase and, once archived, the archive to download. */
function TermSites({ term }: { term: Term }) {
  const [sites, setSites] = useState<TermSite[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    get<TermSite[]>(`/terms/${term.id}/sites/`)
      .then(setSites)
      .catch((err) => setError(errorMessage(err, "Could not read the courses of this term.")));
  }, [term.id]);
  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (sites === null) return <p className="loading">Reading the courses…</p>;
  if (sites.length === 0) return <p className="muted small">No course uses this term code.</p>;
  return (
    <ul className="plain term-sites">
      {sites.map((s) => (
        <li key={s.id}>
          <a href={`#/sites/${s.id}`}>{s.title}</a>
          <span className="muted small">
            {" "}
            {s.code} · {SITE_PHASE[s.phase]}
          </span>
          {s.archive !== null && (
            <a className="small" href={`/api/v1/site-archives/${s.archive}/download/`} download>
              Download the archive{s.archive_size !== null ? ` (${sizeInWords(s.archive_size)})` : ""}
            </a>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * The term calendar (item 7.12), for course administrators. Each term's courses take work until the end of its
 * close date and the grace after it; they are then read-only for appeals, and archived once the retention
 * schedule's period for course sites has passed. Terms from the SRMS keep its code and teaching dates.
 */
export default function TermsScreen() {
  const [terms, setTerms] = useState<Term[] | null>(null);
  const [missing, setMissing] = useState<MissingTerm[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useCrumb("Terms");

  const load = useCallback(() => {
    get<Paginated<Term>>("/terms/")
      .then((page) => setTerms(page.results))
      .catch((err) => setError(errorMessage(err, "Could not read the terms.")));
    get<MissingTerm[]>("/terms/missing/")
      .then(setMissing)
      .catch(() => setMissing([]));
  }, []);
  useEffect(load, [load]);

  const start = (next: Draft) => {
    setStatus(null);
    setError(null);
    setDraft(next);
  };

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!draft) return;
    setError(null);
    const dates = { closes_on: draft.closes_on, grace_days: draft.grace_days === "" ? null : Number(draft.grace_days) };
    const body = draft.srms ? dates : { ...dates, code: draft.code, name: draft.name, starts_on: draft.starts_on, ends_on: draft.ends_on };
    try {
      if (draft.id) await patch(`/terms/${draft.id}/`, body);
      else await post("/terms/", body);
      setStatus(`Saved the term ${draft.code}.`);
      setDraft(null);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not save the term."));
    }
  }

  async function destroy() {
    if (!draft?.id) return;
    try {
      await remove(`/terms/${draft.id}/`);
      setStatus(`Removed the term ${draft.code}.`);
      setDraft(null);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not remove the term."));
    }
  }

  const field = (name: keyof Draft, value: string) => draft && setDraft({ ...draft, [name]: value });

  return (
    <>
      <div className="page-head">
        <h1>Terms</h1>
        {!draft && (
          <button type="button" onClick={() => start(blank())}>
            Add a term
          </button>
        )}
      </div>
      <p className="muted">
        Courses take work until the end of their term's close date and the grace after it. They are then read-only, kept for
        appeals, and archived when the retention schedule says.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p role="status" className={status ? "notice good" : "sr-only"}>
        {status}
      </p>
      {!draft && missing.length > 0 && (
        <div className="notice">
          <p>These term codes have courses but no dates, so their courses never close:</p>
          <ul className="plain">
            {missing.map((m) => (
              <li key={m.term_code} className="spread">
                <span>
                  {m.term_code} ({plural(m.sites, "course", "courses")})
                </span>
                <button type="button" className="secondary" onClick={() => start(blank(m.term_code))}>
                  Add {m.term_code}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {draft && (
        <form className="stack term-form" onSubmit={save}>
          <h2>{draft.id ? `Change ${draft.code}` : "New term"}</h2>
          {draft.srms && <p className="muted small">This term comes from the SRMS: its code, name and teaching dates are set there.</p>}
          <label>
            Term code
            <input value={draft.code} onChange={(e) => field("code", e.target.value)} required disabled={draft.srms} placeholder="2026-27-S1" />
          </label>
          <label>
            Name
            <input value={draft.name} onChange={(e) => field("name", e.target.value)} required disabled={draft.srms} placeholder="Semester 1" />
          </label>
          <div className="form-row">
            <label className="grow">
              Teaching starts
              <input type="date" value={draft.starts_on} onChange={(e) => field("starts_on", e.target.value)} required disabled={draft.srms} />
            </label>
            <label className="grow">
              Teaching ends
              <input type="date" value={draft.ends_on} onChange={(e) => field("ends_on", e.target.value)} required disabled={draft.srms} />
            </label>
          </div>
          <div className="form-row">
            <label className="grow">
              Last day for work
              <input type="date" value={draft.closes_on} onChange={(e) => field("closes_on", e.target.value)} required />
            </label>
            <label className="grow">
              Days of grace (empty for the standard)
              <input type="number" min={0} inputMode="numeric" value={draft.grace_days} onChange={(e) => field("grace_days", e.target.value)} />
            </label>
          </div>
          <div className="actions">
            <button type="submit">Save the term</button>
            <button type="button" className="secondary" onClick={() => setDraft(null)}>
              Cancel
            </button>
            {draft.id && !draft.srms && (
              <button type="button" className="danger" onClick={destroy}>
                Remove the term
              </button>
            )}
          </div>
        </form>
      )}
      {!draft && terms === null && !error && <p className="loading">Reading the terms…</p>}
      {!draft && terms?.length === 0 && <p className="muted">No terms yet. Add the current term so its courses close on time.</p>}
      {!draft && (
        <ul className="plain terms">
          {terms?.map((t) => (
            <li key={t.id} className="panel-card padded">
              <div className="spread">
                <div>
                  <h2 className="item-title">
                    {t.code} {t.name} <span className="pill">{TERM_PHASE[t.phase]}</span>
                  </h2>
                  <p className="muted small">
                    Teaching {dmy(t.starts_on)} to {dmy(t.ends_on)} · last day for work {dmy(t.closes_on)}, then{" "}
                    {plural(t.grace_days_applied, "day", "days")} of grace · archived from {dmy(t.archive_due_on)} ·{" "}
                    {plural(t.site_count, "course", "courses")} · {t.source_name}
                  </p>
                </div>
                <div className="actions">
                  {t.phase !== "archived" && (
                    <button type="button" className="secondary" aria-label={`Change the term ${t.code}`} onClick={() => start(draftOf(t))}>
                      Change
                    </button>
                  )}
                  <button
                    type="button"
                    className="secondary"
                    aria-expanded={open === t.id}
                    aria-label={`${open === t.id ? "Hide" : "Show"} the courses of ${t.code}`}
                    onClick={() => setOpen(open === t.id ? null : t.id)}
                  >
                    Courses
                  </button>
                </div>
              </div>
              {open === t.id && <TermSites term={t} />}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
