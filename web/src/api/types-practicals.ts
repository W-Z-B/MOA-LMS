/** Types for practical assessment, competency and the logbook (items 3.12 to 3.15, 5.15). They mirror
 * api/practicals/serializers.py; keep in step with /api/docs. */

export type UnitType = "crop_plot" | "livestock_unit" | "pond" | "forest_stand" | "laboratory" | "processing_unit" | "other";

export const UNIT_TYPES: { value: UnitType; label: string }[] = [
  { value: "crop_plot", label: "Crop plot" },
  { value: "livestock_unit", label: "Livestock unit" },
  { value: "pond", label: "Fish pond" },
  { value: "forest_stand", label: "Forest stand" },
  { value: "laboratory", label: "Laboratory" },
  { value: "processing_unit", label: "Processing unit" },
  { value: "other", label: "Other" },
];

export const unitLabel = (value: string) => UNIT_TYPES.find((u) => u.value === value)?.label ?? value;

export interface Criterion {
  id: number;
  position: number;
  text: string;
  kind: "pass_fail" | "scored";
  max_score: number;
  pass_score: number;
  is_critical: boolean;
  performance_criteria: number[];
}

export interface PracticalTask {
  id: number;
  site: number;
  title: string;
  instructions: string;
  unit_type: UnitType;
  location: string;
  weight: string;
  counts_in_coursework: boolean;
  opens_at: string | null;
  closes_at: string | null;
  max_attempts: number;
  is_published: boolean;
  criteria: Criterion[];
}

/** One student on a task's class list (GET /practical-tasks/{id}/students/). */
export interface TaskStudent {
  person_id: number;
  student_no: string;
  name: string;
  attempts: number;
  attempts_left: number;
  latest: { id: number; attempt: number; is_released: boolean; critical_passed: boolean; score: string } | null;
}

export interface Photo {
  id: number;
  filename: string;
  download_url: string;
}

export interface ObservationResult {
  criterion: number;
  text: string;
  kind: "pass_fail" | "scored";
  is_critical: boolean;
  max_score: number;
  passed: boolean;
  score: number | null;
  comment: string;
}

export interface Observation {
  id: number;
  task: number;
  task_title: string;
  site: number;
  student: number;
  student_no: string;
  student_name: string;
  attempt: number;
  assessor_name: string;
  observed_at: string;
  recorded_at: string;
  latitude: string | null;
  longitude: string | null;
  location_text: string;
  comments: string;
  results: ObservationResult[];
  score: { earned: number; possible: number };
  critical_passed: boolean;
  photos: Photo[];
  is_released: boolean;
  released_at: string | null;
}

export interface Assessor {
  id: number;
  site: number;
  person: number;
  person_name: string;
  employee_no: string;
  note: string;
  is_active: boolean;
}

export interface FrameworkTree {
  id: number;
  code: string;
  title: string;
  source: string;
  version: string;
  is_active: boolean;
  units: {
    id: number;
    code: string;
    title: string;
    elements: { id: number; code: string; title: string; criteria: { id: number; code: string; text: string }[] }[];
  }[];
}

export interface SiteFramework {
  id: number;
  site: number;
  framework: number;
  framework_title: string;
}

export type CompetencyStatus = "competent" | "not_yet_competent" | "not_assessed";

export const STATUS_LABEL: Record<CompetencyStatus, string> = {
  competent: "Competent",
  not_yet_competent: "Not yet competent",
  not_assessed: "Not assessed",
};

interface CriterionRef {
  id: number;
  task: string;
  text: string;
}

/** One unit for one student on the competency sheet. A student's copy has no suggestion or criteria. */
export interface UnitCell {
  unit_id: number;
  unit_code: string;
  unit_title: string;
  framework: string;
  suggested?: CompetencyStatus;
  critical_criteria?: CriterionRef[];
  missing_critical?: CriterionRef[];
  observations: number[];
  assignments: number[];
  result: { id: number; status: CompetencyStatus; assessor: string; decided_on: string } | null;
}

export interface CompetencySheet {
  site: string;
  units: { id: number; code: string; title: string; framework: string }[];
  rows: { person_id: number; student_no: string; name: string; units: UnitCell[] }[];
}

export type LogbookStatus = "pending" | "signed" | "returned";

export const LOGBOOK_STATUS: Record<LogbookStatus, string> = {
  pending: "Waiting for sign-off",
  signed: "Signed off",
  returned: "Returned for correction",
};

export interface LogbookEntry {
  id: number;
  site: number;
  student_no: string;
  student_name: string;
  work_date: string;
  unit_type: UnitType;
  unit_text: string;
  task: string;
  hours: string;
  notes: string;
  latitude: string | null;
  longitude: string | null;
  client_recorded_at: string;
  created_at: string;
  status: LogbookStatus;
  supervisor_name: string | null;
  reviewed_at: string | null;
  review_comment: string;
  photo_files: Photo[];
}

export interface HoursRow {
  unit_type: string;
  label: string;
  signed_hours: string;
  waiting_hours: string;
}

export interface LogbookTotals {
  site: string;
  rows: { person_id: number; student_no: string; name: string; hours: HoursRow[] }[];
}

interface PortfolioPhoto {
  filename: string;
  download_url: string;
}

/** GET /portfolio/: signed entries, released observations and competency results, site by site. */
export interface Portfolio {
  student: { student_no: string; name: string };
  generated_at: string;
  sites: {
    site: { id: number; code: string; title: string; term: string };
    logbook: { date: string; unit_type: string; unit: string; task: string; hours: string; signed_by: string | null; photos: PortfolioPhoto[] }[];
    logbook_hours: HoursRow[];
    observations: {
      task: string;
      attempt: number;
      assessor: string;
      observed_at: string;
      score: string;
      critical_passed: boolean;
      comments: string;
      photos: PortfolioPhoto[];
    }[];
    competencies: { unit_code: string; unit_title: string; status: string; assessor: string; decided_on: string; framework: string }[];
  }[];
}
