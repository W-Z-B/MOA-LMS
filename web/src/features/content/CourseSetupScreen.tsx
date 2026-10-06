import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post } from "../../api/client";
import { canTeach, type Paginated, type Site } from "../../api/types";
import type { Contents, CopyDone, SiteTemplate, StorageSummary } from "../../api/types-content";
import { sizeInWords } from "../../api/types-content";
import { plural } from "../../app/format";
import { useCrumb } from "../../app/frame";
import { DateManager } from "./DateManager";
import "./content.css";

interface Props {
  siteId: number;
}

/**
 * Course setup for teaching staff (items 2.17, 2.18 and 2.20): give an empty course a template, copy an
 * earlier course with its dates moved, manage every date on the course in one table, and see the course's
 * storage use with its largest files.
 */
export default function CourseSetupScreen({ siteId }: Props) {
  const [contents, setContents] = useState<Contents | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  useCrumb(contents ? `${contents.site.title}: setup` : null);

  const load = useCallback(() => {
    get<Contents>(`/sites/${siteId}/contents/`)
      .then((c) => {
        setContents(c);
        setVersion((v) => v + 1);
      })
      .catch((err) => setError(errorMessage(err, "Could not open this course.")));
  }, [siteId]);
  useEffect(load, [load]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!contents) return <p className="loading">Opening course setup…</p>;
  if (!canTeach(contents.site.my_role))
    return (
      <p role="alert" className="error">
        Only the course's teaching staff set it up.
      </p>
    );
  const empty = contents.modules.length === 0;
  return (
    <div className="setup">
      <p className="back-link">
        <a href={`#/sites/${siteId}`}>Back to {contents.site.title}</a>
      </p>
      <h1>Course setup</h1>
      <p className="muted">{contents.site.title}</p>
      {empty && <ApplyTemplate siteId={siteId} onDone={load} />}
      <CopyCourse siteId={siteId} empty={empty} onDone={load} />
      <DateManager key={version} siteId={siteId} />
      <StorageUse key={`storage-${version}`} siteId={siteId} />
    </div>
  );
}

function ApplyTemplate({ siteId, onDone }: { siteId: number; onDone: () => void }) {
  const [templates, setTemplates] = useState<SiteTemplate[]>([]);
  const [chosen, setChosen] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Paginated<SiteTemplate>>("/site-templates/")
      .then((page) => {
        setTemplates(page.results);
        setChosen(String((page.results.find((t) => t.is_default) ?? page.results[0])?.id ?? ""));
      })
      .catch(() => setTemplates([]));
  }, []);

  async function apply(e: FormEvent) {
    e.preventDefault();
    try {
      await post(`/sites/${siteId}/apply-template/`, chosen ? { template: Number(chosen) } : {});
      onDone();
    } catch (err) {
      setError(errorMessage(err, "Could not apply the template."));
    }
  }

  return (
    <section className="panel-card padded setup-section" aria-labelledby="template-title">
      <h2 id="template-title">Start from a template</h2>
      <p className="muted small">The course is empty. A template gives it the GSA layout, with draft pages for you to fill in.</p>
      {templates.length === 0 ? (
        <p className="muted">There is no course template yet. A course administrator can add one.</p>
      ) : (
        <form className="form-row" onSubmit={apply}>
          <label className="grow">
            Template
            <select id="template-choice" value={chosen} onChange={(e) => setChosen(e.target.value)}>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                  {t.is_default ? " (standard)" : ""}
                </option>
              ))}
            </select>
          </label>
          <div className="actions">
            <button type="submit">Apply template</button>
          </div>
        </form>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}

