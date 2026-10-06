/** Fictional data for the insight screens' tests, in the shapes of api/insights/api.py. */

import type {
  AlertRule,
  Analytics,
  CourseReport,
  EarlyAlert,
  EvidenceChoices,
  ProgressRow,
  SiteOutcomes,
  StaffReport,
  Standings,
  StudentProgress,
} from "../api/types-insights";

export const analytics: Analytics = {
  site: 9,
  students: 2,
  items: [
    { id: 1, title: "Soil horizons", module: "Week 1", kind: "page", is_published: true, opened: 1, opened_percent: "50.0", downloads: null },
    { id: 2, title: "Field handout", module: "Week 1", kind: "file", is_published: false, opened: 0, opened_percent: "0.0", downloads: 3 },
  ],
  assignments: [
    {
      id: 5,
      title: "Soil profile report",
      due_at: "2026-10-01T16:00:00Z",
      handed_in: 1,
      handed_in_percent: "50.0",
      late: 1,
      missing: 1,
      marked: 1,
      released: 0,
      average_percent: "80.0",
      lowest_percent: "80.0",
      highest_percent: "80.0",
    },
  ],
  quizzes: [
    {
      id: 7,
      title: "Soils quiz",
      closes_at: null,
      is_practice: true,
      students_attempted: 1,
      attempted_percent: "50.0",
      attempts: 2,
      average_percent: "75.0",
      statistics: "/sites/9/quizzes/7/statistics",
    },
  ],
  not_recorded: "Time spent on a page is not recorded.",
};

const row = (over: Partial<ProgressRow>): ProgressRow => ({
  person_id: 101,
  student_no: "S2026911",
  name: "Ria Ramdial",
  items_total: 4,
  items_done: 3,
  items_percent: "75.0",
  work_done: 2,
  work_missed: 1,
  work_to_come: 1,
  work_marked: 2,
  coursework_percent: "61.50",
  last_seen: "2026-10-04T10:00:00Z",
  last_signed_in: "2026-10-05T08:00:00Z",
  open_alerts: 1,
  ...over,
});

export const progress: ProgressRow[] = [
  row({}),
  row({ person_id: 102, student_no: "S2026912", name: "Andre Persaud", items_done: 0, items_percent: "0.0", last_seen: null, last_signed_in: null, open_alerts: 0 }),
];

export const standings: Standings = {
  met_percent: 50,
  outcomes: [
    { id: 31, code: "LO1", text: "Describe a soil profile", source: "srms", links: 1 },
    { id: 32, code: "LO2", text: "Plan fertiliser use", source: "srms", links: 0 },
  ],
  students: [
    {
      person_id: 101,
      student_no: "S2026911",
      name: "Ria Ramdial",
      outcomes: {
        "31": { standing: "met", percent: "70.0", evidence: [{ kind: "assignment", title: "Soil profile report", percent: "70.0" }] },
        "32": { standing: "no_evidence", percent: null, evidence: [] },
      },
    },
    {
      person_id: 102,
      student_no: "S2026912",
      name: "Andre Persaud",
      outcomes: {
        "31": { standing: "not_yet", percent: "30.0", evidence: [{ kind: "assignment", title: "Soil profile report", percent: "30.0" }] },
        "32": { standing: "no_evidence", percent: null, evidence: [] },
      },
    },
  ],
};

export const studentProgress: StudentProgress = {
  ...row({ open_alerts: undefined }),
  work: [
    { kind: "assignment", id: 5, title: "Soil profile report", state: "graded", percent: "70.00", due_at: "2026-10-01T16:00:00Z" },
    { kind: "quiz", id: 7, title: "Soils quiz", state: "zero", percent: "0.00" },
    { kind: "practical", id: 8, title: "Take a core", state: "not_due", percent: null },
  ],
  outcomes: { ...standings, students: [standings.students[0]] },
};

export const srmsOutcomes: SiteOutcomes = {
  course_code: "AGR205",
  from_srms: true,
  may_add: false,
  outcomes: [
    {
      id: 31,
      code: "LO1",
      text: "Describe a soil profile",
      source: "srms",
      position: 1,
      links: [{ id: 61, outcome: 31, kind: "assignment", assignment: 5, question: null, criterion: null, title: "Soil profile report" }],
    },
    { id: 32, code: "LO2", text: "Plan fertiliser use", source: "srms", position: 2, links: [] },
  ],
};

export const localOutcomes: SiteOutcomes = {
  course_code: "",
  from_srms: false,
  may_add: true,
  outcomes: [{ id: 40, code: "L1", text: "Name three soils", source: "local", position: 1, links: [] }],
};

