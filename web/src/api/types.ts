/** Types mirror the LMS API serializers. Keep in step with /api/docs. */

export interface Me {
  id: number;
  username: string;
  name: string;
  roles: string[];
  is_superuser: boolean;
  mfa_required: boolean;
  mfa_verified: boolean;
  person_id: number | null;
  person_kind: "staff" | "student" | null;
  external_id: string | null;
  /** The privacy notice version still to be read, or null (item 1.18). */
  privacy_notice_due?: number | null;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Campus {
  id: number;
  code: string;
  name: string;
}

export interface Notification {
  id: number;
  kind: "info" | "approval" | "alert";
  title: string;
  body: string;
  link: string;
  created_at: string;
  read_at: string | null;
}

export type SiteRole = "admin" | "lecturer" | "assistant" | "student" | "auditor" | null;

export interface Site {
  id: number;
  code: string;
  title: string;
  term_code: string;
  campus_code: string;
  source: "srms" | "local";
  kind: "academic" | "staff_development";
  description: string;
  is_published: boolean;
  coursework_weight: string;
  my_role: SiteRole;
  members: number;
}

export interface ContentItem {
  id: number;
  module: number;
  kind: "page" | "file" | "link";
  title: string;
  body: string;
  filename: string | null;
  download_url: string | null;
  url: string;
  is_published: boolean;
  /** Release conditions in words, for teaching staff; null for everyone else. */
  conditions: string | null;
  licence: Licence;
  open_licence: string;
  source: string;
  under_review: boolean;
}

export type Licence = "gsa_own" | "open_licence" | "fair_dealing" | "permission_held" | "unknown";

export interface Module {
  id: number;
  site: number;
  title: string;
  position: number;
  items: ContentItem[];
}

export interface Announcement {
  id: number;
  site: number;
  title: string;
  body: string;
  author_name: string | null;
  created_at: string;
}

export interface SiteContents {
  site: Site;
  modules: Module[];
  announcements: Announcement[];
}

export interface SubmissionMark {
  mark: string;
  feedback: string;
  is_released: boolean;
}

export interface Submission {
  id: number;
  assignment: number;
  student_no: string;
  student_name: string;
  text: string;
  filename: string | null;
  download_url: string | null;
  submitted_at: string;
  is_late: boolean;
  mark: SubmissionMark | null;
}

export interface Assignment {
  id: number;
  site: number;
  title: string;
  instructions: string;
  due_at: string;
  max_mark: string;
  weight: string;
  allow_late: boolean;
  is_published: boolean;
  my_submission: Submission | null;
  submissions_count: number | null;
}

export interface Gradebook {
  site: string;
  assignments: { id: number; title: string; max_mark: string; weight: string }[];
  rows: {
    person_id: number;
    student_no: string;
    name: string;
    marks: Record<string, { submitted: boolean; late: boolean; mark: string | null; feedback: string }>;
    coursework_percent: string | null;
  }[];
}

export const canTeach = (role: SiteRole) => role === "admin" || role === "lecturer" || role === "assistant";

export interface SignedInSession {
  id: number;
  device: string;
  ip: string | null;
  created_at: string;
  last_seen_at: string;
  current: boolean;
}