function CopyCourse({ siteId, empty, onDone }: { siteId: number; empty: boolean; onDone: () => void }) {
  const [sites, setSites] = useState<Site[]>([]);
  const [source, setSource] = useState("");
  const [how, setHow] = useState<"days" | "start">("start");
  const [days, setDays] = useState("0");
  const [start, setStart] = useState("");
  const [replace, setReplace] = useState(false);
  const [done, setDone] = useState<CopyDone | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copying, setCopying] = useState(false);

  useEffect(() => {
    get<Paginated<Site>>("/sites/")
      .then((page) => setSites(page.results.filter((s) => s.id !== siteId && canTeach(s.my_role))))
      .catch(() => setSites([]));
  }, [siteId]);

  async function copy(e: FormEvent) {
    e.preventDefault();
    setCopying(true);
    setError(null);
    setDone(null);
    try {
      const when = how === "start" ? { start_date: start } : { offset_days: Number(days) };
      setDone(await post<CopyDone>(`/sites/${siteId}/copy-from/`, { source: Number(source), replace_existing: replace, ...when }));
      onDone();
    } catch (err) {
      setError(errorMessage(err, "Could not copy the course."));
    } finally {
      setCopying(false);
    }
  }

  return (
    <section className="panel-card padded setup-section" aria-labelledby="copy-title">
      <h2 id="copy-title">Copy from an earlier course</h2>
      <p className="muted small">
        Copies modules, pages, files, links, release dates and assignments, never students, groups, work or marks. Every date is moved
        by the same number of days.
      </p>
      {sites.length === 0 ? (
        <p className="muted">You teach no other course to copy from.</p>
      ) : (
        <form className="stack" onSubmit={copy}>
          <label>
            Course to copy from
            <select id="copy-source" value={source} onChange={(e) => setSource(e.target.value)} required>
              <option value="" disabled>
                Choose…
              </option>
              {sites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title} ({s.code})
                </option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend>Move its dates</legend>
            <label className="inline">
              <input type="radio" name="copy-how" checked={how === "start"} onChange={() => setHow("start")} /> So that its first date falls on a
              new start date
            </label>
            <label className="inline">
              <input type="radio" name="copy-how" checked={how === "days"} onChange={() => setHow("days")} /> By a number of days
            </label>
            {how === "start" ? (
              <label>
                New start date
                <input id="copy-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} required />
              </label>
            ) : (
              <label>
                Days to move every date (a minus number moves them earlier)
                <input id="copy-days" type="number" inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} required />
              </label>
            )}
          </fieldset>
          <label className="inline">
            <input id="copy-replace" type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> Replace this course's
            present modules and items
          </label>
          {!empty && !replace && (
            <p className="muted small">This course already has content. Tick “Replace” to copy over it; otherwise the copy is refused.</p>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <div className="actions">
            <button type="submit" disabled={copying}>
              {copying ? "Copying…" : "Copy the course"}
            </button>
          </div>
        </form>
      )}
      {done && (
        <div role="status" className="notice good">
          <p>
            Copied {plural(done.modules, "module", "modules")}, {plural(done.items, "item", "items")} and{" "}
            {plural(done.assignments, "assignment", "assignments")}; every date moved by {plural(done.offset_days, "day", "days")}. Check the
            dates below before students start.
          </p>
          {done.left_out.length > 0 && <p>Left out (under review or withdrawn): {done.left_out.join(", ")}.</p>}
          {done.missing_files.length > 0 && <p>Files that could not be found and were not copied: {done.missing_files.join(", ")}.</p>}
        </div>
      )}
    </section>
  );
}

function StorageUse({ siteId }: { siteId: number }) {
  const [use, setUse] = useState<StorageSummary | null>(null);
  useEffect(() => {
    get<StorageSummary>(`/sites/${siteId}/storage/`)
      .then(setUse)
      .catch(() => setUse(null));
  }, [siteId]);
  if (!use) return null;
  const files = use.largest_files ?? [];
  return (
    <section className="panel-card padded setup-section" aria-labelledby="storage-title">
      <h2 id="storage-title">Storage</h2>
      <p>
        {sizeInWords(use.used_bytes)} used of {sizeInWords(use.allowance_bytes)} ({use.percent}%).
      </p>
      <span className="bar wide-bar" aria-hidden="true">
        <span style={{ width: `${Math.min(use.percent, 100)}%` }} />
      </span>
      {use.warning && <p className="notice warn">{use.warning}</p>}
      {files.length > 0 && (
        <div className="scroll-x" tabIndex={0} role="region" aria-label="Largest files">
          <table>
            <caption className="sr-only">The course's largest files</caption>
            <thead>
              <tr>
                <th scope="col">File</th>
                <th scope="col">Module</th>
                <th scope="col" className="num">
                  Size
                </th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.id}>
                  <td>
                    {f.title}
                    <span className="muted small block">{f.filename}</span>
                  </td>
                  <td>{f.module}</td>
                  <td className="num">{sizeInWords(f.file_size)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