export const evidence: EvidenceChoices = {
  assignments: [{ id: 5, title: "Soil profile report" }],
  questions: [{ id: 81, title: "pH meaning" }],
  criteria: [{ id: 11, title: "Soil profile report rubric: Profile description" }],
};

export const alert = (over: Partial<EarlyAlert> = {}): EarlyAlert => ({
  id: 70,
  site: 9,
  student: 101,
  student_no: "S2026911",
  student_name: "Ria Ramdial",
  kind: "missed_work",
  kind_label: "Missed work",
  summary: "2 pieces of work missed in the last 28 days",
  evidence: [
    { what: "Soil profile report: nothing handed in by the due date", when: "2026-10-01T16:00:00Z" },
    { what: "Soils quiz: nothing handed in by the due date", when: null },
  ],
  raised_at: "2026-10-05T08:15:00Z",
  state: "open",
  state_label: "New",
  handled_by_name: null,
  handled_at: null,
  note: "",
  conversation: null,
  ...over,
});

export const rules: AlertRule[] = [
  {
    id: 1,
    kind: "missed_work",
    label: "Missed work",
    description: "2 or more pieces of work missed (past their due date with nothing handed in) in the last 28 days",
    threshold: 2,
    window_days: 28,
    is_active: true,
  },
  {
    id: 3,
    kind: "no_visits",
    label: "No visits",
    description: "nothing done on the course for 14 days or more",
    threshold: 14,
    window_days: 0,
    is_active: false,
  },
];

export const courseReport: CourseReport = {
  min_group: 5,
  marking_days: 14,
  total: {
    sites: 2,
    sites_without_content: 1,
    students: 10,
    handed_in: 8,
    marked: 8,
    turnaround_days: "4.5",
    waiting_too_long: 0,
    srms_sent: 8,
    hidden: false,
  },
  groups: [
    { campus_code: "ESQ", programme: "DIP-AH", sites: 1, sites_without_content: 0, students: 8, handed_in: 8, marked: 8, turnaround_days: "4.5", waiting_too_long: 0, srms_sent: 8, hidden: false },
    { campus_code: "MRP", programme: "Programme not known", sites: 1, sites_without_content: 1, students: null, handed_in: null, marked: null, turnaround_days: null, waiting_too_long: null, srms_sent: null, hidden: true },
  ],
  sites: [
    {
      id: 12,
      code: "ANS201-2026-27-S1-ESQ",
      title: "ANS201 Animal Science",
      term_code: "2026-27-S1",
      campus_code: "ESQ",
      programmes: ["DIP-AH"],
      is_published: true,
      items: 4,
      no_content: false,
      assignments: 1,
      students: 8,
      handed_in: 8,
      marked: 8,
      turnaround_days: "4.5",
      marked_late: 0,
      waiting_too_long: 0,
      srms_sent: 8,
      srms_accepted: 7,
      srms_locked: 0,
      srms_unknown: 1,
      srms_last_sent: "2026-10-05T02:30:00Z",
      hidden: false,
    },
    {
      id: 9,
      code: "AGR205-2026-27-S1-MRP",
      title: "AGR205 Soil Science",
      term_code: "2026-27-S1",
      campus_code: "MRP",
      programmes: [],
      is_published: false,
      items: 0,
      no_content: true,
      assignments: 0,
      students: null,
      handed_in: null,
      marked: null,
      turnaround_days: null,
      marked_late: null,
      waiting_too_long: null,
      srms_sent: null,
      srms_accepted: null,
      srms_locked: null,
      srms_unknown: null,
      srms_last_sent: null,
      hidden: true,
    },
  ],
  choices: { campuses: ["ESQ", "MRP"], programmes: ["DIP-AH", "Programme not known"], terms: ["2026-27-S1"] },
};

export const staffReport: StaffReport = {
  min_group: 5,
  since: null,
  total: { staff: 13, completions: 3, required: 6, required_done: 2, overdue: 1, hidden: false },
  units: [
    { unit_code: "FARM", staff: 6, completions: 2, required: 6, required_done: 2, overdue: 1, hidden: false },
    { unit_code: "LIBRARY", staff: null, completions: null, required: null, required_done: null, overdue: null, hidden: true },
  ],
  courses: [
    { site: 20, title: "Fire safety", code: "SD-FIRE", completions: null, hidden: true },
    { site: 21, title: "First aid", code: "SD-AID", completions: 6, hidden: false },
  ],
};
