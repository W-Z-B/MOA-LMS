/**
 * Types for accounts, staff development, certificates and the administration console. They mirror the
 * serializers of iam, staffdev, approvals, certificates, integration, audit and privacy: keep in step with
 * /api/docs.
 */

import { hasAnyRole, type Me } from "./types";

// --- Roles: who the server lets do what. A screen shows a section only to these; others see nothing. ---

export const MANAGERS = ["administrator", "course_admin"] as const;
export const OVERSEERS = ["administrator", "course_admin", "auditor"] as const;
export const KEEPERS = ["administrator", "dpo"] as const;
export const PRIVACY_READERS = ["administrator", "dpo", "auditor"] as const;
export const CORRECTION_READERS = ["administrator", "course_admin", "dpo", "auditor"] as const;
export const AUDIT_READERS = ["administrator", "auditor"] as const;
/** Everyone the console has a section for. */
export const CONSOLE_ROLES = ["administrator", "course_admin", "auditor", "dpo", "registrar", "head_of_department"] as const;

/** Staff development is for members of staff, and for those who look after it. */
export const usesLearning = (me: Me) => me.person_kind === "staff" || hasAnyRole(me, OVERSEERS);

// --- Accounts (items 1.10, 1.22) ---

export interface PasswordLink {
  username: string;
  kind: "invitation" | "reset";
}

export interface SignInEmail {
  email: string;
  pending: { new_email: string; expires_at: string } | null;
}

export interface Uninvited {
  count: number;
  without_email: number;
}

export interface Invited {
  invited: number;
  emailed: number;
  in_use: number;
}

// --- Staff development (items 5.02 to 5.05) ---

export type Enrol = "open" | "approval" | "closed";
export type MyStatus = "none" | "requested" | "enrolled" | "completed" | "renewal_due";

export interface CatalogueCourse {
  site: number;
  code: string;
  title: string;
  description: string;
  summary: string;
  audience: string;
  length_hours: string | null;
  self_enrol: Enrol;
  capacity: number | null;
  places_left: number | null;
  my_status: MyStatus | null;
  completed_on: string | null;
  expires_on: string | null;
}

export interface CompletionProgress {
  complete: boolean;
  rules: { code: string; label: string; met: boolean; done: number; total: number }[];
  completed_on: string | null;
  expires_on: string | null;
}

export interface EnrolmentRequest {
  id: number;
  site: number;
  site_title: string;
  person: number;
  person_name: string;
  approver: number | null;
  approver_name: string | null;
  state: "submitted" | "approved" | "rejected" | "withdrawn";
  reason: string;
  decision_comment: string;
  waiting_since: string | null;
  created_at: string;
  allowed_actions: string[];
}

export interface LearningPath {
  id: number;
  code: string;
  title: string;
  description: string;
  audience: string;
  is_published: boolean;
  steps: { position: number; site: number; title: string }[];
}

export interface PathProgress {
  joined: boolean;
  done: number;
  total: number;
  complete: boolean;
  steps: { position: number; site: number; title: string; state: "done" | "open" | "locked"; enrolled: boolean }[];
}

export interface RequiredTraining {
  id: number;
  site: number;
  site_title: string;
  campus_code: string;
  unit_code: string;
  post_title: string;
  applies_to: string;
  due_days: number;
  renewal_months: number | null;
  is_active: boolean;
  notes: string;
  assigned: number;
}

export interface TrainingAssignment {
  id: number;
  site: number;
  site_title: string;
  person: number;
  person_name: string;
  employee_no: string;
  campus_code: string;
  assigned_on: string;
  due_on: string;
  completed_on: string | null;
  state: "done" | "due" | "overdue";
}

export interface Delegation {
  id: number;
  delegator: number;
  delegator_name: string;
  delegate: number;
  delegate_name: string;
  starts: string;
  ends: string;
  reason: string;
  cancelled: boolean;
  in_force: boolean;
  created_at: string;
}

// --- Certificates (items 5.08 to 5.11) ---

