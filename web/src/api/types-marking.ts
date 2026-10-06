/**
 * Types for assignments, marking, rubrics and the gradebook (features 9, 11, 12, 13, 16, 17, 18). They mirror
 * the serializers of api/assessments, api/rubrics and api/notifications; keep in step with /api/docs.
 */

import type { PeerSummary } from "./types-assess";

export type LatePenalty = "none" | "per_day" | "per_hour";
export type Moderation = "none" | "sample" | "double";
export type RubricKind = "scored" | "descriptive" | "guide";
/** File kinds a submission may be (core.uploads). */
export const FILE_KINDS = [
  ["pdf", "PDF"],
  ["jpeg", "JPG"],
  ["png", "PNG"],
  ["webp", "WebP"],
  ["heic", "HEIC"],
  ["docx", "Word (.docx)"],
  ["xlsx", "Excel (.xlsx)"],
  ["pptx", "PowerPoint (.pptx)"],
] as const;
export type FileKind = (typeof FILE_KINDS)[number][0];

export interface StoredFile {
  id: number;
  filename: string;
  size: number;
  sha256: string;
  download_url: string;
}

export interface FeedbackFile {
  id: number;
  filename: string;
  kind: string;
  is_audio: boolean;
  size: number;
  download_url: string;
}

export interface RubricScore {
  criterion: number;
  level: number | null;
  points: string | null;
  comment: string;
}

export interface MarkShown {
  /** The mark that counts, after any late penalty. */
  mark: string;
  raw_mark: string;
  penalty: string;
  penalty_percent: string;
  feedback: string;
  is_released: boolean;
  source: "manual" | "rubric" | "upload" | "group" | "agreed";
  group_mark: string | null;
  adjustment: string;
  rubric_scores: RubricScore[];
}

export interface WorkSubmission {
  id: number;
  assignment: number;
  /** The student number, or the pseudonym while anonymous marking hides names. */
  student_no: string;
  student_name: string;
  group: string | null;
  text: string;
  filename: string | null;
  download_url: string | null;
  files: StoredFile[];
  submitted_at: string;
  client_submitted_at: string | null;
  is_late: boolean;
  due_at: string;
  extended: boolean;
  attempts: number;
  receipt: string | null;
  /** Markers only: that an accommodation applies, never why. Null for the student. */
  accommodation_applies: boolean | null;
  /** When the SRMS took the coursework: the mark is locked from then. */
  srms_locked_at: string | null;
  mark: MarkShown | null;
  feedback_files: FeedbackFile[];
}

export interface Level {
  id?: number;
  points: string;
  description: string;
}

export interface Criterion {
  id?: number;
  title: string;
  description: string;
  max_points: string | null;
  levels: Level[];
}

export interface Rubric {
  id: number;
  site: number | null;
  title: string;
  description: string;
  kind: RubricKind;
  copied_from: number | null;
  criteria: Criterion[];
  max_points: string;
  in_use: boolean;
}

export interface AssignmentDetail {
  id: number;
  site: number;
  title: string;
  instructions: string;
  opens_at: string | null;
  due_at: string;
  max_mark: string;
  weight: string;
  allow_late: boolean;
  is_published: boolean;
  category: number | null;
  allow_resubmission: boolean;
  accepted_kinds: FileKind[];
  max_files: number;
  /** What files are accepted, in words. */
  accepts: string;
  upload_limit_mb: number;
  requires_integrity: boolean;
  integrity_statement: string | null;
  late_penalty: LatePenalty;
  late_penalty_percent: string;
  late_penalty_cap: string | null;
  is_group: boolean;
  groups: number[];
  rubric: number | null;
  rubric_detail: Rubric | null;
  anonymous: boolean;
  moderation: Moderation;
  marks_released_at: string | null;
  my_due_at: string | null;
  my_submission: WorkSubmission | null;
  submissions_count: number | null;
  /** Peer review (item 4.13): its dates and state, or null when the assignment has none. */
  peer_review?: PeerSummary | null;
}

export interface Attempt {
  number: number;
  submitted_at: string;
  client_submitted_at: string | null;
  submitted_by: string;
  is_late: boolean;
  receipt: string;
  content_hash: string;
  integrity_accepted: boolean;
  text: string;
  files: StoredFile[];
  is_marked_attempt: boolean;
}

