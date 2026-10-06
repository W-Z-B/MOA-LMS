import { useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post, remove } from "../../api/client";
import type { Module, Paginated } from "../../api/types";
import type { GradeCategory } from "../../api/types-marking";
import type { SiteTools, Tool, ToolLineItem } from "../../api/types-connect";
import "./tools.css";

interface Props {
  siteId: number;
  teaching: boolean;
  modules: Module[];
}

/**
 * A course's outside tools (item 6.07). Students open the published ones; teaching staff place registered
 * tools in modules, choose content inside a tool, and say how each tool's gradebook column counts. A tool
 * opens in a new window: the LMS signs the person in to it, sending only what the tool may receive.
 */
export function ToolsTab({ siteId, teaching, modules }: Props) {
  const [data, setData] = useState<SiteTools | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const load = useCallback(() => {
    get<SiteTools>(`/sites/${siteId}/tools/`)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not read this course's tools.")));
  }, [siteId]);

  useEffect(() => {
    load();
    // Content chosen in a tool comes back in the tool's window: show it when this window is used again.
    window.addEventListener("focus", load);
    return () => window.removeEventListener("focus", load);
  }, [load]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!data) return <p className="loading">Reading the tools…</p>;

  async function removePlacement(id: number, title: string) {
    try {
      await remove(`/tool-placements/${id}/`);
      setStatus(`Removed “${title}”.`);
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not remove the tool."));
    }
  }

  return (
    <div className="tools">
      {status && (
        <p role="status" className="notice good">
          {status}
        </p>
      )}
      <section aria-labelledby="tools-on-course">
        <h2 id="tools-on-course">Outside tools on this course</h2>
        {data.placements.length === 0 && <p className="muted">No outside tools on this course yet.</p>}
        <ul className="plain tool-list">
          {data.placements.map((p) => (
            <li key={p.id} className="panel-card padded">
              <h3 className="item-title">{p.title}</h3>
              <p className="muted small">
                {p.tool_name}
                {teaching && (p.is_published ? " · Published" : " · Draft: publish it in Content")}
                {teaching && ` · in ${modules.find((m) => m.id === p.module_id)?.title ?? "a module"}`}
              </p>
              <div className="actions">
                <a className="button" href={p.launch_url} target="_blank" rel="noopener" aria-label={`Open ${p.title} (opens in a new window)`}>
                  Open
                </a>
                {teaching && (
                  <button type="button" className="secondary" onClick={() => removePlacement(p.id, p.title)} aria-label={`Remove ${p.title}`}>
                    Remove
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
        {!teaching && data.placements.length > 0 && (
          <p className="muted small">Each opens in a new window. The tool learns your role and this course, and a code that stands for you there.</p>
        )}
      </section>
      {teaching && (
        <>
          <AddTool siteId={siteId} tools={data.tools} modules={modules} onAdded={(title) => (setStatus(`Added “${title}” as a draft.`), load())} />
          <Columns siteId={siteId} items={data.line_items} onSaved={(label) => (setStatus(`Saved how “${label}” counts.`), load())} />
        </>
      )}
    </div>
  );
}

function AddTool({ tools, modules, onAdded }: { siteId: number; tools: Tool[]; modules: Module[]; onAdded: (title: string) => void }) {
  const [toolId, setToolId] = useState<number | "">(tools[0]?.id ?? "");
  const [moduleId, setModuleId] = useState<number | "">(modules[0]?.id ?? "");
  const [title, setTitle] = useState("");
  const [graded, setGraded] = useState(false);
  const [maximum, setMaximum] = useState("10");
  const [error, setError] = useState<string | null>(null);
  const tool = tools.find((t) => t.id === toolId);

  if (tools.length === 0)
    return (
      <section aria-labelledby="tools-add">
        <h2 id="tools-add">Add a tool</h2>
        <p className="muted">No outside tools are registered yet. A course administrator registers them in Admin.</p>
      </section>
    );

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await post("/tool-placements/", {
        module: moduleId,
        tool: toolId,
        title: title || tool?.name,
        score_maximum: graded && tool?.grades ? maximum : null,
      });
      onAdded(title || tool?.name || "the tool");
      setTitle("");
    } catch (err) {
      setError(errorMessage(err, "Could not add the tool."));
    }
  }

  return (
    <section aria-labelledby="tools-add">
      <h2 id="tools-add">Add a tool</h2>
      {modules.length === 0 ? (
        <p className="muted">Add a module in Content first: tools are placed in a module.</p>
      ) : (
        <form className="stack sub-form" onSubmit={add}>
          <div className="form-row">
            <label className="grow">
              Tool
              <select value={toolId} onChange={(e) => setToolId(Number(e.target.value))}>
                {tools.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="grow">
              Module
              <select value={moduleId} onChange={(e) => setModuleId(Number(e.target.value))}>
                {modules.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {tool && (
            <div className="notice receives">
              <p>
                <strong>What {tool.name} receives</strong>
              </p>
              <ul>
                {tool.receives.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          )}
          <label>
            Title students see
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={tool?.name} maxLength={160} />
          </label>
          {tool?.grades && (
            <div className="form-row">
              <label className="inline">
                <input type="checkbox" checked={graded} onChange={(e) => setGraded(e.target.checked)} /> The tool sends scores to a gradebook column
              </label>
              {graded && (
                <label>
                  Maximum score
                  <input type="number" min={0.01} step="any" inputMode="decimal" value={maximum} onChange={(e) => setMaximum(e.target.value)} required />
                </label>
              )}
            </div>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <div className="actions">
            <button type="submit">Add as a draft</button>
            {tool?.can_choose_content && (
              <a className="button secondary" href={`/api/lti/choose/?tool=${toolId}&module=${moduleId}`} target="_blank" rel="noopener">
                Choose content in {tool.name} (new window)
              </a>
            )}
          </div>
        </form>
      )}
    </section>
  );
}

function Columns({ siteId, items, onSaved }: { siteId: number; items: ToolLineItem[]; onSaved: (label: string) => void }) {
  const [categories, setCategories] = useState<GradeCategory[]>([]);
  useEffect(() => {
    if (items.length === 0) return;
    get<Paginated<GradeCategory>>(`/grade-categories/?site=${siteId}`)
      .then((page) => setCategories(page.results))
      .catch(() => setCategories([]));
  }, [siteId, items.length]);
  return (
    <section aria-labelledby="tools-columns">
      <h2 id="tools-columns">Gradebook columns from tools</h2>
      {items.length === 0 ? (
        <p className="muted">No tool sends scores to this course yet.</p>
      ) : (
        <>
          <p className="muted small">Each column shows in the gradebook. With a weight above 0 it counts in the coursework total.</p>
          <ul className="plain tool-list">
            {items.map((item) => (
              <Column key={item.id} item={item} categories={categories} onSaved={onSaved} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function Column({ item, categories, onSaved }: { item: ToolLineItem; categories: GradeCategory[]; onSaved: (label: string) => void }) {
  const [weight, setWeight] = useState(item.weight);
  const [category, setCategory] = useState<number | "">(item.grade_category ?? "");
  const [error, setError] = useState<string | null>(null);
  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await patch(`/tool-line-items/${item.id}/`, { weight, grade_category: category === "" ? null : category });
      setError(null);
      onSaved(item.label);
    } catch (err) {
      setError(errorMessage(err, "Could not save the column."));
    }
  }
  return (
    <li className="panel-card padded">
      <h3 className="item-title">{item.label}</h3>
      <p className="muted small">
        {item.tool_name} · scores out of {Number(item.score_maximum)}
      </p>
      <form className="form-row" onSubmit={save} aria-label={`How ${item.label} counts`}>
        <label>
          Weight
          <input type="number" min={0} step="any" inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} />
        </label>
        {categories.length > 0 && (
          <label className="grow">
            Category
            <select value={category} onChange={(e) => setCategory(e.target.value === "" ? "" : Number(e.target.value))}>
              <option value="">Not in a category</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="actions">
          <button type="submit" className="secondary">
            Save
          </button>
        </div>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </li>
  );
}
