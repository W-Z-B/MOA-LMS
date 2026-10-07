import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import type { AccessibilityIssue, Contents, Item } from "../../api/types-content";
import { documentKind } from "../../api/types-content";
import { useCrumb } from "../../app/frame";
import { useAltSuggestions } from "../ai/altText";
import { RichEditor, type Picture } from "./RichEditor";
import "./content.css";

interface Props {
  siteId: number;
  /** The page being changed; a new page when null. */
  itemId: number | null;
  /** For a new page: the module it goes in. */
  moduleId: number | null;
  onNavigate: (to: string) => void;
}

/** How long the writer pauses before the accessibility check runs on what they have written. */
export const CHECK_AFTER_MS = 800;

function Issues({ issues, title }: { issues: AccessibilityIssue[]; title: string }) {
  if (issues.length === 0) return null;
  return (
    <div className="issues">
      <h3 className="issues-title">{title}</h3>
      <ul>
        {issues.map((issue, at) => (
          <li key={at} className={issue.severity === "error" ? "issue issue-error" : "issue"}>
            <strong>{issue.severity === "error" ? "Must be fixed: " : "Check: "}</strong>
            {issue.detail}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Writing a page (items 2.12 and 2.13): the rich text editor, with the accessibility check run as the
 * lecturer writes (after a pause) and its findings beside the text. A picture without alternative text
 * cannot be saved; other findings are warnings, saved and shown again after the save.
 */
export default function PageEditorScreen({ siteId, itemId, moduleId, onNavigate }: Props) {
  const [contents, setContents] = useState<Contents | null>(null);
  const [page, setPage] = useState<Item | null>(null);
  const [title, setTitle] = useState("");
  const [module, setModule] = useState<number | null>(moduleId);
  const [body, setBody] = useState("");
  const [issues, setIssues] = useState<AccessibilityIssue[]>([]);
  const [checking, setChecking] = useState(false);
  const [saved, setSaved] = useState<{ message: string; issues: AccessibilityIssue[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const asked = useRef(0);
  useCrumb(page ? `Editing ${page.title}` : "New page");
  const describe = useAltSuggestions(siteId); // AI help with alternative text, where it is on (item 6.11)

  // The accessibility check, run on the server's own rules a moment after the writer stops typing.
  const check = useCallback((html: string) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const ask = ++asked.current;
      setChecking(true);
      post<{ body: string; issues: AccessibilityIssue[] }>("/content/check-page/", { body: html })
        .then((result) => ask === asked.current && setIssues(result.issues))
        .catch(() => undefined)
        .finally(() => ask === asked.current && setChecking(false));
    }, CHECK_AFTER_MS);
  }, []);

  useEffect(() => {
    const loads: [Promise<Contents>, Promise<Item | null>] = [
      get<Contents>(`/sites/${siteId}/contents/`),
      itemId ? get<Item>(`/content/${itemId}/`) : Promise.resolve(null),
    ];
    Promise.all(loads)
      .then(([site, item]) => {
        setContents(site);
        if (item) {
          setPage(item);
          setTitle(item.title);
          setModule(item.module);
          setBody(item.body);
          check(item.body); // what is already on the page is checked too
        } else if (!moduleId) setModule(site.modules[0]?.id ?? null);
      })
      .catch((err) => setError(errorMessage(err, "Could not open the page.")));
  }, [siteId, itemId, moduleId, check]);

  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);

  const write = useCallback(
    (html: string) => {
      setBody(html);
      setSaved(null);
      check(html);
    },
    [check],
  );

  async function save(publish: boolean | null, e?: FormEvent) {
    e?.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const fields: Record<string, unknown> = { title, body };
      if (publish !== null) fields.is_published = publish;
      const result = page
        ? await patch<Item>(`/content/${page.id}/`, fields)
        : await post<Item>("/content/", { ...fields, module, kind: "page", is_published: publish ?? false });
      const found = result.accessibility_issues ?? [];
      setIssues(found);
      setPage(result);
      const state = result.is_published ? "Saved and published." : "Saved as a draft: students do not see it yet.";
      setSaved({ message: found.length ? `${state} The accessibility check found ${found.length} thing${found.length === 1 ? "" : "s"} to look at.` : state, issues: found });
      if (!page) onNavigate(`/sites/${siteId}/pages/${result.id}/edit`);
    } catch (err) {
      setError(errorMessage(err, "Could not save the page."));
    } finally {
      setSaving(false);
    }
  }

  if (error && !contents)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!contents || (itemId && !page)) return <p className="loading">Opening the editor…</p>;

  const pictures: Picture[] = contents.modules
    .flatMap((m) => m.items)
    .filter((i) => i.kind === "file" && i.download_url && documentKind(i.filename) === "image")
    .map((i) => ({ id: i.id, title: i.title, url: i.download_url! }));
  const blocking = issues.some((i) => i.severity === "error");

  return (
    <form className="page-editor" onSubmit={(e) => save(null, e)}>
      <p className="back-link">
        <a href={`#/sites/${siteId}`}>Back to {contents.site.title}</a>
        {page && (
          <>
            {" · "}
            <a href={`#/sites/${siteId}/pages/${page.id}`}>See it as students do</a>
          </>
        )}
      </p>
      <h1>{page ? "Edit page" : "New page"}</h1>
      <div className="grid2">
        <label>
          Title
          <input id="page-title" value={title} onChange={(e) => setTitle(e.target.value)} required />
        </label>
        {!page && (
          <label>
            Module
            <select id="page-module" value={module ?? ""} onChange={(e) => setModule(Number(e.target.value))} required>
              {contents.modules.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="editor-columns">
        <div className="editor-main">
          <span className="field-label">
            Text
          </span>
          <RichEditor key={page?.id ?? "new"} initialHtml={page?.body ?? ""} onChange={write} pictures={pictures} label="Page text" describe={describe} />
        </div>
        <aside className="editor-side" aria-labelledby="check-title">
          <h2 id="check-title">Accessibility check</h2>
          <div aria-live="polite">
            {checking && <p className="muted small">Checking…</p>}
            {!checking && issues.length === 0 && <p className="muted small">Nothing found so far. The check runs as you write.</p>}
            <Issues issues={issues} title={`${issues.length} to look at`} />
          </div>
        </aside>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {saved && (
        <div role="status" className={saved.issues.length ? "notice warn" : "notice good"}>
          <p>{saved.message}</p>
        </div>
      )}
      <div className="actions">
        <button type="submit" className="secondary" disabled={saving || blocking || !module}>
          {page ? "Save" : "Save as draft"}
        </button>
        {(!page || !page.is_published) && (
          <button type="button" disabled={saving || blocking || !module} onClick={() => save(true)}>
            Save and publish
          </button>
        )}
        {page?.is_published && (
          <button type="button" className="secondary" disabled={saving} onClick={() => save(false)}>
            Unpublish
          </button>
        )}
      </div>
      {blocking && <p className="muted small">Fix what must be fixed before saving.</p>}
    </form>
  );
}