export interface ModerationState {
  first_mark: string | null;
  second_mark: string | null;
  second_note: string;
  agreed_mark: string | null;
  agreed_note: string;
  agreed_at: string | null;
}

export interface History {
  submission: number;
  attempts: Attempt[];
  marks: {
    mark: string;
    feedback: string;
    is_released: boolean;
    source: string;
    rubric_scores: RubricScore[];
    changed_by: string | null;
    changed_at: string;
  }[];
  moderation: ModerationState | null;
}

export interface Receipt {
  receipt: string;
  site: string;
  assignment: string;
  student_no: string;
  attempt: number;
  submitted_at: string;
  is_late: boolean;
  content_hash: string;
  files: StoredFile[];
}

export interface Neighbours {
  position: number;
  total: number;
  previous: number | null;
  next: number | null;
  previous_unmarked: number | null;
  next_unmarked: number | null;
}

export interface UploadRow {
  line: number;
  student_no: string;
  mark: string | null;
  feedback: string;
  outcome: string;
  detail: string;
}

export interface UploadResult {
  applied: boolean;
  token: string;
  rows: UploadRow[];
  refused: number;
  to_save: number;
}

export interface Extension {
  id: number;
  assignment: number;
  student: number | null;
  student_no: string | null;
  group: number | null;
  due_at: string;
  reason: string;
  granted_by: number | null;
}

export interface Member {
  membership_id: number;
  person_id: number;
  external_id: string;
  name: string;
  role: string;
}

export interface GroupChoice {
  id: number;
  name: string;
}

export interface GradeCategory {
  id: number;
  site: number;
  name: string;
  weight: string;
  drop_lowest: number;
  position: number;
}

export type ItemState = "graded" | "zero" | "pending" | "not_due" | "dropped";

export interface GradebookColumn {
  id: number;
  title: string;
  weight: string;
  category: number | null;
}

export interface SrmsState {
  outcome: "accepted" | "locked" | "unknown";
  percent: string;
  sent_at: string;
  locked_since: string | null;
}

export interface GradebookRow {
  person_id: number;
  student_no: string;
  name: string;
  marks: Record<
    string,
    {
      submitted: boolean;
      late: boolean;
      mark: string | null;
      raw_mark: string | null;
      penalty: string | null;
      feedback: string;
      anonymous: boolean;
      label?: string;
    }
  >;
  quizzes: Record<string, { attempts: number; state: string; percent: string | null }>;
  practicals: Record<string, { state: ItemState; percent: string | null }>;
  forums: Record<string, { state: ItemState; percent: string | null }>;
  categories: Record<string, string | null>;
  coursework_percent: string | null;
  srms: SrmsState | null;
}

export interface GradebookData {
  site: string;
  categories: { id: number; name: string; weight: string; drop_lowest: number }[];
  assignments: (GradebookColumn & { max_mark: string })[];
  quizzes: (GradebookColumn & { counts: boolean; grading_method: string })[];
  practicals: GradebookColumn[];
  forums: GradebookColumn[];
  rows: GradebookRow[];
}

export interface WorkingItem {
  kind: "assignment" | "quiz" | "practical" | "forum";
  id: number;
  title: string;
  category: number | null;
  weight: string;
  state: ItemState;
  percent: string | null;
  max_mark?: string;
  due_at?: string;
  extended?: boolean;
  late?: boolean;
  raw_mark?: string | null;
  penalty?: string | null;
  final_mark?: string | null;
  /** Pending because marking is anonymous and the marks are not released. */
  anonymous?: boolean;
}

export interface Working {
  student_no: string;
  name: string;
  coursework_percent: string | null;
  uses_categories: boolean;
  categories: { id: number | null; name: string; weight: string; drop_lowest: number; percent: string | null; counted: boolean }[];
  items: WorkingItem[];
}

export interface CourseworkSent {
  site: string;
  sent_at: string;
  accepted: string[];
  locked: string[];
  unknown: string[];
  students: { student_no: string; percent: string; outcome: "accepted" | "locked" | "unknown" }[];
}

export interface Accommodation {
  id: number;
  person: number;
  student_no: string;
  extra_time_percent: number;
  extra_days: number;
  other_format: string;
  reason: string;
  is_active: boolean;
}

export type EmailChoice = "instant" | "daily" | "off";

export interface NotificationPreference {
  kind: string;
  label: string;
  in_app: boolean;
  email: EmailChoice;
  push: boolean;
}
