/** Fictional records for the talk screens' component tests. */

import type { Site } from "../../api/types";
import type { ClassSession, ConductCurrent, Forum, Post, Thread } from "../../api/types-talk";

export const site = (over: Partial<Site> = {}): Site => ({
  id: 9,
  code: "AGR101-2026-27-S1-MRP",
  title: "Introduction to Crop Production",
  term_code: "2026-27-S1",
  campus_code: "MRP",
  source: "local",
  kind: "academic",
  description: "",
  is_published: true,
  coursework_weight: "40.00",
  my_role: "student",
  members: 3,
  ...over,
});

export const sites = (over: Partial<Site> = {}) => ({ count: 1, next: null, previous: null, results: [site(over)] });

export const forum = (over: Partial<Forum> = {}): Forum => ({
  id: 3,
  site: 9,
  module: null,
  title: "Crop questions",
  description: "<p>Ask about the week's work.</p>",
  forum_type: "general",
  is_published: true,
  groups: [],
  weight: "0.00",
  max_mark: "10.00",
  rubric_id: null,
  grade_category: null,
  subscribed: false,
  threads: 1,
  created_at: "2026-10-01T12:00:00Z",
  ...over,
});

export const thread = (over: Partial<Thread> = {}): Thread => ({
  id: 7,
  forum: 3,
  title: "Spacing of tomato plants",
  author_name: "Marlon Bacchus",
  is_pinned: false,
  is_locked: false,
  last_post_at: "2026-10-04T12:00:00Z",
  replies: 1,
  created_at: "2026-10-04T10:00:00Z",
  ...over,
});

export const postOf = (over: Partial<Post> = {}): Post => ({
  id: 70,
  thread: 7,
  parent: null,
  author_name: "Marlon Bacchus",
  body: "<p>How far apart should tomato plants be?</p>",
  created_at: "2026-10-04T10:00:00Z",
  edited_at: null,
  removed: false,
  removed_reason: null,
  hidden: false,
  can_edit: false,
  ...over,
});

export const conduct = (accepted: boolean): ConductCurrent => ({
  statement: { id: 1, version: 1, body: "Be respectful.\n\nKeep to the course.", created_at: "2026-09-01T00:00:00Z", published_at: "2026-09-01T00:00:00Z" },
  accepted,
});

export const classSession = (over: Partial<ClassSession> = {}): ClassSession => {
  const now = Date.now();
  return {
    id: 5,
    site: 9,
    site_code: "AGR101-2026-27-S1-MRP",
    group: null,
    title: "Soil science lecture",
    starts_at: new Date(now - 5 * 60_000).toISOString(),
    ends_at: new Date(now + 55 * 60_000).toISOString(),
    location: "Room 4",
    meeting_url: "https://meet.example.org/agr101",
    recording_url: "",
    takes_attendance: true,
    my_status: null,
    ...over,
  };
};
