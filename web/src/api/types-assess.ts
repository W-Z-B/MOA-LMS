/**
 * The shapes of the similarity check (3.20), paper quizzes (3.24), peer review (4.13) and open short courses
 * (5.07), as the API sends them (api/similarity, api/paperquizzes, api/peerreview, api/opencourses).
 */

import type { Rubric, RubricScore } from "./types-marking";

// --- similarity (item 3.20) ---

export interface SimilarOther {
  /** True when the reader teaches on the other work's course too: only then is it named. */
  known: boolean;
  label: string;
  year: number;
  site: string | null;
  assignment: string | null;
  student: string | null;
  submission: number | null;
}

export interface SimilarPassage {
  mine: string;
  theirs: string;
  words: number;
}

export interface SimilarityMatch {
  id: number;
  percent: string;
  shared_words: number;
  other: SimilarOther;
  passages: SimilarPassage[];
}

export type SimilarityStatus = "not_checked" | "waiting" | "done" | "no_text" | "failed";

export interface SimilarityReport {
  status: SimilarityStatus;
  statement: string;
  overall_percent: string | null;
  word_count: number;
  attempt_number: number | null;
  checked_at: string | null;
  notes: string[];
  matches: SimilarityMatch[];
}

// --- peer review (item 4.13) ---

export interface PeerSetup {
  reviews_each: number;
  reviews_due_at: string;
  self_assessment: boolean;
  peer_weight: string;
  allocated_at: string | null;
  released_at: string | null;
}

export interface PeerReviewRow {
  id: number;
  reviewer: string;
  is_self: boolean;
  submitted_at: string | null;
  mark: string | null;
  scores: RubricScore[];
  comment: string;
  moderation: "counts" | "left_out";
  moderation_note: string;
}

export interface PeerWorkRow {
  submission: number;
  label: string;
  peer_mark: string | null;
  override: string | null;
  self_mark: string | null;
  staff_mark: string | null;
  mark: string | null;
  reviews: PeerReviewRow[];
}

export interface PeerStaffView {
  setup: PeerSetup | null;
  rubric: boolean;
  work: PeerWorkRow[];
}

export interface PeerTask {
  id: number;
  label: string;
  is_self: boolean;
  submitted_at: string | null;
  mark: string | null;
}

export interface PeerReceived {
  label: string;
  is_self: boolean;
  mark: string | null;
  scores: RubricScore[];
  comment: string;
}

export interface PeerStudentView {
  setup: PeerSetup | null;
  to_do: PeerTask[];
  received: PeerReceived[] | null;
}

export interface PeerWork {
  id: number;
  label: string;
  is_self: boolean;
  assignment: string;
  max_mark: string;
  reviews_due_at: string;
  open: boolean;
  text: string;
  files: { id: number; filename: string; download_url: string }[];
  /** Null when the rubric was taken off the assignment after peer review was set up. */
  rubric: Rubric | null;
  scores: RubricScore[];
  mark: string | null;
  comment: string;
  submitted_at: string | null;
}

/** The assignment's own summary of its peer review (AssignmentDetail.peer_review). */
export interface PeerSummary {
  reviews_due_at: string;
  allocated: boolean;
  released: boolean;
}

// --- paper quizzes (item 3.24) ---

export interface Paper {
  id: number;
  quiz: number;
  title: string;
  sat_on: string;
  versions: string[];
  questions: number;
  keyed: number;
}

export interface PaperColumn {
  number: number;
  qtype: string;
  hint: string;
}

export interface PaperGridRow {
  student_no: string;
  name: string;
  version: string;
  answers: string[];
  attempt: number | null;
  score: string | null;
  max_score: string | null;
  needs_marking: boolean;
}

export interface PaperGrid extends Paper {
  columns: Record<string, PaperColumn[]>;
  rows: PaperGridRow[];
}

export interface KeyedResult {
  saved: number;
  errors: { student_no: string; detail: string }[];
}

// --- open short courses (item 5.07) ---

export interface OpenCourse {
  id: number;
  code: string;
  title: string;
  summary: string;
  audience: string;
  length_hours: string | null;
  places_left: number | null;
  joined: boolean;
  certificate: boolean;
}

export interface OpenCatalogue {
  courses: OpenCourse[];
  privacy_notice: { version: number; title: string; body: string } | null;
}
