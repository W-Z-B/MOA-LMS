/**
 * Competency for teaching staff and assessors (item 3.13, decision D8): the frameworks the site follows
 * (imported by a course administrator), each student's standing unit by unit with the computed suggestion
 * and its evidence, and the result an assessor records. The system suggests; a person decides. The server
 * refuses "competent" until every critical criterion has been passed and evidence is given, and says why.
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import { ADMIN_ROLES, hasAnyRole, type Me, type Paginated } from "../../api/types";
import {
  STATUS_LABEL,
  type CompetencySheet,
  type CompetencyStatus,
  type FrameworkTree,
  type Observation,
  type SiteFramework,
  type UnitCell,
} from "../../api/types-practicals";
import { dmy } from "../../app/format";
import { practicalsPath } from "./routes";

interface Props {
  siteId: number;
  personId: number | null;
  onNavigate: (to: string) => void;
}

export function StatusChip({ status }: { status: CompetencyStatus }) {
  return <span className={`chip chip-${status}`}>{STATUS_LABEL[status]}</span>;
}

export function CompetencyScreen({ siteId, personId, onNavigate }: Props) {
  const [sheet, setSheet] = useState<CompetencySheet | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<CompetencySheet>(`/sites/${siteId}/competency/`)
      .then((s) => {
        setSheet(s);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not load the competency records.")));
  }, [siteId]);

  useEffect(load, [load]);

  const row = personId === null ? null : sheet?.rows.find((r) => r.person_id === personId);
  if (row && sheet)
    return <StudentRecord siteId={siteId} row={row} onBack={() => onNavigate(practicalsPath(siteId, "competency"))} onSaved={load} />;

  return (
    <>
      <Frameworks siteId={siteId} onChanged={load} />
      <h3>Students</h3>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {sheet && sheet.units.length === 0 && <p className="muted">Follow a framework to record competency on this course.</p>}
      {sheet && sheet.units.length > 0 && (
        <ul className="plain">
          {sheet.rows.map((r) => (
            <li key={r.person_id} className="module">
              <div className="panel-head wrap-head">
                <div>
                  <strong>{r.name}</strong> <span className="muted">{r.student_no}</span>
                </div>
                <button className="secondary small-button" onClick={() => onNavigate(practicalsPath(siteId, "competency", r.person_id))}>
                  Record for {r.name}
                </button>
              </div>
              <ul className="plain unit-lines">
                {r.units.map((u) => (
                  <li key={u.unit_id} className="spread">
                    <span>
                      {u.unit_code} {u.unit_title}
                    </span>
                    <span className="actions">
                      {u.result ? <StatusChip status={u.result.status} /> : <span className="muted small">No result</span>}
                      {u.suggested && (!u.result || u.result.status !== u.suggested) && (
                        <span className="muted small">suggests {STATUS_LABEL[u.suggested].toLowerCase()}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function StudentRecord({
  siteId,
  row,
  onBack,
  onSaved,
}: {
  siteId: number;
  row: CompetencySheet["rows"][number];
  onBack: () => void;
  onSaved: () => void;
}) {
  const [observations, setObservations] = useState<Observation[]>([]);
  useEffect(() => {
    get<Paginated<Observation>>(`/observations/?site=${siteId}&student=${row.person_id}`)
      .then((r) => setObservations(r.results))
      .catch(() => setObservations([]));
  }, [siteId, row.person_id]);

  return (
    <>
      <p>
        <button type="button" className="link accent" onClick={onBack}>
          ← All students
        </button>
      </p>
      <h2>
        {row.name} <span className="muted">{row.student_no}</span>
      </h2>
      {row.units.map((u) => (
        <UnitForm key={u.unit_id} siteId={siteId} personId={row.person_id} cell={u} observations={observations} onSaved={onSaved} />
      ))}
    </>
  );
}

function UnitForm({
  siteId,
  personId,
  cell,
  observations,
  onSaved,
}: {
  siteId: number;
  personId: number;
  cell: UnitCell;
  observations: Observation[];
  onSaved: () => void;
}) {
  const [status, setStatus] = useState<CompetencyStatus>(cell.result?.status ?? cell.suggested ?? "not_assessed");
  const [evidence, setEvidence] = useState<number[]>(cell.observations);
  const [comments, setComments] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const released = observations.filter((o) => o.is_released);
  const name = (id: number) => {
    const o = observations.find((x) => x.id === id);
    return o ? `${o.task_title}, attempt ${o.attempt} (${o.score.earned} of ${o.score.possible})` : `Observation ${id}`;
  };
  const choices = [...new Set([...cell.observations, ...released.map((o) => o.id)])];

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSaved(null);
    try {
      await post("/competency-results/", {
        site: siteId,
        student: personId,
        unit: cell.unit_id,
        status,
        comments,
        evidence_observations: evidence,
        client_recorded_at: new Date().toISOString(),
      });
      setSaved(`${STATUS_LABEL[status]} recorded for ${cell.unit_code}.`);
      onSaved();
    } catch (err) {
      // "Competent" without every critical criterion passed, or without evidence: the server says which.
      setError(errorMessage(err, "Could not record the result."));
    }
  }

  return (
    <form className="module stack" onSubmit={save} aria-label={`${cell.unit_code} ${cell.unit_title}`}>
      <div>
        <h3>
          {cell.unit_code} {cell.unit_title}
        </h3>
        <p className="muted small">
          {cell.framework}
          {cell.result && ` · recorded ${STATUS_LABEL[cell.result.status].toLowerCase()} by ${cell.result.assessor} on ${dmy(cell.result.decided_on)}`}
        </p>
      </div>
      {cell.suggested && (
        <p className="notice">
          The evidence suggests: <strong>{STATUS_LABEL[cell.suggested]}</strong>. You decide.
        </p>
      )}
      {cell.critical_criteria && cell.critical_criteria.length > 0 && (
        <div>
          <p className="strong" style={{ margin: "0 0 4px" }}>
            Critical criteria
          </p>
          <ul className="plain small">
            {cell.critical_criteria.map((c) => {
              const missing = cell.missing_critical?.some((m) => m.id === c.id);
              return (
                <li key={c.id} className={missing ? "result not-met" : "result met"}>
                  <span className="result-mark" aria-hidden="true">
                    {missing ? "✗" : "✓"}
                  </span>
                  <span>
                    <span className="sr-only">{missing ? "Still to pass: " : "Passed: "}</span>
                    {c.task}: {c.text}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      <fieldset>
        <legend>Evidence: released observations</legend>
        {choices.length === 0 && <p className="muted small">No released observation yet.</p>}
        {choices.map((id) => (
          <label key={id} className="inline check-row">
            <input
              type="checkbox"
              checked={evidence.includes(id)}
              onChange={() => setEvidence(evidence.includes(id) ? evidence.filter((x) => x !== id) : [...evidence, id])}
            />
            <span>{name(id)}</span>
          </label>
        ))}
        {cell.assignments.length > 0 && <p className="muted small">Assignments mapped to this unit: {cell.assignments.length}.</p>}
      </fieldset>
      <fieldset>
        <legend>Result</legend>
        <div className="choice-row">
          {(Object.keys(STATUS_LABEL) as CompetencyStatus[]).map((s) => (
            <label key={s} className={status === s ? "choice chosen" : "choice"}>
              <input type="radio" name={`status-${cell.unit_id}`} checked={status === s} onChange={() => setStatus(s)} />
              {STATUS_LABEL[s]}
            </label>
          ))}
        </div>
      </fieldset>
      <label>
        Comments
        <textarea value={comments} onChange={(e) => setComments(e.target.value)} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {saved && (
        <p role="status" className="notice good">
          {saved}
        </p>
      )}
      <div className="actions">
        <button type="submit">Record {cell.unit_code}</button>
      </div>
    </form>
  );
}

/** The frameworks the site follows; following another; importing one (course administrators). */
function Frameworks({ siteId, onChanged }: { siteId: number; onChanged: () => void }) {
  const [followed, setFollowed] = useState<SiteFramework[]>([]);
  const [all, setAll] = useState<FrameworkTree[]>([]);
  const [chosen, setChosen] = useState("");
  const [canImport, setCanImport] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<SiteFramework>>(`/site-frameworks/?site=${siteId}`)
      .then((r) => setFollowed(r.results))
      .catch((err) => setError(errorMessage(err, "Could not load the frameworks.")));
    get<Paginated<FrameworkTree>>("/competency-frameworks/")
      .then((r) => setAll(r.results))
      .catch(() => setAll([]));
  }, [siteId]);

  useEffect(load, [load]);
  useEffect(() => {
    get<Me>("/auth/me/")
      .then((me) => setCanImport(hasAnyRole(me, ADMIN_ROLES)))
      .catch(() => setCanImport(false));
  }, []);

  async function follow(e: FormEvent) {
    e.preventDefault();
    try {
      await post("/site-frameworks/", { site: siteId, framework: Number(chosen) });
      setChosen("");
      setError(null);
      load();
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not follow the framework."));
    }
  }

  const open = all.filter((f) => f.is_active && !followed.some((s) => s.framework === f.id));

  return (
    <section className="module" aria-labelledby="frameworks-heading">
      <h3 id="frameworks-heading">Competency frameworks</h3>
      {followed.length === 0 ? (
        <p className="muted">This course follows no framework yet.</p>
      ) : (
        <ul className="plain">
          {followed.map((f) => (
            <li key={f.id}>{f.framework_title}</li>
          ))}
        </ul>
      )}
      {open.length > 0 && (
        <form className="form-row" onSubmit={follow} style={{ marginTop: 12 }}>
          <label className="grow">
            Follow a framework
            <select value={chosen} onChange={(e) => setChosen(e.target.value)} required>
              <option value="" disabled>
                Choose…
              </option>
              {open.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.code} v{f.version} {f.title}
                </option>
              ))}
            </select>
          </label>
          <div className="actions">
            <button type="submit">Follow</button>
          </div>
        </form>
      )}
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
      {canImport && (
        <ImportFramework
          onImported={(f) => {
            setNotice(`Imported ${f.code} v${f.version} ${f.title}.`);
            load();
          }}
        />
      )}
    </section>
  );
}

