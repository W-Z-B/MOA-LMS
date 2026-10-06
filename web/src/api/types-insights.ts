/**
 * Types for insight: course analytics (6.01), progress (6.02), learning outcomes (3.11), early alerts (6.05) and
 * the reports that leave a course (6.03, 6.04, 6.06). They mirror api/insights/api.py: keep in step with /api/docs.
 */

import type { ItemState } from "./types-marking";

// --- Who reads the reports (insights.reports). Others see no link to them. ---
export const COURSE_REPORT_READERS = ["administrator", "course_admin", "auditor", "registrar", "head_of_department"] as const;
export const STAFF_REPORT_READERS = ["administrator", "course_admin", "auditor", "head_of_department"] as const;
export const RULE_KEEPERS = ["administrator", "course_admin"] as const;

// --- Course analytics (item 6.01) ---

export interface ItemUse {
  id: number;
  title: string;
  module: string;
  kind: string;
  is_published: boolean;
  opened: number;
  opened_percent: string | null;
  downloads: number | null;
}

export interface AssignmentUse {
  id: number;
  title: string;
  due_at: string;
  handed_in: number;
  handed_in_percent: string | null;
  late: number;
  missing: number;
  marked: number;
  released: number;
  average_percent: string | null;
  lowest_percent: string | null;
  highest_percent: string | null;
}

export interface QuizUse {
  id: number;
  title: string;
  closes_at: string | null;
  is_practice: boolean;
  students_attempted: number;
  attempted_percent: string | null;
  attempts: number;
  average_percent: string | null;
  /** The web address of the quiz's question statistics, without the leading #. */
  statistics: string;
}

export interface Analytics {
  site: number;
  students: number;
  items: ItemUse[];
  assignments: AssignmentUse[];
  quizzes: QuizUse[];
  not_recorded: string;
}

// --- Progress (item 6.02) ---

export interface ProgressRow {
  person_id: number;
  student_no: string;
  name: string;
  items_total: number;
  items_done: number;
  items_percent: string | null;
  work_done: number;
  work_missed: number;
  work_to_come: number;
  work_marked: number;
  coursework_percent: string | null;
  last_seen: string | null;
  last_signed_in: string | null;
  /** Teaching staff only. */
  open_alerts?: number;
}

export interface WorkItem {
  kind: "assignment" | "quiz" | "practical" | "forum";
  id: number;
  title: string;
  state: ItemState;
  percent: string | null;
  due_at?: string;
}

// --- Learning outcomes (item 3.11) ---

export type StandingWord = "met" | "not_yet" | "no_evidence";

export interface Standing {
  standing: StandingWord;
  percent: string | null;
  evidence: { kind: string; title: string; percent: string }[];
}

export interface OutcomeHead {
  id: number;
  code: string;
  text: string;
  source: "srms" | "local";
  links: number;
}

export interface Standings {
  met_percent: number;
  outcomes: OutcomeHead[];
  students: { person_id: number; student_no: string; name: string; outcomes: Record<string, Standing> }[];
}

export interface StudentProgress extends ProgressRow {
  work: WorkItem[];
  outcomes: Standings;
}

export interface OutcomeLink {
  id: number;
  outcome: number;
  kind: "assignment" | "question" | "criterion";
  assignment: number | null;
  question: number | null;
  criterion: number | null;
  title: string;
}

export interface SiteOutcome {
  id: number;
  code: string;
  text: string;
  source: "srms" | "local";
  position: number;
  links: OutcomeLink[];
}

export interface SiteOutcomes {
  course_code: string;
  from_srms: boolean;
  may_add: boolean;
  outcomes: SiteOutcome[];
}

export interface EvidenceChoices {
  assignments: { id: number; title: string }[];
  questions: { id: number; title: string }[];
  criteria: { id: number; title: string }[];
}

// --- Early alerts (item 6.05) ---

export type AlertState = "open" | "acknowledged" | "acted" | "dismissed";

export interface EarlyAlert {
  id: number;
  site: number;
  student: number;
  student_no: string;
  student_name: string;
  kind: "missed_work" | "falling_marks" | "no_visits";
  kind_label: string;
  summary: string;
  evidence: { what: string; when: string | null }[];
  raised_at: string;
  state: AlertState;
  state_label: string;
  handled_by_name: string | null;
  handled_at: string | null;
  note: string;
  conversation: number | null;
}

export interface AlertRule {
  id: number;
  kind: EarlyAlert["kind"];
  label: string;
  description: string;
  threshold: number;
  window_days: number;
  is_active: boolean;
}

// --- Reports (items 6.03, 6.04, 6.06): a figure is null where its group is too small to show ---

export interface SiteReportRow {
  id: number;
  code: string;
  title: string;
  term_code: string;
  campus_code: string;
  programmes: string[];
  is_published: boolean;
  items: number;
  no_content: boolean;
  assignments: number;
  students: number | null;
  handed_in: number | null;
  marked: number | null;
  turnaround_days: string | null;
  marked_late: number | null;
  waiting_too_long: number | null;
  srms_sent: number | null;
  srms_accepted: number | null;
  srms_locked: number | null;
  srms_unknown: number | null;
  srms_last_sent: string | null;
  hidden: boolean;
}

export interface GroupReportRow {
  campus_code: string;
  programme: string;
  sites: number;
  sites_without_content: number;
  students: number | null;
  handed_in: number | null;
  marked: number | null;
  turnaround_days: string | null;
  waiting_too_long: number | null;
  srms_sent: number | null;
  hidden: boolean;
}

export interface CourseReport {
  min_group: number;
  marking_days: number;
  total: Omit<GroupReportRow, "campus_code" | "programme">;
  groups: GroupReportRow[];
  sites: SiteReportRow[];
  choices: { campuses: string[]; programmes: string[]; terms: string[] };
}

export interface UnitReportRow {
  unit_code: string;
  staff: number | null;
  completions: number | null;
  required: number | null;
  required_done: number | null;
  overdue: number | null;
  hidden: boolean;
}

export interface StaffReport {
  min_group: number;
  since: string | null;
  total: Omit<UnitReportRow, "unit_code">;
  units: UnitReportRow[];
  courses: { site: number; title: string; code: string; completions: number | null; hidden: boolean }[];
}
