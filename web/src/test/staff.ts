/** Fictional people and records for the staff-development and console screen tests. */

import type { Me } from "../api/types";
import type { CatalogueCourse, Certificate, EnrolmentRequest } from "../api/types-staff";

export const person = (roles: string[], over: Partial<Me> = {}): Me => ({
  id: 7,
  username: "E0901",
  name: "Marlon Bacchus",
  roles,
  is_superuser: false,
  mfa_required: false,
  mfa_verified: true,
  person_id: 21,
  person_kind: "staff",
  external_id: "E0901",
  ...over,
});

export const staff = person([]);
export const courseAdmin = person(["course_admin"], { person_id: 30, name: "Course Admin" });
export const administrator = person(["administrator"], { person_id: null, person_kind: null, name: "Ayesha Ramdin" });
export const auditor = person(["auditor"], { person_id: null, person_kind: null });
export const dpo = person(["dpo"], { person_id: null, person_kind: null });
export const student = person(["student"], { person_kind: "student" });

export const course = (over: Partial<CatalogueCourse> = {}): CatalogueCourse => ({
  site: 41,
  code: "SD-101",
  title: "Safe use of farm machinery",
  description: "For farm staff.",
  summary: "Tractors, mowers and the rules for both.",
  audience: "All farm staff",
  length_hours: "3.0",
  self_enrol: "open",
  capacity: null,
  places_left: null,
  my_status: "none",
  completed_on: null,
  expires_on: null,
  ...over,
});

export const page = <T>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });

export const request = (over: Partial<EnrolmentRequest> = {}): EnrolmentRequest => ({
  id: 5,
  site: 42,
  site_title: "First aid in the field",
  person: 22,
  person_name: "Joy Lall",
  approver: 21,
  approver_name: "Marlon Bacchus",
  state: "submitted",
  reason: "I run the field days.",
  decision_comment: "",
  waiting_since: "2026-10-01T10:00:00Z",
  created_at: "2026-10-01T10:00:00Z",
  allowed_actions: ["approve", "reject"],
  ...over,
});

export const certificate = (over: Partial<Certificate> = {}): Certificate => ({
  id: 9,
  reference: "GSA/LMS/2026/0001",
  site: 42,
  course: "First aid in the field",
  person: 21,
  holder: "Marlon Bacchus",
  issued_on: "2026-10-05",
  completed_on: "2026-10-05",
  expires_on: "2028-10-05",
  sha256: "ab",
  status: "valid",
  withdrawn_at: null,
  withdrawal_reason: "",
  ...over,
});
