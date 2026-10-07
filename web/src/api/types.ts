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
  /** Which Home the person gets (item 2.07): the widest of their roles. */
  persona?: Persona;
  /** Their roles as people say them, never a system code: "Lecturer, AGR101". */
  title?: string;
}

export type Persona = "student" | "lecturer" | "course_admin" | "admin" | "office";

/** Work a student has still to hand in (item 2.08). */
export interface Work {
  kind: "assignment" | "quiz";
  id: number;
  title: string;
  site_id: number;
  site_code: string;
  site_title: string;
  due_at: string;
  link: string;
  can_still_submit: boolean;
}

export interface Feedback {
  kind: "assignment" | "quiz" | "practical";
  id: number;
  title: string;
  site_id: number;
  site_title: string;
  released_at: string;
  result: string;
  link: string;
}

export interface Progress {
  site_id: number;
  code: string;
  title: string;
  completed: number;
  released: number;
  share: number;
  coursework_percent: string | null;
}

/** Work waiting for teaching staff, grouped by assignment, quiz, task or site (item 2.09). */
export interface Marking {
  kind: "submission" | "quiz_answer" | "observation" | "logbook";
  site_id: number;
  site_title: string;
  title: string;
  count: number;
  oldest: string;
  link: string;
}

export interface QuietSite {
  site_id: number;
  code: string;
  title: string;
  next_item_at: string | null;
}

export interface Absent {
  person_id: number;
  name: string;
  student_no: string;
  sites: string[];
  last_seen: string | null;
}

export interface SiteFigures {
  total: number;
  published: number;
  drafts: number;
  without_teacher: number;
  students: number;
  open_takedowns: number;
}

/** What one person's Home shows (GET /home/). Each block is null when it is not the person's to see. */
export interface HomeSummary {
  persona: Persona;
  as_at: string;
  waiting: number;
  student: { due: Work[]; overdue: Work[]; feedback: Feedback[]; progress: Progress[] } | null;
  teaching: {
    to_mark: Marking[];
    quiet_sites: QuietSite[];
    not_seen: Absent[];
    not_seen_count: number;
    not_seen_days: number;
  } | null;
  sites: SiteFigures | null;
}

/** One thing waiting for the person (GET /to-do/), oldest first. */
export interface WaitingItem {
  kind: string;
  kind_name: string;
  title: string;
  since: string;
  due_at: string | null;
  waited_days: number;
  overdue: boolean;
  link: string;
  site_title: string;
}

export interface SearchHit {
  id: number;
  title: string;
  sub: string;
  link: string;
}

/** Search for everything (GET /search/?q=), each group only as far as the person may open it. */
export interface SearchHits {
  sites: SearchHit[];
  content: SearchHit[];
  assignments: SearchHit[];
  quizzes: SearchHit[];
  people: SearchHit[];
}

export const hasAnyRole = (me: Me, roles: readonly string[]) => me.is_superuser || roles.some((r) => me.roles.includes(r));

/** Staff who look after sites and records rather than (only) teach or learn. */
export const ADMIN_ROLES = ["administrator", "course_admin"] as const;

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
  /** The term life-cycle (item 7.12): open, grace, closed (read-only for appeals) or archived. */
  phase?: "open" | "grace" | "closed" | "archived";
  /** Why nothing on the site can be changed, once it is closed. */
  closed_notice?: string | null;
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
  /** When the device handed it in, for work sent later from its offline queue (item 4.02). */
  client_submitted_at: string | null;
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
