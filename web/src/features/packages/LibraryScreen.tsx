import { useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, post, remove } from "../../api/client";
import { canTeach, type Paginated, type Site, type SiteContents } from "../../api/types";
import { STANDARD_NAME, type LibraryItem, type LibraryKind, type SharedBank } from "../../api/types-packages";
import { useData } from "../admin/data";
import { Said, Section } from "../admin/kit";
import { LicenceFields } from "./LicenceFields";
import { NO_LICENCE, licenceFields, licenceLine, type LicenceValue } from "./licence";
import "./packages.css";

const KIND_WORDS: Record<LibraryKind, string> = { page: "Page", file: "File", link: "Link", package: "Package" };

interface Props {
  /** The address after #/library: "", "/banks" or "/share?item=12". */
  path: string;
  onNavigate: (to: string) => void;
}

/**
 * The shared content library (item 5.14): material and question banks shared across courses and departments,
 * with open educational resources (FAO, CABI and the like) and their licences. Teaching staff browse it, add
 * to it, and copy an item into a module of a course they teach as a draft.
 */
export default function LibraryScreen({ path, onNavigate }: Props) {
  const [bare, query = ""] = path.split("?");
  const share = bare === "/share" ? Number(new URLSearchParams(query).get("item")) || null : null;
  const banks = bare === "/banks";
  return (
    <div className="library-view">
      <div className="page-head">
        <h1>Content library</h1>
      </div>
      <nav aria-label="Library">
        <ul className="tabs plain-tabs">
          <li>
            <a className={!banks ? "tab active" : "tab"} aria-current={!banks ? "page" : undefined} href="#/library">
              Material
            </a>
          </li>
          <li>
            <a className={banks ? "tab active" : "tab"} aria-current={banks ? "page" : undefined} href="#/library/banks">
              Question banks
            </a>
          </li>
        </ul>
      </nav>
      {share !== null && <ShareItem itemId={share} onDone={() => onNavigate("/library")} />}
      {banks ? <Banks /> : <Material />}
    </div>
  );
}

