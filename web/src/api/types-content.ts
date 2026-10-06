/**
 * Types for teaching content and course administration (api/courses, items 2.12 to 2.20). They mirror the
 * serializers in courses/api.py; keep them in step with /api/docs.
 */

import type { Announcement, Licence, Site } from "./types";

/** One problem the accessibility check found in a page (courses.richtext.check). */
export interface AccessibilityIssue {
  code: string;
  detail: string;
  /** "error" refuses the save; "warning" is saved and reported. */
  severity: "error" | "warning";
}

/** A site's storage use (courses.storage.summary); a warning in words from 80%. */
export interface StorageSummary {
  used_bytes: number;
  allowance_bytes: number;
  percent: number;
  warning: string | null;
  largest_files?: { id: number; title: string; module: string; filename: string; file_size: number }[];
}

/** The release conditions shared by modules and items (item 2.16). */
export interface Released {
  available_from: string | null;
  requires_item: number | null;
  groups: number[];
  /** The conditions in words, for teaching staff; null for everyone else or when there are none. */
  conditions: string | null;
}

export interface Item extends Released {
  id: number;
  module: number;
  kind: "page" | "file" | "link" | "package";
  title: string;
  /** A page's text: HTML cleaned on the server against an allow-list (courses.richtext). */
  body: string;
  filename: string | null;
  file_size: number;
  download_url: string | null;
  url: string;
  position: number;
  is_published: boolean;
  /** Whether the person asking has completed it (a student's own progress). */
  completed: boolean;
  licence: Licence;
  open_licence: string;
  source: string;
  under_review: boolean;
  /** After a save: what the accessibility check found. Null otherwise. */
  accessibility_issues: AccessibilityIssue[] | null;
  /** After a file was saved: the site's storage use. Null otherwise. */
  storage: StorageSummary | null;
}

export interface CourseModule extends Released {
  id: number;
  site: number;
  title: string;
  position: number;
  items: Item[];
}

/** GET /sites/{id}/contents/ with the fields this area reads. */
export interface Contents {
  site: Site & { storage_allowance_mb: number | null };
  modules: CourseModule[];
  announcements: Announcement[];
}

export interface SiteGroup {
  id: number;
  site: number;
  name: string;
  members: number[];
}

/** One dated thing on a site, for the date manager (item 2.18). */
export interface DatedThing {
  kind: "module" | "item" | "assignment";
  id: number;
  title: string;
  field: "available_from" | "opens_at" | "due_at";
  value: string | null;
}

export interface CopyDone {
  modules: number;
  items: number;
  assignments: number;
  offset_days: number;
  missing_files: string[];
  left_out: string[];
}

export interface TemplatePage {
  kind?: "page";
  title: string;
  body?: string;
}

export interface SiteTemplate {
  id: number;
  name: string;
  description: string;
  structure: { modules: { title: string; items?: TemplatePage[] }[] };
  is_default: boolean;
}

export interface Takedown {
  id: number;
  item: number;
  item_title: string;
  site: number;
  reason: string;
  status: "open" | "withdrawn" | "restored";
  created_at: string;
  reviewed_at: string | null;
  review_note: string;
}

/** Sizes as people read them: 1.4 GB, 320 MB, 12 KB. */
export function sizeInWords(bytes: number): string {
  const mb = 1024 * 1024;
  if (bytes >= 1024 * mb) return `${(bytes / (1024 * mb)).toFixed(1).replace(/\.0$/, "")} GB`;
  if (bytes >= mb) return `${Math.round(bytes / mb)} MB`;
  return bytes > 0 ? `${Math.max(Math.floor(bytes / 1024), 1)} KB` : "nothing";
}

/** What kind of document a file is, by its name: shown in the page (item 2.14) or only downloaded. */
export function documentKind(filename: string | null): "pdf" | "image" | "other" {
  const name = (filename ?? "").toLowerCase();
  if (name.endsWith(".pdf")) return "pdf";
  if (/\.(jpe?g|png|webp)$/.test(name)) return "image";
  return "other";
}
