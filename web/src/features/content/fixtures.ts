/** Fictional course content for the component tests of this folder. */

import type { SiteContents } from "../../api/types";
import type { Contents, CourseModule, Item } from "../../api/types-content";

export function item(id: number, module: number, title: string, more: Partial<Item> = {}): Item {
  return {
    id,
    module,
    kind: "page",
    title,
    body: `<p>${title} text</p>`,
    filename: null,
    file_size: 0,
    download_url: null,
    url: "",
    position: id,
    is_published: true,
    available_from: null,
    requires_item: null,
    groups: [],
    conditions: null,
    completed: false,
    licence: "gsa_own",
    open_licence: "",
    source: "",
    under_review: false,
    accessibility_issues: null,
    storage: null,
    ...more,
  };
}

export function module(id: number, title: string, items: Item[], more: Partial<CourseModule> = {}): CourseModule {
  return { id, site: 9, title, position: id, available_from: null, requires_item: null, groups: [], conditions: null, items, ...more };
}

export function contents(modules: CourseModule[], role: "lecturer" | "student" = "lecturer"): Contents {
  return {
    site: {
      id: 9,
      code: "AGR101-2026-27-S1-MRP",
      title: "Introduction to Crop Production",
      term_code: "2026-27-S1",
      campus_code: "MRP",
      source: "local",
      kind: "academic",
      description: "",
      is_published: true,
      coursework_weight: "40.00",
      storage_allowance_mb: null,
      my_role: role,
      members: 3,
    },
    modules,
    announcements: [],
  };
}

/** The same, typed as the course site screen holds it. */
export const asSite = (c: Contents) => c as unknown as SiteContents;
