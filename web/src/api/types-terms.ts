/** The term calendar and the term life-cycle of course sites (item 7.12). */

export type TermPhase = "upcoming" | "teaching" | "ended" | "grace" | "closed" | "archived";
export type SitePhase = "open" | "grace" | "closed" | "archived";

export interface Term {
  id: number;
  code: string;
  name: string;
  starts_on: string;
  ends_on: string;
  closes_on: string;
  grace_days: number | null;
  grace_days_applied: number;
  source: "srms" | "local";
  source_name: string;
  phase: TermPhase;
  locks_at: string;
  archive_due_on: string;
  closed_at: string | null;
  archived_at: string | null;
  site_count: number;
}

export interface TermSite {
  id: number;
  code: string;
  title: string;
  phase: SitePhase;
  archive: number | null;
  archive_size: number | null;
  archive_made_at: string | null;
}

export interface MissingTerm {
  term_code: string;
  sites: number;
}

/** What each phase means, in the words the screen uses. */
export const TERM_PHASE: Record<TermPhase, string> = {
  upcoming: "Not started",
  teaching: "Teaching",
  ended: "Teaching over, taking work",
  grace: "In the grace after closing",
  closed: "Closed, read-only for appeals",
  archived: "Archived",
};

export const SITE_PHASE: Record<SitePhase, string> = {
  open: "Open",
  grace: "In the grace",
  closed: "Closed, read-only",
  archived: "Archived",
};
