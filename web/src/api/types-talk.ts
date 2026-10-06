/**
 * Types for forums, messages, groups, attendance and the calendar (items 4.08 to 4.12, 4.14, 4.15, 2.32).
 * They mirror the serializers of api/forums, api/messaging, api/courses (groups), api/attendance and
 * api/calendars. Keep in step with /api/docs.
 */

export type ForumType = "general" | "question" | "graded";

export interface Forum {
  id: number;
  site: number;
  module: number | null;
  title: string;
  /** Cleaned HTML. */
  description: string;
  forum_type: ForumType;
  is_published: boolean;
  groups: number[];
  weight: string;
  max_mark: string;
  rubric_id: number | null;
  grade_category: number | null;
  subscribed: boolean;
  threads: number;
  created_at: string;
}

export interface Thread {
  id: number;
  forum: number;
  title: string;
  author_name: string | null;
  is_pinned: boolean;
  is_locked: boolean;
  last_post_at: string | null;
  replies: number;
  created_at: string;
}

export interface Post {
  id: number;
  thread: number;
  parent: number | null;
  author_name: string | null;
  /** Cleaned HTML; empty when removed, or hidden from the reader. */
  body: string;
  created_at: string;
  edited_at: string | null;
  removed: boolean;
  /** For moderators and the author only. */
  removed_reason: string | null;
  hidden: boolean;
  can_edit: boolean;
}

export interface ThreadDetail {
  thread: Thread;
  posts: Post[];
  /** Question-and-answer forum: others' replies show once the reader has replied. */
  replies_hidden: boolean;
  subscribed: boolean;
  moderator: boolean;
}

export interface PostReport {
  id: number;
  post: number;
  thread: number;
  forum: number;
  site: number;
  reason: string;
  status: "open" | "removed" | "restored";
  created_at: string;
  reviewed_at: string | null;
  review_note: string;
}

export interface ConductStatement {
  id: number;
  version: number;
  body: string;
  created_at: string;
  published_at: string | null;
}

export interface ConductCurrent {
  statement: ConductStatement | null;
  accepted: boolean;
}

export interface ParticipationRow {
  person_id: number;
  student_no: string;
  name: string;
  posts: number;
  mark: string | null;
  feedback: string;
  rubric_id: number | null;
  is_released: boolean;
}

export type Audience = "direct" | "group" | "site";

export interface Conversation {
  id: number;
  site: number;
  site_code: string;
  audience: Audience;
  subject: string;
  group: number | null;
  last_message_at: string | null;
  unread: number;
  may_send: boolean;
}

export interface Message {
  id: number;
  sender_name: string | null;
  mine: boolean;
  body: string;
  created_at: string;
  client_sent_at: string | null;
  /** Names of the others who have read it. */
  read_by: string[];
}

export interface ConversationDetail {
  conversation: Conversation;
  participants: { name: string | null; last_read_at: string | null; may_send: boolean }[];
  messages: Message[];
}

export interface Recipient {
  person_id: number;
  name: string;
  role: "admin" | "lecturer" | "assistant" | "student" | "auditor";
}

export interface SiteMember {
  membership_id: number;
  person_id: number;
  external_id: string;
  name: string;
  role: Recipient["role"];
}

export interface SiteGroup {
  id: number;
  site: number;
  name: string;
  /** Membership ids. */
  members: number[];
}

export interface Grouping {
  id: number;
  site: number;
  name: string;
  description: string;
  groups: number[];
}

/** A group as /sites/{id}/my-groups/ shows it: every group for teaching staff, mine and joinable for students. */
export interface MyGroup {
  id: number;
  name: string;
  groupings: string[];
  member: boolean;
  self_sign_up: boolean;
  open: boolean;
  places_left: number | null;
  closes_at: string | null;
}

export interface SignUpSettings {
  is_open: boolean;
  max_size: number | null;
  closes_at: string | null;
}

export type AttendanceStatus = "present" | "late" | "excused" | "absent";

export interface ClassSession {
  id: number;
  site: number;
  site_code: string;
  group: number | null;
  title: string;
  starts_at: string;
  ends_at: string;
  location: string;
  meeting_url: string;
  recording_url: string;
  takes_attendance: boolean;
  my_status: AttendanceStatus | null;
}

export interface RegisterRow {
  person_id: number;
  student_no: string;
  name: string;
  status: AttendanceStatus | null;
  how: "register" | "check_in" | "closed" | null;
  acted_at: string | null;
  note: string;
}

export interface RegisterSaved {
  saved: number;
  kept: number[];
  register: RegisterRow[];
}

export interface CheckInCode {
  code: string;
  valid_seconds: number;
  expires_at: string;
  /** Six characters to show large in the room. */
  short_code: string;
  refresh_seconds: number;
}

export interface TotalsRow {
  person_id: number;
  student_no: string;
  name: string;
  sessions: number;
  present: number;
  late: number;
  excused: number;
  absent: number;
  not_recorded: number;
  percent: string | null;
}

export interface AttendancePolicy {
  send_to_srms: boolean;
  minimum_percent: string | null;
  last_sent_at: string | null;
}

export interface SrmsAnswer {
  offering_code: string;
  skipped?: string;
  accepted?: string[];
  locked?: string[];
  unknown?: string[];
}

export type EventKind = "assignment_due" | "quiz_closes" | "practical_closes" | "class_session" | "release";

export interface CalendarEvent {
  kind: EventKind;
  id: number;
  site: number;
  site_code: string;
  title: string;
  starts_at: string;
  ends_at: string | null;
  location: string;
  meeting_url: string;
  /** Where it is in the web app. */
  link: string;
}

export interface CalendarFeed {
  url: string | null;
  created_at: string | null;
  last_used_at: string | null;
}
