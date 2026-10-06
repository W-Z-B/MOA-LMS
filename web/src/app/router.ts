/**
 * Hash-based routing with no dependency, as in the HRMS and across the GSA ecosystem front-ends (item 2.10).
 * Every page has an address that can be shared and bookmarked, down to a course site's tab: #/sites/4/assignments.
 */

import { useEffect, useState } from "react";
import { ADMIN_ROLES, hasAnyRole, type Me } from "../api/types";
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
  // --- talk: forums, messages and the calendar (items 4.08 to 4.11, 2.32) ---
  { path: "/messages", label: "Messages", desc: "Conversations with your teaching staff, and notices" },
  { path: "/calendar", label: "Calendar", desc: "Due dates, classes and releases, and a feed for your phone" },
  { path: "/forums", label: "Discussion", desc: "The forums of your courses" },
  // --- end talk ---
  { path: "/my-data", label: "My data", desc: "What the LMS holds about you, and corrections" },
  { path: "/account", label: "My account", desc: "Password, sign-in email and signed-in devices" },
  // --- marking ---
  { path: "/notification-settings", label: "Notification settings", desc: "What comes by email, and the daily summary" },
  { path: "/rubrics", label: "Rubric library", desc: "The GSA rubrics every course may copy", roles: ADMIN_ROLES },
  { path: "/accommodations", label: "Accommodations", desc: "Extra time and other arrangements for students", roles: ADMIN_ROLES },
  // --- end marking ---
  // --- staff development and the console ---
  {
    path: "/learning",
    label: "Staff development",
    desc: "Courses to join, learning paths, required training and certificates",
    for: usesLearning,
    under: ["/staff-development", "/certificates"],
  },
  { path: "/admin", label: "Admin", desc: "Accounts, audit log, integration runs, privacy, access review and course administration", roles: [...new Set([...CONSOLE_ROLES, ...ADMIN_ROLES])] },
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
export const SITE_TABS = [
  "content",
  "assignments",
  "gradebook",
  "quizzes",
  "announcements",
  "discussion",
  "classes",
  "groups",
  // --- practicals --- (items 3.12 to 3.15): each has addresses below it, #/sites/4/practicals/12/observe
  "practicals",
  "logbook",
  // --- insight --- (items 6.01, 6.02, 3.11, 6.05): Insights for teaching staff, My progress for students
  "insights",
  "progress",
] as const;
export type SiteTab = (typeof SITE_TABS)[number];

/** #/sites/4 or #/sites/4/gradebook: the site and its tab. A tab the screen does not have opens Content. */
export function siteAddress(path: string): { id: number; tab: SiteTab } | null {
  const match = path.match(/^\/sites\/(\d+)(?:\/([a-z-]+))?/);
  if (!match) return null;
  const tab = SITE_TABS.find((t) => t === match[2]) ?? "content";
  return { id: Number(match[1]), tab };
}

// --- marking ---
/** Pages inside a course site beyond its tabs: #/sites/4/assignments/12/marking/55 and #/sites/4/rubrics. */
export type MarkingAddress =
  | { kind: "marking"; siteId: number; assignmentId: number; submissionId: number | null }
  | { kind: "site-rubrics"; siteId: number };

export function markingAddress(path: string): MarkingAddress | null {
  const bare = path.split("?")[0];
  const marking = bare.match(/^\/sites\/(\d+)\/assignments\/(\d+)\/marking(?:\/(\d+))?\/?$/);
  if (marking)
    return { kind: "marking", siteId: Number(marking[1]), assignmentId: Number(marking[2]), submissionId: marking[3] ? Number(marking[3]) : null };
  const rubrics = bare.match(/^\/sites\/(\d+)\/rubrics\/?$/);
  return rubrics ? { kind: "site-rubrics", siteId: Number(rubrics[1]) } : null;
}
// --- end marking ---
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

// --- talk: addresses inside forums, messages and a site's classes (items 4.08 to 4.15) ---

/** #/forums/3 or #/forums/3/threads/7: a forum, and a thread in it. #/forums alone lists every forum. */
export function forumAddress(path: string): { forum: number | null; thread: number | null } | null {
  const match = path.split("?")[0].match(/^\/forums(?:\/(\d+)(?:\/threads\/(\d+))?)?\/?$/);
  if (!match) return null;
  return { forum: match[1] ? Number(match[1]) : null, thread: match[2] ? Number(match[2]) : null };
}

/** #/messages or #/messages/12: the conversations, and one of them. */
export function messageAddress(path: string): { conversation: number | null } | null {
  const match = path.split("?")[0].match(/^\/messages(?:\/(\d+))?\/?$/);
  if (!match) return null;
  return { conversation: match[1] ? Number(match[1]) : null };
}

/** #/sites/4/classes/9 opens one class; #/sites/4/classes/9/code shows its check-in code in the room. */
export function classAddress(path: string): { session: number; code: boolean } | null {
  const match = path.split("?")[0].match(/^\/sites\/\d+\/classes\/(\d+)(\/code)?\/?$/);
  return match ? { session: Number(match[1]), code: Boolean(match[2]) } : null;
}
// --- end talk ---

// --- quizzes ---
/**
 * Inside a site's Quizzes tab (feature 10), every view has an address too:
 * #/sites/4/quizzes                       the quizzes of the site
 * #/sites/4/quizzes/banks                 question banks (teaching staff)
 * #/sites/4/quizzes/12                    one quiz; teaching staff also /settings, /questions, /students,
 *                                         /marking, /results and /statistics
 * #/sites/4/quizzes/12/attempts/30        an attempt: answering it, or its review
 */
export const QUIZ_SECTIONS = ["settings", "questions", "students", "marking", "results", "statistics"] as const;
export type QuizSection = (typeof QUIZ_SECTIONS)[number];

export type QuizView =
  | { view: "list" }
  | { view: "banks" }
  | { view: "quiz"; quizId: number; section: QuizSection }
  | { view: "attempt"; quizId: number; attemptId: number };

export function quizAddress(path: string): QuizView {
  const rest = path.split("?")[0].match(/^\/sites\/\d+\/quizzes(?:\/(.*))?$/)?.[1] ?? "";
  if (rest === "banks") return { view: "banks" };
  const attempt = rest.match(/^(\d+)\/attempts\/(\d+)$/);
  if (attempt) return { view: "attempt", quizId: Number(attempt[1]), attemptId: Number(attempt[2]) };
  const quiz = rest.match(/^(\d+)(?:\/([a-z]+))?$/);
  if (quiz) return { view: "quiz", quizId: Number(quiz[1]), section: QUIZ_SECTIONS.find((s) => s === quiz[2]) ?? "settings" };
  return { view: "list" };
}
// --- end quizzes ---

// --- insight ---
/** The parts of a site's Insights tab: #/sites/4/insights, /insights/progress, /insights/outcomes, /insights/alerts. */
export const INSIGHTS_SECTIONS = ["overview", "progress", "outcomes", "alerts"] as const;
export type InsightsSection = (typeof INSIGHTS_SECTIONS)[number];

export function insightsSection(path: string): InsightsSection {
  const part = path.split("?")[0].match(/^\/sites\/\d+\/insights\/([a-z]+)\/?$/)?.[1];
  return INSIGHTS_SECTIONS.find((s) => s === part) ?? "overview";
}
// --- end insight ---
