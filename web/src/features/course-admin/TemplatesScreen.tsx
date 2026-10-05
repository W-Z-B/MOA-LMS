import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post, remove } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { SiteTemplate, TemplatePage } from "../../api/types-content";
import { useCrumb } from "../../app/frame";
import { asHtml } from "./sections";
import "../content/content.css";

interface Draft {
  id: number | null;
  name: string;
  description: string;
  is_default: boolean;
  modules: { title: string; items: TemplatePage[] }[];
}

const blank = (): Draft => ({ id: null, name: "", description: "", is_default: false, modules: [{ title: "", items: [] }] });

/**
 * Course templates (item 2.17), for course administrators: the modules and draft pages a new, empty course
 * starts with. One template is the standard, applied to every course created here.
 */
export default function TemplatesScreen() {
  const [templates, setTemplates] = useState<SiteTemplate[] | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useCrumb("Course templates");

  const load = useCallback(() => {
    get<Paginated<SiteTemplate>>("/site-templates/")
      .then((page) => setTemplates(page.results))
      .catch((err) => setError(errorMessage(err, "Could not read the templates.")));
  }, []);
  useEffect(load, [load]);

  const edit = (t: SiteTemplate) => {
    setStatus(null);
    setConfirming(false);
    setDraft({
      id: t.id,
      name: t.name,
      description: t.description,
      is_default: t.is_default,
      modules: t.structure.modules.map((m) => ({ title: m.title, items: (m.items ?? []).map((i) => ({ title: i.title, body: i.body ?? "" })) })),
    });
  };

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!draft) return;
    setError(null);
    const body = {
      name: draft.name,
      description: draft.description,
      is_default: draft.is_default,
      structure: {
        modules: draft.modules.map((m) => ({
          title: m.title,
          items: m.items.map((i) => ({ kind: "page", title: i.title, body: asHtml(i.body ?? "") })),
        })),
      },
    };
    try {
      if (draft.id) await patch(`/site-templates/${draft.id}/`, body);
      else await post("/site-templates/", body);
      setStatus(`Saved the template “${draft.name}”.`);
      setDraft(null);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not save the template."));
    }
  }

  async function destroy() {
    if (!draft?.id) return;
    try {
      await remove(`/site-templates/${draft.id}/`);
      setStatus(`Removed the template “${draft.name}”.`);
      setDraft(null);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not remove the template."));
    }
  }

  const setModule = (at: number, change: Partial<Draft["modules"][number]>) =>
    draft && setDraft({ ...draft, modules: draft.modules.map((m, i) => (i === at ? { ...m, ...change } : m)) });

  return (
    <>
      <div className="page-head">
        <h1>Course templates</h1>
        {!draft && (
          <button
            type="button"
            onClick={() => {
              setDraft(blank());
              setStatus(null);
            }}
          >
            New template
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p role="status" className={status ? "notice good" : "sr-only"}>
        {status}
      </p>
      {!draft && templates?.length === 0 && <p className="muted">No templates yet.</p>}
      {!draft && (
        <ul className="plain templates">
          {templates?.map((t) => (
            <li key={t.id} className="panel-card padded">
              <div className="spread">
                <div>
                  <h2 className="item-title">
                    {t.name} {t.is_default && <span className="pill">Standard</span>}
                  </h2>
                  <p className="muted small">
                    {t.structure.modules.length} modules{t.description ? ` · ${t.description}` : ""}
                  </p>
                </div>
                <button type="button" className="secondary" aria-label={`Edit the template “${t.name}”`} onClick={() => edit(t)}>
                  Edit
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {draft && (
        <form className="stack template-form" onSubmit={save}>
          <h2>{draft.id ? `Edit “${draft.name}”` : "New template"}</h2>
          <label>
            Name
            <input id="template-name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} required />
          </label>
          <label>
            What it is for
            <input id="template-description" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
          </label>
          <label className="inline">
            <input type="checkbox" checked={draft.is_default} onChange={(e) => setDraft({ ...draft, is_default: e.target.checked })} /> The standard
            template, given to every new course
          </label>
          {draft.modules.map((m, mi) => (
            <fieldset key={mi} className="template-module">
              <legend>Module {mi + 1}</legend>
              <label>
                Module title
                <input value={m.title} onChange={(e) => setModule(mi, { title: e.target.value })} required />
              </label>
              {m.items.map((page, pi) => (
                <div key={pi} className="template-page">
                  <label>
                    Page {pi + 1} title
                    <input
                      value={page.title}
                      onChange={(e) => setModule(mi, { items: m.items.map((p, i) => (i === pi ? { ...p, title: e.target.value } : p)) })}
                      required
                    />
                  </label>
                  <label>
                    Page {pi + 1} starting text
                    <textarea
                      value={page.body ?? ""}
                      onChange={(e) => setModule(mi, { items: m.items.map((p, i) => (i === pi ? { ...p, body: e.target.value } : p)) })}
                    />
                  </label>
                  <button
                    type="button"
                    className="link"
                    onClick={() => setModule(mi, { items: m.items.filter((_, i) => i !== pi) })}
                    aria-label={`Remove page ${pi + 1} of module ${mi + 1}`}
                  >
                    Remove page
                  </button>
                </div>
              ))}
              <div className="actions">
                <button type="button" className="secondary small-button" onClick={() => setModule(mi, { items: [...m.items, { title: "", body: "" }] })}>
                  Add a page
                </button>
                {draft.modules.length > 1 && (
                  <button
                    type="button"
                    className="secondary small-button"
                    aria-label={`Remove module ${mi + 1}`}
                    onClick={() => setDraft({ ...draft, modules: draft.modules.filter((_, i) => i !== mi) })}
                  >
                    Remove module
                  </button>
                )}
              </div>
            </fieldset>
          ))}
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setDraft({ ...draft, modules: [...draft.modules, { title: "", items: [] }] })}>
              Add a module
            </button>
          </div>
          <div className="actions">
            {draft.id &&
              (confirming ? (
                <button type="button" className="danger" onClick={destroy}>
                  Remove it for good
                </button>
              ) : (
                <button type="button" className="secondary danger-text" onClick={() => setConfirming(true)}>
                  Remove template
                </button>
              ))}
            <button type="button" className="secondary" onClick={() => setDraft(null)}>
              Cancel
            </button>
            <button type="submit">Save template</button>
          </div>
        </form>
      )}
    </>
  );
}