function Material() {
  const [words, setWords] = useState("");
  const [kind, setKind] = useState("");
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [using, setUsing] = useState<number | null>(null);
  const [said, setSaid] = useState<string | null>(null);
  const params = new URLSearchParams();
  if (words) params.set("q", words);
  if (kind) params.set("kind", kind);
  if (open) params.set("open", "true");
  const { data, error, reload } = useData<Paginated<LibraryItem>>(`/library/items/?${params}`, "Could not load the library.");
  const [failed, setFailed] = useState<string | null>(null);

  async function drop(item: LibraryItem) {
    try {
      await remove(`/library/items/${item.id}/`);
      setSaid(`Removed “${item.title}” from the library.`);
      reload();
    } catch (err) {
      setFailed(errorMessage(err, "Could not remove it."));
    }
  }

  return (
    <Section title="Material" intro="Pages, files, links and packages shared by GSA's departments, and open educational resources with their licences.">
      <div className="library-filters">
        <label>
          Search
          <input type="search" value={words} onChange={(e) => setWords(e.target.value)} placeholder="Title, description or tag" />
        </label>
        <label>
          Kind
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">Every kind</option>
            {Object.entries(KIND_WORDS).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="check-line">
          <input type="checkbox" checked={open} onChange={(e) => setOpen(e.target.checked)} /> Open educational resources only
        </label>
      </div>
      <Said done={said} error={error ?? failed} />
      {!adding && (
        <div className="actions">
          <button type="button" onClick={() => setAdding(true)}>
            Add to the library
          </button>
        </div>
      )}
      {adding && (
        <AddItem
          onCancel={() => setAdding(false)}
          onSaved={(item) => {
            setAdding(false);
            setSaid(`Added “${item.title}” to the library.`);
            reload();
          }}
        />
      )}
      {data === null && !error && <p className="loading">Loading…</p>}
      {data !== null && data.results.length === 0 && <p className="muted">Nothing in the library matches.</p>}
      {data !== null && data.results.length > 0 && (
        <ul className="rows" aria-label="Library items">
          {data.results.map((item) => (
            <li key={item.id} className="library-item">
              <div className="row-head">
                <span className="strong">{item.title}</span>
                <span className="chip">{KIND_WORDS[item.kind]}</span>
                {item.is_open_resource && <span className="chip">Open resource</span>}
              </div>
              {item.description && <p className="small-gap">{item.description}</p>}
              <p className="small muted licence-line">
                {licenceLine(item)}
                {item.kind === "package" && item.package.standard ? ` · ${STANDARD_NAME[item.package.standard]}` : ""}
                {` · ${item.department_code ? `Department ${item.department_code}` : "The whole School"}`}
              </p>
              {item.tags.length > 0 && (
                <p className="tags small">
                  {item.tags.map((tag) => (
                    <span key={tag} className="chip">
                      {tag}
                    </span>
                  ))}
                </p>
              )}
              <div className="row-actions">
                <button type="button" className="secondary" aria-expanded={using === item.id} onClick={() => setUsing(using === item.id ? null : item.id)}>
                  Use in a course
                </button>
                {item.download_url && (
                  <a className="button secondary" href={item.download_url}>
                    Download
                  </a>
                )}
                {item.kind === "link" && (
                  <a className="button secondary" href={item.url} target="_blank" rel="noopener noreferrer">
                    Open the link
                  </a>
                )}
                {item.may_change && (
                  <button type="button" className="secondary danger-text" onClick={() => drop(item)} aria-label={`Remove “${item.title}” from the library`}>
                    Remove
                  </button>
                )}
              </div>
              {using === item.id && (
                <UseItem
                  item={item}
                  onCancel={() => setUsing(null)}
                  onDone={(words) => {
                    setUsing(null);
                    setSaid(words);
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function AddItem({ onSaved, onCancel }: { onSaved: (item: LibraryItem) => void; onCancel: () => void }) {
  const [kind, setKind] = useState<LibraryKind>("file");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [body, setBody] = useState("");
  const [department, setDepartment] = useState("");
  const [oer, setOer] = useState(false);
  const [publisher, setPublisher] = useState("");
  const [tags, setTags] = useState("");
  const [licence, setLicence] = useState<LicenceValue>(NO_LICENCE);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    if ((kind === "file" || kind === "package") && !file) return setError("Choose the file to put up.");
    setSaving(true);
    setError(null);
    const form = new FormData();
    const chosen = oer ? { ...licence, licence: "open_licence" as const } : licence;
    const fields: Record<string, string> = {
      kind,
      title,
      description,
      department_code: department.trim(),
      is_open_resource: String(oer),
      publisher: oer ? publisher : "",
      ...licenceFields(chosen),
    };
    if (kind === "link") fields.url = url;
    if (kind === "page") Object.assign(fields, { body, body_format: "text" });
    Object.entries(fields).forEach(([key, value]) => form.set(key, value));
    tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)
      .forEach((t) => form.append("tags", t));
    if (file && (kind === "file" || kind === "package")) form.set("file", file);
    try {
      onSaved(await post<LibraryItem>("/library/items/", form));
    } catch (err) {
      setError(errorMessage(err, "Could not add it to the library."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="stack sub-form" onSubmit={save} aria-label="Add to the library">
      <label>
        What it is
        <select value={kind} onChange={(e) => setKind(e.target.value as LibraryKind)}>
          <option value="file">A file (PDF, photograph, Word, Excel or PowerPoint)</option>
          <option value="package">A SCORM package or an H5P file</option>
          <option value="link">A link to a web page</option>
          <option value="page">A page of text</option>
        </select>
      </label>
      <label>
        Title{kind === "package" ? " (the package's own when left empty)" : ""}
        <input value={title} onChange={(e) => setTitle(e.target.value)} required={kind !== "package"} maxLength={160} />
      </label>
      {(kind === "file" || kind === "package") && (
        <label>
          {kind === "file" ? "File" : "Package"}
          <input
            type="file"
            accept={kind === "file" ? ".pdf,.jpg,.jpeg,.png,.webp,.heic,.heif,.docx,.xlsx,.pptx" : ".zip,.h5p"}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            aria-required="true"
          />
        </label>
      )}
      {kind === "link" && (
        <label>
          Web address
          <input type="url" inputMode="url" placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)} required />
        </label>
      )}
      {kind === "page" && (
        <label>
          Text
          <textarea value={body} onChange={(e) => setBody(e.target.value)} required />
        </label>
      )}
      <label>
        Description
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>
      <label>
        Department (its HRMS unit code; empty for the whole School)
        <input value={department} onChange={(e) => setDepartment(e.target.value)} maxLength={20} />
      </label>
      <label className="check-line">
        <input type="checkbox" checked={oer} onChange={(e) => setOer(e.target.checked)} /> An open educational resource from a trusted source
      </label>
      {oer && (
        <label>
          Publisher
          <input value={publisher} onChange={(e) => setPublisher(e.target.value)} placeholder="FAO, CABI…" required />
        </label>
      )}
      <LicenceFields id="library-new" value={licence} onChange={setLicence} openOnly={oer} />
      <label>
        Tags (separated by commas)
        <input value={tags} onChange={(e) => setTags(e.target.value)} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" disabled={saving}>
          {saving ? "Adding…" : "Add to the library"}
        </button>
      </div>
    </form>
  );
}

/** Choose a module of a course the person teaches. */
function useTaughtModules() {
  const [sites, setSites] = useState<Site[] | null>(null);
  useEffect(() => {
    get<Paginated<Site>>("/sites/")
      .then((page) => setSites(page.results.filter((s) => canTeach(s.my_role))))
      .catch(() => setSites([]));
  }, []);
  return sites;
}

function UseItem({ item, onDone, onCancel }: { item: LibraryItem; onDone: (words: string) => void; onCancel: () => void }) {
  const sites = useTaughtModules();
  const [site, setSite] = useState("");
  const [modules, setModules] = useState<{ id: number; title: string }[]>([]);
  const [module, setModule] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!site) return;
    get<SiteContents>(`/sites/${site}/contents/`)
      .then((contents) => setModules(contents.modules.map((m) => ({ id: m.id, title: m.title }))))
      .catch(() => setModules([]));
  }, [site]);

  async function use(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const done = await post<{ site: number; title: string }>(`/library/items/${item.id}/use/`, { module: Number(module) });
      onDone(`Copied “${done.title}” into the course as a draft. Publish it there when it is ready.`);
    } catch (err) {
      setError(errorMessage(err, "Could not copy it into the course."));
    }
  }

  return (
    <form className="stack sub-form" onSubmit={use} aria-label={`Use “${item.title}” in a course`}>
      <label>
        Course
        <select
          value={site}
          onChange={(e) => {
            setSite(e.target.value);
            setModule("");
            setModules([]);
          }}
          required
        >
          <option value="">{sites === null ? "Loading…" : "Choose…"}</option>
          {(sites ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.code} {s.title}
            </option>
          ))}
        </select>
      </label>
      <label>
        Module
        <select value={module} onChange={(e) => setModule(e.target.value)} required disabled={!site}>
          <option value="">Choose…</option>
          {modules.map((m) => (
            <option key={m.id} value={m.id}>
              {m.title}
            </option>
          ))}
        </select>
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit">Copy into the course</button>
      </div>
    </form>
  );
}

function ShareItem({ itemId, onDone }: { itemId: number; onDone: () => void }) {
  const [department, setDepartment] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  useEffect(() => {
    get<{ title: string }>(`/content/${itemId}/`)
      .then((item) => setTitle(item.title))
      .catch(() => setTitle(null));
  }, [itemId]);

  async function share(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await post("/library/items/share/", { item: itemId, department_code: department.trim(), description });
      onDone();
    } catch (err) {
      setError(errorMessage(err, "Could not share it."));
    }
  }

  return (
    <Section title="Share to the library" intro={title ? `A copy of “${title}” goes on the shelf you choose; the course keeps its own.` : undefined}>
      <form className="stack" onSubmit={share}>
        <label>
          Department (its HRMS unit code; empty for the whole School)
          <input value={department} onChange={(e) => setDepartment(e.target.value)} maxLength={20} />
        </label>
        <label>
          Description
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="submit">Share a copy</button>
        </div>
      </form>
    </Section>
  );
}

function Banks() {
  const { data, error, reload } = useData<SharedBank[]>("/library/banks/", "Could not load the question banks.");
  const mine = useData<Paginated<{ id: number; name: string; site: number | null; owner_label: string; can_manage: boolean }>>(
    "/question-banks/",
    "Could not load your question banks.",
  );
  const [bank, setBank] = useState("");
  const [department, setDepartment] = useState("");
  const [name, setName] = useState("");
  const [licence, setLicence] = useState<LicenceValue>(NO_LICENCE);
  const [said, setSaid] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const courseBanks = (mine.data?.results ?? []).filter((b) => b.site !== null && b.can_manage);

  async function share(e: FormEvent) {
    e.preventDefault();
    setFailed(null);
    try {
      const made = await post<SharedBank>("/library/banks/share/", { bank: Number(bank), department_code: department.trim(), name, ...licenceFields(licence) });
      setSaid(`Copied ${made.questions} questions to the bank “${made.name}” of department ${made.department_code}.`);
      reload();
    } catch (err) {
      setFailed(errorMessage(err, "Could not share the bank."));
    }
  }

  return (
    <>
      <Section title="Question banks" intro="Department banks are open to every lecturer, in the Quizzes tab of any course.">
        <Said error={error} done={said} />
        {data === null && !error && <p className="loading">Loading…</p>}
        {data !== null && data.length === 0 && <p className="muted">No department banks yet.</p>}
        {data !== null && data.length > 0 && (
          <ul className="rows" aria-label="Department question banks">
            {data.map((b) => (
              <li key={b.id}>
                <div className="row-head">
                  <span className="strong">{b.name}</span>
                  <span className="chip">Department {b.department_code}</span>
                </div>
                <p className="small muted licence-line">
                  {b.questions} questions · {licenceLine(b)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Section>
      {courseBanks.length > 0 && (
        <Section title="Share a course's question bank" intro="Its questions are copied, at their latest version, to a department's bank.">
          <form className="stack" onSubmit={share}>
            <label>
              Bank
              <select value={bank} onChange={(e) => setBank(e.target.value)} required>
                <option value="">Choose…</option>
                {courseBanks.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.owner_label}: {b.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Department (its HRMS unit code)
              <input value={department} onChange={(e) => setDepartment(e.target.value)} maxLength={20} required />
            </label>
            <label>
              Name for the shared bank (the bank's own when left empty)
              <input value={name} onChange={(e) => setName(e.target.value)} maxLength={160} />
            </label>
            <LicenceFields id="bank-share" value={licence} onChange={setLicence} />
            <Said error={failed} />
            <div className="actions">
              <button type="submit">Share a copy</button>
            </div>
          </form>
        </Section>
      )}
    </>
  );
}
