/** Types of the quizzes API (feature 10; items 3.01 to 3.08). They mirror api/quizzes/api.py and schemas.py. */

export type QType =
  | "multichoice"
  | "truefalse"
  | "matching"
  | "ordering"
  | "shortanswer"
  | "numerical"
  | "cloze"
  | "essay"
  | "file"
  | "image_label";

export const QTYPE_LABEL: Record<QType, string> = {
  multichoice: "Multiple choice",
  truefalse: "True or false",
  matching: "Matching",
  ordering: "Ordering",
  shortanswer: "Short answer",
  numerical: "Numerical",
  cloze: "Fill in the blanks",
  essay: "Essay",
  file: "File response",
  image_label: "Label a diagram",
};

export interface QuestionBank {
  id: number;
  name: string;
  site: number | null;
  department_code: string;
  description: string;
  owner_label: string;
  can_manage: boolean;
}

export interface QuestionCategory {
  id: number;
  bank: number;
  parent: number | null;
  name: string;
  position: number;
}

export interface QuestionVersion {
  id: number;
  number: number;
  /** As written, for editing. */
  text: string;
  /** Cleaned on the server against the course pages' allow-list: safe to place in the page. */
  text_html: string;
  data: QuestionData;
  default_mark: string;
  general_feedback: string;
  image_url: string | null;
  created_at: string;
  in_use: boolean;
}

export interface Question {
  id: number;
  bank: number;
  category: number | null;
  qtype: QType;
  name: string;
  tags: string[];
  is_archived: boolean;
  latest: QuestionVersion;
  versions_count: number;
  new_version: boolean;
}

/** A question's type-specific settings (quizzes/schemas.py). Loose on purpose: each editor knows its own. */
export type QuestionData = Record<string, any>;

export interface ImportReport {
  imported: { id: number; name: string; qtype: QType; category: string[] }[];
  skipped: { name: string; reason: string }[];
  warnings: string[];
}

export interface ExportResult {
  format: string;
  filename: string;
  content: string;
  exported: number;
  skipped: { name: string; reason: string }[];
}

export type Review = "immediately" | "after_close" | "never";

export interface MyQuizStatus {
  attempts_used: number;
  attempts_allowed: number;
  closes_at: string | null;
  time_limit_minutes: number | null;
  in_progress_attempt: number | null;
  grade_state: "graded" | "pending" | "none";
  grade_percent: string | null;
}

export interface Quiz {
  id: number;
  site: number;
  title: string;
  description: string;
  opens_at: string | null;
  closes_at: string | null;
  time_limit_minutes: number | null;
  attempts_allowed: number;
  grading_method: "highest" | "average" | "first" | "last";
  pass_mark: string | null;
  weight: string;
  is_practice: boolean;
  /** Secure exam mode (item 3.25): one attempt only, enforced on the server; the sitting is logged. */
  is_secure_exam: boolean;
  is_published: boolean;
  shuffle_questions: boolean;
  shuffle_answers: boolean;
  questions_per_page: number;
  navigation: "free" | "sequential";
  review_marks: Review;
  review_correct: Review;
  review_feedback: Review;
  auto_release: boolean;
  feedback_bands: { min_percent: number; feedback: string }[];
  max_mark: string;
  my_status: MyQuizStatus | null;
}

export interface QuizSlot {
  id: number;
  quiz: number;
  position: number;
  question: number | null;
  category: number | null;
  random_count: number;
  include_subcategories: boolean;
  tag: string;
  mark: string | null;
}

export interface QuizOverride {
  id: number;
  quiz: number;
  student: number;
  student_no: string;
  student_name: string;
  extra_minutes: number;
  extra_attempts: number;
  closes_at: string | null;
  reason: string;
}

export interface AttemptSummary {
  id: number;
  quiz: number;
  student_no: string;
  student_name: string;
  number: number;
  state: "in_progress" | "finished";
  started_at: string;
  deadline: string | null;
  submitted_at: string | null;
  auto_submitted: boolean;
  score: string | null;
  max_score: string;
  percent: string | null;
  needs_grading: boolean;
  is_released: boolean;
}

export type AnswerState = "correct" | "partial" | "incorrect" | "needs_marking";

export interface AttemptQuestion {
  position: number;
  page: number;
  qtype: QType;
  /** Cleaned HTML (server side): safe to place in the page. */
  text: string;
  image_url: string | null;
  data: QuestionData;
  max_mark: string;
  response: Record<string, any> | null;
  file_url: string | null;
  saved_at: string | null;
  /** Only when the review options allow. */
  awarded?: string | null;
  state?: AnswerState;
  feedback?: string;
  general_feedback?: string;
  comment?: string;
  right_answer?: Record<string, any> | null;
  /** Teaching staff only. */
  needs_manual?: boolean;
  marked_at?: string | null;
}

export interface Attempt {
  id: number;
  quiz: number;
  quiz_title: string;
  student_no: string;
  number: number;
  state: "in_progress" | "finished";
  server_time: string;
  started_at: string;
  deadline: string | null;
  seconds_left: number | null;
  submitted_at: string | null;
  auto_submitted: boolean;
  /** Secure exam mode (item 3.25): the deterrent banner shows, and integrity events are reported. */
  is_secure_exam: boolean;
  navigation: "free" | "sequential";
  current_page: number;
  last_page: number;
  is_released: boolean;
  needs_grading: boolean | null;
  score: string | null;
  max_score: string;
  percent: string | null;
  passed: boolean | null;
  overall_feedback: string;
  questions: AttemptQuestion[];
}

/** Kinds the server accepts from the browser's own integrity reporting (item 3.25). */
export type IntegrityEventKind = "focus_lost" | "focus_resumed" | "copy_attempted" | "paste_attempted" | "context_menu_blocked";

/** One entry in an attempt's integrity timeline, read by teaching staff (item 3.25). */
export interface IntegrityLogEntry {
  kind: IntegrityEventKind | string;
  label: string;
  at: string;
}

export interface AnswerSaved {
  position: number;
  saved: boolean;
  stale: boolean;
  server_time: string;
  seconds_left: number | null;
}

export interface MarkingItem {
  attempt: number;
  position: number;
  student_no: string;
  student_name: string;
  question: string;
  qtype: QType;
  max_mark: string;
  submitted_at: string;
}

export interface QuizStatistics {
  quiz: number;
  attempts: number;
  mean_percent: number | null;
  median_percent: number | null;
  pass_rate: number | null;
  questions: {
    question_id: number;
    name: string;
    qtype: QType;
    positions: number[];
    answered: number;
    facility_index: number;
    discrimination_index: number | null;
    responses: { response: string; count: number }[];
  }[];
}

export interface SiteMember {
  membership_id: number;
  person_id: number;
  external_id: string;
  name: string;
  role: string;
}
