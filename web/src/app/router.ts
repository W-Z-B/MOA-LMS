/**
 * Hash-based routing with no dependency, as in the HRMS and across the GSA ecosystem front-ends (item 2.10).
 * Every page has an address that can be shared and bookmarked, down to a course site's tab: #/sites/4/assignments.
 */

import { useEffect, useState } from "react";
import { hasAnyRole, type Me } from "../api/types";
import { CONSOLE_ROLES, usesLearning } from "../api/types-staff";

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
  /** Who may open it, when that is more than a role: staff development is for members of staff. */
  for?: (me: Me) => boolean;
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
  { path: "/account", label: "My account", desc: "Password, sign-in email and signed-in devices" },
  // --- staff development and the console ---
  {
    path: "/learning",
    label: "Staff development",
    desc: "Courses to join, learning paths, required training and certificates",
    for: usesLearning,
    under: ["/staff-development", "/certificates"],
  },
  { path: "/admin", label: "Admin", desc: "Accounts, audit log, integration runs, privacy and access review", roles: CONSOLE_ROLES },
];

/** The pages this person may open. */
export const pagesFor = (me: Me) =>
  PAGES.filter((page) => (!page.roles || hasAnyRole(me, page.roles)) && (!page.for || page.for(me)));

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
