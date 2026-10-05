/**
 * Hash-based routing with no dependency, as in the HRMS and across the GSA ecosystem front-ends (item 2.10).
 * Every page has an address that can be shared and bookmarked, down to a course site's tab: #/sites/4/assignments.
 */

import { useEffect, useState } from "react";
import { ADMIN_ROLES, hasAnyRole, type Me } from "../api/types";

const read = () => window.location.hash.replace(/^#/, "") || "/";

export function useHashRoute(): [string, (to: string) => void] {
  const [path, setPath] = useState<string>(read);
  useEffect(() => {
    const onChange = () => setPath(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return [path, (to: string) => (window.location.hash = to)];
}

export interface Page {
  path: string;
  label: string;
  /** What the page is for, in a few words: shown beside it in search and on Home. */
  desc: string;
  /** Who may open it; everyone when absent. */
  roles?: readonly string[];
  /** Addresses that belong to this page too, for the breadcrumb: a course site is under My courses. */
  under?: readonly string[];
  /** A placeholder for a later release: it has an address, but search does not offer it yet. */
  later?: boolean;
}

/**
 * Every page, in the order search lists them (item 2.07). There is no permanent menu: Home shows each role
 * its pages, and search finds the rest. Who may open a page is the server's rule; this only hides what the
 * server would refuse.
 */
export const PAGES: readonly Page[] = [
  { path: "/", label: "Home", desc: "Your work and your shortcuts" },
  { path: "/to-do", label: "To do", desc: "Work due, work to mark and requests waiting for you" },
  { path: "/courses", label: "My courses", desc: "Your course sites: content, assignments and marks", under: ["/sites"] },
  { path: "/my-data", label: "My data", desc: "What the LMS holds about you, and corrections" },
  { path: "/account", label: "My account", desc: "Authenticator and signed-in devices" },
  { path: "/admin", label: "Admin", desc: "Course templates, takedown requests and storage allowances", roles: ADMIN_ROLES },
];

/** The pages this person may open. */
export const pagesFor = (me: Me) => PAGES.filter((page) => !page.roles || hasAnyRole(me, page.roles));

/** The page an address belongs to: the longest page path (or path it stands for) the address starts with. */
export function pageOf(path: string): Page | undefined {
  const bare = path.split("?")[0];
  const starts = (prefix: string) => bare === prefix || bare.startsWith(`${prefix}/`);
  return PAGES.filter((page) => page.path !== "/")
    .map((page) => ({ page, length: Math.max(...[page.path, ...(page.under ?? [])].filter(starts).map((p) => p.length), -1) }))
    .filter((match) => match.length >= 0)
    .sort((a, b) => b.length - a.length)[0]?.page;
}

/** The tabs of a course site, each with an address of its own. */
export const SITE_TABS = ["content", "assignments", "gradebook", "announcements"] as const;
export type SiteTab = (typeof SITE_TABS)[number];

/** #/sites/4 or #/sites/4/gradebook: the site and its tab. A tab the screen does not have opens Content. */
export function siteAddress(path: string): { id: number; tab: SiteTab } | null {
  const match = path.match(/^\/sites\/(\d+)(?:\/([a-z-]+))?/);
  if (!match) return null;
  const tab = SITE_TABS.find((t) => t === match[2]) ?? "content";
  return { id: Number(match[1]), tab };
}

// --- content (items 2.12 to 2.20) ---

/**
 * Addresses under a course site for its pages and its setup: #/sites/4/setup, #/sites/4/pages/12 (a page as
 * students read it), #/sites/4/pages/12/edit, and #/sites/4/pages/new?module=7 for a new page in a module.
 */
export type ContentRoute =
  | { view: "setup"; siteId: number }
  | { view: "page"; siteId: number; itemId: number }
  | { view: "edit"; siteId: number; itemId: number | null; moduleId: number | null };

export function contentAddress(path: string): ContentRoute | null {
  const [bare, query = ""] = path.split("?");
  const setup = bare.match(/^\/sites\/(\d+)\/setup$/);
  if (setup) return { view: "setup", siteId: Number(setup[1]) };
  const page = bare.match(/^\/sites\/(\d+)\/pages\/(\d+|new)(\/edit)?$/);
  if (!page) return null;
  const siteId = Number(page[1]);
  if (page[2] === "new") {
    const module = new URLSearchParams(query).get("module");
    return { view: "edit", siteId, itemId: null, moduleId: module && /^\d+$/.test(module) ? Number(module) : null };
  }
  const itemId = Number(page[2]);
  return page[3] ? { view: "edit", siteId, itemId, moduleId: null } : { view: "page", siteId, itemId };
}

/** The parts of Admin with screens of their own: #/admin/templates, #/admin/takedowns, #/admin/storage. */
export type AdminPart = "home" | "templates" | "takedowns" | "storage";

export function adminAddress(path: string): AdminPart | null {
  const match = path.split("?")[0].match(/^\/admin(?:\/([a-z-]+))?$/);
  if (!match) return null;
  const part = match[1] ?? "home";
  return part === "templates" || part === "takedowns" || part === "storage" || part === "home" ? part : null;
}
// --- end content ---
