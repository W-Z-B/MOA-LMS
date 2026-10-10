import { lazy, Suspense, useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import type { Paginated, SiteContents } from "../../api/types";
import type { Contents, CourseModule, Item, SiteGroup } from "../../api/types-content";
import { isToolLaunch } from "../../api/types-connect";
import { DocumentView, PageBody } from "./PageBody";
import { ItemForm } from "./ItemForm";
import { ReleaseEditor } from "./ReleaseEditor";
import "./content.css";

// Packages (items 5.12, 5.13): the form loads only when a package is put up.
const PackageForm = lazy(() => import("../packages/PackageForm"));
// --- media: lecture video and offline reading (items 4.03, 4.06), fetched when a course has them ---
const VideoItem = lazy(() => import("../media/VideoItem"));
const ModuleDownload = lazy(() => import("../media/ModuleDownload"));
// --- end media ---

interface Props {
  data: SiteContents;
  teaching: boolean;
  onChanged: () => void;
}

type Release = { kind: "module"; id: number } | { kind: "item"; id: number };
type Adding = { module: number; kind: "file" | "link" | "video" | "package" };
type Dragged = { item: number; from: number };

/** Where a button that was used lives after the list is drawn again, so focus can go back to it. */
const focusId = (item: number, what: string) => `item-${item}-${what}`;

/**
 * The Content tab (items 2.15 and 2.16): modules with their items. Teaching staff arrange them by dragging,
 * or with "Move up" and "Move down" from a keyboard or a phone, copy an item, move it to another module, set
 * when students see it, and publish it; they are told the conditions in the server's words. Students see what
 * is released to them, mark items complete and see their progress through each module.
 */
export function ContentTab({ data, teaching, onChanged }: Props) {
  const contents = data as unknown as Contents;
  const siteId = contents.site.id;
  const modules = contents.modules;
  // Only students record progress; an auditor reads without it.
  const student = contents.site.my_role === "student";
  const [open, setOpen] = useState<number | null>(null);
  const [release, setRelease] = useState<Release | null>(null);
  const [adding, setAdding] = useState<Adding | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [groups, setGroups] = useState<SiteGroup[]>([]);
  const [moduleTitle, setModuleTitle] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragged, setDragged] = useState<Dragged | null>(null);
  const [destinations, setDestinations] = useState<Record<number, string>>({});
  const refocus = useRef<string | null>(null);
  // The size of each course file by item id: pictures on pages say it in data-light mode (item 4.05).
  const sizes = useMemo(() => Object.fromEntries(modules.flatMap((m) => m.items).map((i) => [i.id, i.file_size])), [modules]);

  useEffect(() => {
    if (!teaching) return;
    get<Paginated<SiteGroup>>(`/groups/?site=${siteId}`)
      .then((page) => setGroups(page.results))
      .catch(() => setGroups([]));
  }, [teaching, siteId]);

  // After a move the list is drawn again: focus returns to the control that was used, or its neighbour when
  // that one is now disabled (an item moved to the top can no longer move up).
  useEffect(() => {
    if (!refocus.current) return;
    const target = document.getElementById(refocus.current) as HTMLButtonElement | null;
    const other = refocus.current.endsWith("-up") ? refocus.current.replace(/-up$/, "-down") : refocus.current.replace(/-down$/, "-up");
    const fallback = document.getElementById(other) as HTMLButtonElement | null;
    (target && !target.disabled ? target : fallback)?.focus();
    refocus.current = null;
  }, [data]);

  async function act(action: () => Promise<unknown>, done: string, failed: string, focus?: string) {
    setError(null);
    try {
      await action();
      refocus.current = focus ?? null;
      setStatus(done);
      onChanged();
    } catch (err) {
      setStatus(null);
      setError(errorMessage(err, failed));
    }
  }

  const reorder = (module: CourseModule, item: Item, to: number, focus?: string) => {
    const order = module.items.map((i) => i.id).filter((id) => id !== item.id);
    order.splice(to, 0, item.id);
    return act(
      () => post(`/modules/${module.id}/reorder-items/`, { order }),
      `Moved “${item.title}” to place ${to + 1} of ${order.length} in ${module.title}.`,
      "Could not move the item.",
      focus,
    );
  };

  const moveTo = (item: Item, module: CourseModule, position?: number) =>
    act(
      () => post(`/content/${item.id}/move/`, position ? { module: module.id, position } : { module: module.id }),
      `Moved “${item.title}” to ${module.title}.`,
      "Could not move the item.",
    );

  const moveModule = (module: CourseModule, delta: number) => {
    const order = modules.map((m) => m.id);
    const from = order.indexOf(module.id);
    order.splice(from, 1);
    order.splice(from + delta, 0, module.id);
    return act(
      () => post(`/sites/${siteId}/reorder-modules/`, { order }),
      `Moved the module “${module.title}” to place ${from + delta + 1} of ${order.length}.`,
      "Could not move the module.",
      `module-${module.id}-${delta < 0 ? "up" : "down"}`,
    );
  };

  async function addModule(e: FormEvent) {
    e.preventDefault();
    await act(() => post("/modules/", { site: siteId, title: moduleTitle }), `Added the module “${moduleTitle}”.`, "Could not add the module.");
    setModuleTitle("");
  }

  function drop(e: DragEvent, module: CourseModule, index: number) {
    e.preventDefault();
    e.stopPropagation();
    if (!dragged) return;
    const source = modules.find((m) => m.id === dragged.from);
    const item = source?.items.find((i) => i.id === dragged.item);
    setDragged(null);
    if (!source || !item) return;
    if (source.id === module.id) {
      const from = module.items.findIndex((i) => i.id === item.id);
      if (from !== index) void reorder(module, item, from < index ? index - 1 : index);
    } else void moveTo(item, module, index + 1);
  }

  if (modules.length === 0 && !teaching) return <p className="muted">No content yet.</p>;

  return (
    <div className="content-tab">
      {teaching && (
        <p className="setup-link">
          <a href={`#/sites/${siteId}/setup`}>Course setup: template, copy from another course, dates and storage</a>
          {" · "}
          <a href={`#/sites/${siteId}/transfer`}>Import or export content</a>
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <p role="status" className={status ? "notice" : "sr-only"}>
        {status}
      </p>
      {modules.length === 0 && <p className="muted">No content yet.</p>}
      {modules.map((m, mi) => {
        const done = m.items.filter((i) => i.completed).length;
        return (
          <section className="module" key={m.id} aria-labelledby={`module-${m.id}-title`}>
            <div className="module-head">
              <h2 id={`module-${m.id}-title`}>{m.title}</h2>
              {teaching && (
                <div className="module-tools">
                  <button
                    id={`module-${m.id}-up`}
                    type="button"
                    className="secondary small-button"
                    aria-label={`Move the module “${m.title}” up`}
                    disabled={mi === 0}
                    onClick={() => moveModule(m, -1)}
                  >
                    Move up
                  </button>
                  <button
                    id={`module-${m.id}-down`}
                    type="button"
                    className="secondary small-button"
                    aria-label={`Move the module “${m.title}” down`}
                    disabled={mi === modules.length - 1}
                    onClick={() => moveModule(m, 1)}
                  >
                    Move down
                  </button>
                  <button
                    type="button"
                    className="secondary small-button"
                    aria-expanded={release?.kind === "module" && release.id === m.id}
                    onClick={() => setRelease(release?.kind === "module" && release.id === m.id ? null : { kind: "module", id: m.id })}
                  >
                    When students see it
                  </button>
                </div>
              )}
            </div>
            {teaching && m.conditions && <p className="conditions">{m.conditions}</p>}
            {student && m.items.length > 0 && (
              <div className="progress-line">
                <span>
                  {done} of {m.items.length} complete
                </span>
                <span className="bar" aria-hidden="true">
                  <span style={{ width: `${Math.round((done * 100) / m.items.length)}%` }} />
                </span>
              </div>
            )}
            {m.items.length > 0 && (
              <Suspense fallback={null}>
                <ModuleDownload moduleId={m.id} title={m.title} />
              </Suspense>
            )}
            {release?.kind === "module" && release.id === m.id && (
              <ReleaseEditor
                target={{ kind: "module", record: m }}
                modules={modules}
                groups={groups}
                onSaved={onChanged}
                onClose={() => setRelease(null)}
              />
            )}
            <ol
              className="items"
              aria-label={`Items in ${m.title}`}
              onDragOver={teaching ? (e) => e.preventDefault() : undefined}
              onDrop={teaching ? (e) => drop(e, m, m.items.length) : undefined}
            >
              {m.items.length === 0 && <li className="muted small empty-module">Nothing in this module yet.</li>}
              {m.items.map((i, index) => (
                <li
                  key={i.id}
                  className={dragged?.item === i.id ? "content-item dragging" : "content-item"}
                  draggable={teaching}
                  onDragStart={teaching ? () => setDragged({ item: i.id, from: m.id }) : undefined}
                  onDragEnd={() => setDragged(null)}
                  onDragOver={teaching ? (e) => e.preventDefault() : undefined}
                  onDrop={teaching ? (e) => drop(e, m, index) : undefined}
                >
                  <div className="item-head">
                    <h3 className="item-title">
                      {i.kind === "page" ? (
                        <a href={`#/sites/${siteId}/pages/${i.id}`}>{i.title}</a>
                      ) : i.kind === "package" ? (
                        <a href={`#/sites/${siteId}/packages/${i.id}`}>{i.title}</a>
                      ) : (
                        i.title
                      )}
                    </h3>
                    {!i.is_published && <span className="pill">Draft</span>}
                    {i.under_review && <span className="pill">Under review</span>}
                    {student &&
                      (i.completed ? (
                        <span className="done-mark">Complete</span>
                      ) : i.kind === "package" ? null : (
                        <button
                          type="button"
                          className="secondary small-button"
                          aria-label={`Mark “${i.title}” complete`}
                          onClick={() => act(() => post(`/content/${i.id}/complete/`), `“${i.title}” is complete.`, "Could not record it.")}
                        >
                          Mark complete
                        </button>
                      ))}
                    {teaching && (
                      <button
                        type="button"
                        className="secondary small-button"
                        aria-expanded={open === i.id}
                        aria-label={`Change “${i.title}”`}
                        onClick={() => setOpen(open === i.id ? null : i.id)}
                      >
                        Change
                      </button>
                    )}
                  </div>
                  {teaching && i.conditions && <p className="conditions">{i.conditions}</p>}
                  {teaching && open === i.id && (
                    <div className="item-tools" role="group" aria-label={`Change “${i.title}”`}>
                      <button
                        id={focusId(i.id, "up")}
                        type="button"
                        className="secondary small-button"
                        aria-label={`Move “${i.title}” up`}
                        disabled={index === 0}
                        onClick={() => reorder(m, i, index - 1, focusId(i.id, "up"))}
                      >
                        Move up
                      </button>
                      <button
                        id={focusId(i.id, "down")}
                        type="button"
                        className="secondary small-button"
                        aria-label={`Move “${i.title}” down`}
                        disabled={index === m.items.length - 1}
                        onClick={() => reorder(m, i, index + 1, focusId(i.id, "down"))}
                      >
                        Move down
                      </button>
                      {modules.length > 1 && (
                        <span className="move-to">
                          <label>
                            Move to module
                            <select
                              value={destinations[i.id] ?? ""}
                              onChange={(e) => setDestinations((prev) => ({ ...prev, [i.id]: e.target.value }))}
                            >
                              <option value="">Choose…</option>
                              {modules
                                .filter((other) => other.id !== m.id)
                                .map((other) => (
                                  <option key={other.id} value={other.id}>
                                    {other.title}
                                  </option>
                                ))}
                            </select>
                          </label>
                          <button
                            type="button"
                            className="secondary small-button"
                            disabled={!destinations[i.id]}
                            onClick={() => moveTo(i, modules.find((other) => String(other.id) === destinations[i.id])!)}
                          >
                            Move
                          </button>
                        </span>
                      )}
                      <button
                        type="button"
                        className="secondary small-button"
                        onClick={() =>
                          act(() => post(`/content/${i.id}/duplicate/`), `Copied “${i.title}” as a draft below it.`, "Could not copy the item.")
                        }
                      >
                        Duplicate
                      </button>
                      {i.kind === "page" ? (
                        <a className="button secondary small-button" href={`#/sites/${siteId}/pages/${i.id}/edit`}>
                          Edit page
                        </a>
                      ) : i.kind === "package" ? (
                        <a className="button secondary small-button" href={`#/sites/${siteId}/packages/${i.id}`}>
                          Package settings and results
                        </a>
                      ) : (
                        <button type="button" className="secondary small-button" onClick={() => setEditing(editing === i.id ? null : i.id)}>
                          Edit details
                        </button>
                      )}
                      <button
                        type="button"
                        className="secondary small-button"
                        aria-expanded={release?.kind === "item" && release.id === i.id}
                        onClick={() => setRelease(release?.kind === "item" && release.id === i.id ? null : { kind: "item", id: i.id })}
                      >
                        When students see it
                      </button>
                      <button
                        type="button"
                        className="small-button"
                        onClick={() =>
                          act(
                            () => patch(`/content/${i.id}/`, { is_published: !i.is_published }),
                            i.is_published ? `“${i.title}” is now a draft.` : `“${i.title}” is published.`,
                            "Could not change it.",
                          )
                        }
                      >
                        {i.is_published ? "Unpublish" : "Publish"}
                      </button>
                      <a className="button secondary small-button" href={`#/library/share?item=${i.id}`}>
                        Share to the library
                      </a>
                    </div>
                  )}
                  {release?.kind === "item" && release.id === i.id && (
                    <ReleaseEditor
                      target={{ kind: "item", record: i }}
                      modules={modules}
                      groups={groups}
                      onSaved={onChanged}
                      onClose={() => setRelease(null)}
                    />
                  )}
                  {editing === i.id && i.kind !== "page" && i.kind !== "package" && (
                    <ItemForm
                      moduleId={m.id}
                      kind={i.kind}
                      item={i}
                      onCancel={() => setEditing(null)}
                      onSaved={(saved) => {
                        setEditing(null);
                        setStatus(saved.storage?.warning ?? `Saved “${saved.title}”.`);
                        onChanged();
                      }}
                    />
                  )}
                  {i.kind === "page" && <PageBody html={i.body} sizes={sizes} />}
                  {i.kind === "file" && i.download_url && (
                    <DocumentView title={i.title} filename={i.filename} url={i.download_url} size={i.file_size} />
                  )}
                  {i.kind === "video" && (
                    <Suspense fallback={<p className="loading">Opening the video…</p>}>
                      <VideoItem item={i} siteId={siteId} teaching={teaching} />
                    </Suspense>
                  )}
                  {i.kind === "link" && (
                    <p className="link-line">
                      <a href={i.url} target="_blank" rel="noopener noreferrer">
                        {isToolLaunch(i.url) ? `Open ${i.title} (outside tool, new window)` : i.url}
                      </a>
                    </p>
                  )}
                  {i.source && <p className="muted small credit">Source: {i.source}</p>}
                </li>
              ))}
            </ol>
            {teaching &&
              (adding?.module === m.id && adding.kind === "package" ? (
                <Suspense fallback={<p className="loading">Opening…</p>}>
                  <PackageForm
                    moduleId={m.id}
                    onCancel={() => setAdding(null)}
                    onSaved={(saved) => {
                      setAdding(null);
                      setStatus(saved.storage?.warning ?? `Added the package “${saved.title}”.`);
                      onChanged();
                    }}
                  />
                </Suspense>
              ) : adding?.module === m.id && adding.kind !== "package" ? (
                <ItemForm
                  moduleId={m.id}
                  kind={adding.kind}
                  onCancel={() => setAdding(null)}
                  onSaved={(saved) => {
                    setAdding(null);
                    setStatus(saved.storage?.warning ?? `Added “${saved.title}”.`);
                    onChanged();
                  }}
                />
              ) : (
                <div className="add-row">
                  <a className="button secondary" href={`#/sites/${siteId}/pages/new?module=${m.id}`}>
                    Add a page
                  </a>
                  <button type="button" className="secondary" onClick={() => setAdding({ module: m.id, kind: "file" })}>
                    Upload a file
                  </button>
                  <button type="button" className="secondary" onClick={() => setAdding({ module: m.id, kind: "link" })}>
                    Add a link
                  </button>
                  <button type="button" className="secondary" onClick={() => setAdding({ module: m.id, kind: "package" })}>
                    Add a SCORM or H5P package
                  </button>
                  <a className="button secondary" href="#/library">
                    From the library
                  </a>
                  <button type="button" className="secondary" onClick={() => setAdding({ module: m.id, kind: "video" })}>
                    Put a video up
                  </button>
                </div>
              ))}
          </section>
        );
      })}
      {teaching && (
        <form className="form-row" onSubmit={addModule}>
          <label className="grow">
            New module
            <input id="module-title" value={moduleTitle} onChange={(e) => setModuleTitle(e.target.value)} placeholder="Week 1: Soils" required />
          </label>
          <div className="actions">
            <button type="submit">Add module</button>
          </div>
        </form>
      )}
    </div>
  );
}
