import { useEffect, useState } from "react";
import { errorMessage, get, patch } from "../../api/client";
import type { Paginated, Site } from "../../api/types";
import type { StorageSummary } from "../../api/types-content";
import { sizeInWords } from "../../api/types-content";
import { useCrumb } from "../../app/frame";
import "../content/content.css";

type SiteRow = Site & { storage_allowance_mb: number | null };

/** How many courses are listed at once; finding a course by name or code narrows the list. */
const SHOWN = 20;

/** One course's use and its allowance, which a course administrator may change (item 2.20). */
function AllowanceRow({ site, onSaved }: { site: SiteRow; onSaved: (row: SiteRow) => void }) {
  const [use, setUse] = useState<StorageSummary | null>(null);
  const [value, setValue] = useState(site.storage_allowance_mb === null ? "" : String(site.storage_allowance_mb));
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    get<StorageSummary>(`/sites/${site.id}/storage/`)
      .then(setUse)
      .catch(() => setUse(null));
  }, [site.id, site.storage_allowance_mb]);

  async function save() {
    try {
      const saved = await patch<SiteRow>(`/sites/${site.id}/`, { storage_allowance_mb: value === "" ? null : Number(value) });
      setMessage({ ok: true, text: "Saved." });
      onSaved(saved);
    } catch (err) {
      setMessage({ ok: false, text: errorMessage(err, "Could not save the allowance.") });
    }
  }

  return (
    <li className="panel-card padded allowance">
      <h2 className="item-title">{site.title}</h2>
      <p className="muted small">
        {site.code}
        {use && ` · ${sizeInWords(use.used_bytes)} used of ${sizeInWords(use.allowance_bytes)} (${use.percent}%)`}
      </p>
      {use?.warning && <p className="notice warn small">{use.warning}</p>}
      <div className="form-row">
        <label className="grow">
          Allowance in MB (empty for the standard allowance)
          <input type="number" min={1} inputMode="numeric" value={value} onChange={(e) => setValue(e.target.value)} />
        </label>
        <div className="actions">
          <button type="button" className="secondary" onClick={save}>
            Save allowance
          </button>
        </div>
      </div>
      {message && (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? "muted small" : "error"}>
          {message.text}
        </p>
      )}
    </li>
  );
}

/** Storage allowances for every course (item 2.20): use, and a larger or smaller allowance where needed. */
export default function StorageAllowancesScreen() {
  const [sites, setSites] = useState<SiteRow[] | null>(null);
  const [find, setFind] = useState("");
  const [error, setError] = useState<string | null>(null);
  useCrumb("Storage allowances");

  useEffect(() => {
    get<Paginated<SiteRow>>("/sites/")
      .then((page) => setSites(page.results))
      .catch((err) => setError(errorMessage(err, "Could not read the courses.")));
  }, []);

  const words = find.trim().toLowerCase();
  const matching = (sites ?? []).filter((s) => !words || `${s.title} ${s.code}`.toLowerCase().includes(words));
  return (
    <>
      <div className="page-head">
        <h1>Storage allowances</h1>
      </div>
      <div className="filters">
        <label className="grow">
          Find a course
          <input type="search" value={find} onChange={(e) => setFind(e.target.value)} placeholder="Title or code" />
        </label>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {sites === null && !error && <p className="loading">Reading the courses…</p>}
      {sites !== null && matching.length === 0 && <p className="muted">No course matches.</p>}
      <ul className="plain allowances">
        {matching.slice(0, SHOWN).map((site) => (
          <AllowanceRow key={site.id} site={site} onSaved={(row) => setSites((all) => all?.map((s) => (s.id === row.id ? row : s)) ?? null)} />
        ))}
      </ul>
      {matching.length > SHOWN && <p className="muted small">Showing {SHOWN} of {matching.length}. Type part of a title or code to find a course.</p>}
    </>
  );
}
