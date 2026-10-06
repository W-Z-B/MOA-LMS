/** Addresses inside a site's Practicals and Logbook tabs (item 2.10), so each screen can be shared and
 * bookmarked: #/sites/4/practicals/12/observe/55 is the checklist for one student on one task. */

export type PracticalsView =
  | { view: "tasks" }
  | { view: "task"; taskId: number }
  | { view: "observe"; taskId: number; personId: number | null }
  | { view: "competency"; personId: number | null }
  | { view: "portfolio" };

const rest = (path: string, tab: string) => {
  const match = path.split("?")[0].match(new RegExp(`^/sites/\\d+/${tab}(?:/(.*))?$`));
  return (match?.[1] ?? "").split("/").filter(Boolean);
};

const id = (part: string | undefined) => (part && /^\d+$/.test(part) ? Number(part) : null);

export function practicalsView(path: string): PracticalsView {
  const [first, second, third] = rest(path, "practicals");
  if (first === "competency") return { view: "competency", personId: id(second) };
  if (first === "portfolio") return { view: "portfolio" };
  const taskId = id(first);
  if (taskId === null) return { view: "tasks" };
  if (second === "observe") return { view: "observe", taskId, personId: id(third) };
  return { view: "task", taskId };
}

export type LogbookView = { view: "list" } | { view: "new" } | { view: "edit"; entryId: number };

export function logbookView(path: string): LogbookView {
  const [first] = rest(path, "logbook");
  if (first === "new") return { view: "new" };
  const entryId = id(first);
  return entryId === null ? { view: "list" } : { view: "edit", entryId };
}

export const practicalsPath = (siteId: number, ...parts: (string | number)[]) =>
  [`/sites/${siteId}/practicals`, ...parts].join("/");

export const logbookPath = (siteId: number, ...parts: (string | number)[]) => [`/sites/${siteId}/logbook`, ...parts].join("/");
