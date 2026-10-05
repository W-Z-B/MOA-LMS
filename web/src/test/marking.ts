/** Fictional assignments, submissions, rubrics and gradebooks for the marking screens' tests. */

import type { Site } from "../api/types";
import type { AssignmentDetail, GradebookData, Rubric, WorkSubmission, Working } from "../api/types-marking";

export const site: Site = {
  id: 9,
  code: "AGR205-2026-27-S1-MRP",
  title: "Soil Science and Fertility",
  term_code: "2026-27-S1",
  campus_code: "MRP",
  source: "srms",
  kind: "academic",
  description: "",
  is_published: true,
  coursework_weight: "40.00",
  my_role: "lecturer",
  members: 3,
};

export const rubric: Rubric = {
  id: 4,
  site: 9,
  title: "Soil profile report rubric",
  description: "",
  kind: "scored",
  copied_from: null,
  criteria: [
    {
      id: 11,
      title: "Profile description",
      description: "",
      max_points: null,
      levels: [
        { id: 111, points: "0.00", description: "Missing" },
        { id: 112, points: "5.00", description: "Some horizons described" },
        { id: 113, points: "10.00", description: "Every horizon described" },
      ],
    },
    {
      id: 12,
      title: "Interpretation",
      description: "",
      max_points: null,
      levels: [
        { id: 121, points: "0.00", description: "None" },
        { id: 122, points: "5.00", description: "Some reasoning" },
        { id: 123, points: "10.00", description: "Clear and supported" },
      ],
    },
  ],
  max_points: "20.00",
  in_use: false,
};

export function assignment(change: Partial<AssignmentDetail> = {}): AssignmentDetail {
  return {
    id: 3,
    site: 9,
    title: "Soil profile report",
    instructions: "Describe your soil profile.",
    opens_at: null,
    due_at: "2026-10-01T14:00:00Z",
    max_mark: "20.00",
    weight: "2.00",
    allow_late: true,
    is_published: true,
    category: null,
    allow_resubmission: true,
    accepted_kinds: ["pdf"],
    max_files: 3,
    accepts: "PDF",
    upload_limit_mb: 20,
    requires_integrity: true,
    integrity_statement: "I confirm that this work is my own.",
    late_penalty: "per_day",
    late_penalty_percent: "5.00",
    late_penalty_cap: "20.00",
    is_group: false,
    groups: [],
    rubric: 4,
    rubric_detail: rubric,
    anonymous: false,
    moderation: "none",
    marks_released_at: null,
    my_due_at: null,
    my_submission: null,
    submissions_count: 2,
    ...change,
  };
}

export function submission(change: Partial<WorkSubmission> = {}): WorkSubmission {
  return {
    id: 21,
    assignment: 3,
    student_no: "S2026911",
    student_name: "Ria Ramdial",
    group: null,
    text: "",
    filename: "S2026911-profile.pdf",
    download_url: "/api/v1/submissions/21/download/",
    files: [{ id: 31, filename: "S2026911-profile.pdf", size: 2048, sha256: "ab", download_url: "/api/v1/submission-files/31/download/" }],
    submitted_at: "2026-10-02T14:00:00Z",
    client_submitted_at: null,
    is_late: true,
    due_at: "2026-10-01T14:00:00Z",
    extended: false,
    attempts: 1,
    receipt: "GSA-ABCDE-FGHJK",
    accommodation_applies: false,
    srms_locked_at: null,
    mark: null,
    feedback_files: [],
    ...change,
  };
}

export const released = {
  mark: "14.00",
  raw_mark: "15.00",
  penalty: "1.00",
  penalty_percent: "5.00",
  feedback: "Clear horizons; say more about drainage.",
  is_released: true,
  source: "rubric" as const,
  group_mark: null,
  adjustment: "0.00",
  rubric_scores: [
    { criterion: 11, level: 113, points: "10.00", comment: "" },
    { criterion: 12, level: 122, points: "5.00", comment: "Drainage?" },
  ],
};