export interface Certificate {
  id: number;
  reference: string;
  site: number;
  course: string;
  person: number;
  holder: string;
  issued_on: string;
  completed_on: string;
  expires_on: string | null;
  sha256: string;
  status: "valid" | "expired" | "withdrawn";
  withdrawn_at: string | null;
  withdrawal_reason: string;
  /** The Open Badges 3.0 credential to download (item 5.10); null while badges are off or when withdrawn. */
  badge_url?: string | null;
}

export interface CertificateTemplate {
  id: number;
  code: string;
  version: number;
  name: string;
  heading: string;
  body: string;
  signatory_name: string;
  signatory_title: string;
  is_active: boolean;
  fields_used: string[];
  created_at: string;
}

// --- The console (items 1.17 to 1.23) ---

export interface IntegrationRun {
  id: number;
  kind: string;
  kind_name: string;
  trigger: string;
  started_at: string;
  finished_at: string | null;
  ok: number;
  failed: number;
  errors: { ref: string; code: string; detail: string }[];
  stopped: string;
}

export interface AuditEntry {
  id: number;
  at: string;
  actor: string;
  actor_username: string | null;
  action: string;
  action_name: string;
  entity: string;
  record: string;
  entity_id: number | null;
  person_number: string | null;
  reason: string;
  source_ip: string | null;
  changes: { field: string; before: unknown; after: unknown }[];
}

export interface AuditChain {
  entries: number;
  newest: number | null;
  latest_check: {
    id: number;
    checked_at: string;
    checked_by: string;
    rows: number;
    intact: boolean;
    last_id: number | null;
    first_broken_id: number | null;
    detail: string;
  } | null;
}

export interface Choice {
  code: string;
  name: string;
}

export interface NoticeVersion {
  id: number;
  version: number;
  title: string;
  body: string;
  created_at: string;
  published_at: string | null;
  published_by: string | null;
}

export interface CorrectionRequest {
  id: number;
  person: number;
  person_name: string;
  person_number: string;
  subject: string;
  subject_name: string;
  wrong: string;
  should_be: string;
  state: "open" | "corrected" | "declined";
  state_name: string;
  due_by: string;
  overdue: boolean;
  created_at: string;
  decided_by_name: string | null;
  decision_note: string;
  is_mine: boolean;
}

export interface RetentionRule {
  id: number;
  code: string;
  name: string;
  keep_months: number | null;
  counted_from: string;
  action: "delete" | "review" | "archive";
  action_name: string;
  automatic: boolean;
  confirmed: boolean;
  confirmed_by_name: string | null;
  note: string;
  open_run: number | null;
}

export interface DisposalRun {
  id: number;
  rule: number;
  rule_name: string;
  state: "proposed" | "done" | "cancelled";
  state_name: string;
  created_at: string;
  proposed_by: string | null;
  approved_by_name: string | null;
  proposed_by_me: boolean;
  items: { id: number; description: string; person_number: string | null; due_since: string; keep_reason: string; disposed_at: string | null }[];
}

export interface Breach {
  id: number;
  reference: string;
  discovered_at: string;
  happened: string;
  summary: string;
  data_affected: string;
  people_affected: number | null;
  minors_affected: boolean;
  risk: "low" | "medium" | "high";
  risk_name: string;
  contained_at: string | null;
  commissioner_told_at: string | null;
  people_told_at: string | null;
  actions: string;
  closed_at: string | null;
  recorded_by: string | null;
}

export interface AccessReview {
  last_review: { id: number; reviewed_by: string | null; reviewed_at: string; role_holders: number; teaching_staff: number; notes: string } | null;
  role_holders: {
    username: string;
    name: string;
    role: string;
    role_name: string;
    campus_code: string;
    given: string;
    last_sign_in: string | null;
    account_active: boolean;
  }[];
  teaching_staff: {
    site_code: string;
    site_title: string;
    term_code: string;
    employee_no: string;
    name: string;
    site_role: string;
    person_active: boolean;
    last_sign_in: string | null;
  }[];
}
