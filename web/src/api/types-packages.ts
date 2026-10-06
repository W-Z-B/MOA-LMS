/**
 * Types for packaged content (SCORM and H5P, items 5.12 and 5.13), the statement store (item 6.09), the shared
 * content library (item 5.14) and course interchange (item 6.08). They mirror packages/api.py, library/api.py
 * and interchange/api.py; keep them in step with /api/docs.
 */

import type { Licence } from "./types";

export type Standard = "scorm12" | "scorm2004" | "h5p";

export const STANDARD_NAME: Record<Standard, string> = { scorm12: "SCORM 1.2", scorm2004: "SCORM 2004", h5p: "H5P" };

export interface Sco {
  id: string;
  title: string;
  href: string;
  parameters: string;
}

export interface PackageAttempt {
  id: number;
  number: number;
  registration: string;
  is_preview: boolean;
  learner: string | null;
  student_no: string | null;
  completion: "not_attempted" | "incomplete" | "completed";
  success: "unknown" | "passed" | "failed";
  score: string | null;
  score_percent: string | null;
  created_at: string;
  last_commit_at: string | null;
  completed_at: string | null;
}

export interface ContentPackage {
  id: number;
  item: number;
  title: string;
  site: number;
  module: number;
  is_published: boolean;
  licence: Licence;
  source: string;
  standard: Standard;
  version_label: string;
  scos: Sco[];
  entries: number;
  unpacked_bytes: number;
  weight: string;
  grade_category: number | null;
  max_attempts: number;
  my_attempts: PackageAttempt[];
  attempts_left: number | null;
  my_result: { fraction: string | null; state: "graded" | "not_due" };
  /** The package's xAPI activity id (item 6.09). */
  activity: string;
}

/** POST /packages/{id}/launch/ */
export interface Launched {
  attempt: PackageAttempt;
  sco: Sco;
  standard: Standard;
  play_url: string;
  commit_url: string;
  cmi: Record<string, unknown>;
  activity: string;
  registration: string;
}

export const COMPLETION_WORDS: Record<PackageAttempt["completion"], string> = {
  not_attempted: "Not started",
  incomplete: "Started",
  completed: "Completed",
};

export const SUCCESS_WORDS: Record<PackageAttempt["success"], string> = {
  unknown: "",
  passed: "Passed",
  failed: "Not passed",
};

/** One stored xAPI statement, as the LMS keeps it. */
export interface Statement {
  id: string;
  verb: { id: string; display?: Record<string, string> };
  object: { id: string; definition?: { name?: Record<string, string> } };
  actor: { account?: { name: string } };
  result?: { score?: { scaled?: number; raw?: number; max?: number }; success?: boolean; completion?: boolean };
  timestamp: string;
  stored: string;
}

export type LibraryKind = "page" | "file" | "link" | "package";

export interface LibraryItem {
  id: number;
  kind: LibraryKind;
  title: string;
  description: string;
  body: string;
  filename: string;
  file_size: number;
  download_url: string | null;
  url: string;
  package: { standard?: Standard; version_label?: string };
  licence: Licence;
  open_licence: string;
  source: string;
  publisher: string;
  department_code: string;
  is_open_resource: boolean;
  tags: string[];
  shared_from: number | null;
  may_change: boolean;
  created_at: string;
}

export interface SharedBank {
  id: number;
  name: string;
  department_code: string;
  questions: number;
  licence: Licence | null;
  open_licence: string;
  source: string;
  publisher: string;
  copied_from: number | null;
}

export interface ImportReport {
  format: "common_cartridge" | "moodle_backup";
  modules: number;
  items: number;
  questions: number;
  imported: { kind: string; title: string; module: string }[];
  skipped: { title: string; reason: string }[];
  warnings: string[];
}

export const LICENCE_WORDS: Record<Licence, string> = {
  gsa_own: "GSA's own material",
  open_licence: "Under an open licence",
  fair_dealing: "Used under fair dealing",
  permission_held: "Used with the owner's permission",
  unknown: "Not yet known",
};

export const OPEN_LICENCE_WORDS: Record<string, string> = {
  cc_by: "CC BY",
  cc_by_sa: "CC BY-SA",
  cc_by_nc: "CC BY-NC",
  cc0: "CC0",
  other: "Another open licence",
};
