/** Fictional records shared by the practicals component tests. */

import type { LogbookEntry, Observation, PracticalTask, TaskStudent } from "../../api/types-practicals";

export const task: PracticalTask = {
  id: 5,
  site: 9,
  title: "Prepare a vegetable bed",
  instructions: "Form a raised bed 1.2 m wide.",
  unit_type: "crop_plot",
  location: "Plot 7",
  weight: "2.00",
  counts_in_coursework: true,
  opens_at: null,
  closes_at: "2026-10-20T20:00:00Z",
  max_attempts: 2,
  is_published: true,
  criteria: [
    { id: 11, position: 1, text: "Bed formed to 1.2 m", kind: "pass_fail", max_score: 1, pass_score: 1, is_critical: true, performance_criteria: [] },
    { id: 12, position: 2, text: "Soil tilth", kind: "scored", max_score: 5, pass_score: 3, is_critical: false, performance_criteria: [] },
  ],
};

export const students: TaskStudent[] = [
  { person_id: 31, student_no: "S2026901", name: "Kezia Persaud", attempts: 0, attempts_left: 2, latest: null },
  {
    person_id: 32,
    student_no: "S2026902",
    name: "Tevin Joseph",
    attempts: 1,
    attempts_left: 1,
    latest: { id: 70, attempt: 1, is_released: false, critical_passed: false, score: "3 of 6" },
  },
];

export const observation: Observation = {
  id: 77,
  task: 5,
  task_title: "Prepare a vegetable bed",
  site: 9,
  student: 31,
  student_no: "S2026901",
  student_name: "Kezia Persaud",
  attempt: 1,
  assessor_name: "Marlon Bacchus",
  observed_at: "2026-10-05T14:00:00Z",
  recorded_at: "2026-10-05T14:01:00Z",
  latitude: null,
  longitude: null,
  location_text: "Plot 7",
  comments: "Good, even bed.",
  results: [
    { criterion: 11, text: "Bed formed to 1.2 m", kind: "pass_fail", is_critical: true, max_score: 1, passed: true, score: null, comment: "" },
    { criterion: 12, text: "Soil tilth", kind: "scored", is_critical: false, max_score: 5, passed: true, score: 4, comment: "Fine tilth" },
  ],
  score: { earned: 5, possible: 6 },
  critical_passed: true,
  photos: [{ id: 3, filename: "bed.jpg", download_url: "/api/v1/observation-photos/3/download/" }],
  is_released: true,
  released_at: "2026-10-05T15:00:00Z",
};

export const entry: LogbookEntry = {
  id: 40,
  site: 9,
  student_no: "S2026901",
  student_name: "Kezia Persaud",
  work_date: "2026-10-04",
  unit_type: "pond",
  unit_text: "Pond 2, tilapia",
  task: "Fed fingerlings and checked oxygen",
  hours: "2.50",
  notes: "",
  latitude: null,
  longitude: null,
  client_recorded_at: "2026-10-04T18:00:00Z",
  created_at: "2026-10-04T18:00:00Z",
  status: "pending",
  supervisor_name: null,
  reviewed_at: null,
  review_comment: "",
  photo_files: [],
};

export const page = <T>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

/** A small JPEG-looking file, as a phone's camera gives. */
export const jpeg = (name = "bed.jpg") => new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3])], name, { type: "image/jpeg" });