export const book: GradebookData = {
  site: "AGR205-2026-27-S1-MRP",
  categories: [{ id: 5, name: "Reports", weight: "60.00", drop_lowest: 0 }],
  assignments: [
    { id: 3, title: "Soil profile report", max_mark: "20.00", weight: "2.00", category: 5 },
    { id: 4, title: "Blind essay", max_mark: "10.00", weight: "1.00", category: null },
  ],
  quizzes: [{ id: 7, title: "Soil quiz", weight: "1.00", counts: true, grading_method: "highest", category: null }],
  practicals: [{ id: 8, title: "Take a core", weight: "1.00", category: null }],
  forums: [{ id: 9, title: "Fertiliser debate", weight: "1.00", category: null }],
  rows: [
    {
      person_id: 101,
      student_no: "S2026911",
      name: "Ria Ramdial",
      marks: {
        "3": { submitted: true, late: true, mark: "14.00", raw_mark: "15.00", penalty: "1.00", feedback: "", anonymous: false },
        "4": { submitted: true, late: false, mark: null, raw_mark: null, penalty: null, feedback: "", anonymous: true, label: "Candidate 412345" },
      },
      quizzes: { "7": { attempts: 1, state: "graded", percent: "80.00" } },
      practicals: { "8": { state: "zero", percent: "0.00" } },
      forums: { "9": { state: "graded", percent: "90.00" } },
      categories: { "5": "70.00" },
      coursework_percent: "61.50",
      srms: { outcome: "accepted", percent: "61.50", sent_at: "2026-10-03T12:00:00Z", locked_since: "2026-10-03T12:00:00Z" },
    },
    {
      person_id: 102,
      student_no: "S2026912",
      name: "Andre Fung",
      marks: {
        "3": { submitted: false, late: false, mark: null, raw_mark: null, penalty: null, feedback: "", anonymous: false },
        "4": { submitted: false, late: false, mark: null, raw_mark: null, penalty: null, feedback: "", anonymous: true },
      },
      quizzes: { "7": { attempts: 0, state: "none", percent: null } },
      practicals: { "8": { state: "not_due", percent: null } },
      forums: { "9": { state: "pending", percent: null } },
      categories: { "5": null },
      coursework_percent: null,
      srms: null,
    },
  ],
};

export const working: Working = {
  student_no: "S2026911",
  name: "Ria Ramdial",
  coursework_percent: "61.50",
  uses_categories: true,
  categories: [
    { id: 5, name: "Reports", weight: "60.00", drop_lowest: 1, percent: "70.00", counted: true },
    { id: null, name: "Not in a category", weight: "3.00", drop_lowest: 0, percent: "56.67", counted: true },
  ],
  items: [
    {
      kind: "assignment",
      id: 3,
      title: "Soil profile report",
      category: 5,
      weight: "2.00",
      state: "graded",
      percent: "70.00",
      max_mark: "20.00",
      due_at: "2026-10-01T14:00:00Z",
      extended: true,
      late: true,
      raw_mark: "15.00",
      penalty: "1.00",
      final_mark: "14.00",
      anonymous: false,
    },
    {
      kind: "assignment",
      id: 4,
      title: "Blind essay",
      category: null,
      weight: "1.00",
      state: "pending",
      percent: null,
      max_mark: "10.00",
      due_at: "2026-10-01T14:00:00Z",
      extended: false,
      late: false,
      raw_mark: null,
      penalty: null,
      final_mark: null,
      anonymous: true,
    },
    { kind: "quiz", id: 7, title: "Soil quiz", category: null, weight: "1.00", state: "graded", percent: "80.00" },
    { kind: "practical", id: 8, title: "Take a core", category: null, weight: "1.00", state: "zero", percent: "0.00" },
    { kind: "forum", id: 9, title: "Fertiliser debate", category: null, weight: "1.00", state: "dropped", percent: "90.00" },
  ],
};

export const page = <T>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });
