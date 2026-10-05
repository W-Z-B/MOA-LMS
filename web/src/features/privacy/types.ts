/** Types of the privacy API (items 1.18 to 1.20). Keep in step with /api/docs. */

export interface PrivacyNotice {
  id: number;
  version: number;
  title: string;
  body: string;
  published_at: string | null;
}

export interface CurrentNotice {
  notice: PrivacyNotice | null;
  acknowledged: boolean;
}

export interface Correction {
  id: number;
  subject: string;
  subject_name: string;
  wrong: string;
  should_be: string;
  state: "open" | "corrected" | "declined";
  state_name: string;
  due_by: string;
  created_at: string;
  decision_note: string;
}

type Row = Record<string, string | number | boolean | null>;

export interface OwnRecord {
  produced_at: string;
  about: string;
  account: {
    username: string;
    name: string;
    email: string;
    roles: Row[];
    last_sign_in: string | null;
    sign_ins: Row[];
    privacy_notices_read: Row[];
    notifications: Row[];
  } | null;
  person: {
    kind: string;
    number: string;
    first_name: string;
    last_name: string;
    email: string;
    campus: string;
    memberships: Row[];
    completions: Row[];
    correction_requests: Row[];
    submissions?: Row[];
    released_marks?: Row[];
  } | null;
  teaching_actions: Row[] | null;
}

export const SUBJECTS: [string, string][] = [
  ["personal", "Name, number or email"],
  ["membership", "Courses I belong to"],
  ["submission", "My submissions"],
  ["mark", "My marks or feedback"],
  ["completion", "Courses completed"],
  ["account", "My account or roles"],
  ["other", "Something else"],
];