function ImportFramework({ onImported }: { onImported: (framework: FrameworkTree) => void }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({ code: "", title: "", source: "Council for TVET occupational standard", version: "1" });
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Choose the CSV file of the framework.");
      return;
    }
    const form = new FormData();
    Object.entries(draft).forEach(([k, v]) => form.set(k, v));
    form.set("csv", file);
    try {
      const framework = await post<FrameworkTree>("/competency-frameworks/import/", form);
      setOpen(false);
      setFile(null);
      setError(null);
      onImported(framework);
    } catch (err) {
      setError(errorMessage(err, "Could not import the framework."));
    }
  }

  if (!open)
    return (
      <p>
        <button className="secondary" onClick={() => setOpen(true)}>
          Import a framework
        </button>
      </p>
    );
  return (
    <form className="stack sub-form" onSubmit={send}>
      <h3>Import a framework</h3>
      <p className="muted small">
        A CSV file saved as UTF-8 with one row per performance criterion and these columns: unit_code, unit_title, element_code,
        element_title, criterion_code, criterion_text.
      </p>
      <div className="grid2">
        <label>
          Code
          <input value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} required maxLength={40} placeholder="AGR-CROP-L2" />
        </label>
        <label>
          Version
          <input value={draft.version} onChange={(e) => setDraft({ ...draft, version: e.target.value })} required maxLength={20} />
        </label>
        <label className="span2">
          Title
          <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} required maxLength={200} />
        </label>
        <label className="span2">
          Published by
          <input value={draft.source} onChange={(e) => setDraft({ ...draft, source: e.target.value })} maxLength={200} />
        </label>
        <label className="span2">
          CSV file
          <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="button" className="secondary" onClick={() => setOpen(false)}>
          Cancel
        </button>
        <button type="submit">Import</button>
      </div>
    </form>
  );
}
