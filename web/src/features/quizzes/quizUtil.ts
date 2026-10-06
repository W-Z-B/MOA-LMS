/** Small rules the quiz screens share: no components here, so each screen file holds components only. */

import type { MouseEvent } from "react";
import { get } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { QType, QuestionCategory, QuestionData, Quiz } from "../../api/types-quizzes";
import { dmyTime } from "../../app/format";

/** Every page of a list endpoint, for the short lists of banks, categories and questions a quiz is built from. */
export async function getAll<T>(path: string): Promise<T[]> {
  const rows: T[] = [];
  let next: string | null = path;
  while (next) {
    const page: Paginated<T> = await get<Paginated<T>>(next);
    rows.push(...page.results);
    next = page.next ? page.next.replace(/^.*\/api\/v1/, "") : null;
  }
  return rows;
}

/** Text without its tags, for a short preview or an accessible name. DOMParser's document runs nothing. */
export function plainText(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  return (doc.body.textContent ?? "").replace(/\s+/g, " ").trim();
}

/** Where a quiz stands for a student, in a few words, with the chip colour that goes with it. */
export function studentState(quiz: Quiz, now = new Date()): { label: string; tone: string } {
  const mine = quiz.my_status;
  const closes = mine?.closes_at ?? quiz.closes_at;
  if (mine?.in_progress_attempt) return { label: "In progress", tone: "waiting" };
  if (mine?.grade_state === "graded" && mine.grade_percent !== null) return { label: `Result ${mine.grade_percent}%`, tone: "approved" };
  if (quiz.opens_at && new Date(quiz.opens_at) > now) return { label: `Opens ${dmyTime(quiz.opens_at)}`, tone: "draft" };
  if (closes && new Date(closes) <= now) return { label: mine?.attempts_used ? "Closed: submitted" : "Closed", tone: "draft" };
  if (mine?.grade_state === "pending" && mine.attempts_used) return { label: "Submitted: result to come", tone: "submitted" };
  if (mine && mine.attempts_allowed && mine.attempts_used >= mine.attempts_allowed) return { label: "No attempts left", tone: "draft" };
  return { label: mine?.attempts_used ? "Open: try again" : "Open", tone: "approved" };
}

/** Seconds as the countdown shows them: 4:05, or 1:02:09 past an hour. */
export function formatLeft(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${rest}` : `${m}:${rest}`;
}

/** A date and time from the server as the value of a datetime-local field, in this device's time zone. */
export function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Categories in tree order, each with how deep it sits, for indented lists and choices. */
export function categoryTree(categories: QuestionCategory[]): { category: QuestionCategory; depth: number }[] {
  const out: { category: QuestionCategory; depth: number }[] = [];
  const walk = (parent: number | null, depth: number) =>
    categories
      .filter((c) => c.parent === parent)
      .sort((a, b) => a.position - b.position || a.name.localeCompare(b.name))
      .forEach((c) => {
        out.push({ category: c, depth });
        walk(c.id, depth + 1);
      });
  walk(null, 0);
  return out;
}

export interface Zone {
  id?: string;
  label?: string;
  shape: "rect" | "circle" | "polygon";
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  r?: number;
  points?: number[][];
}

/** The middle of a zone, where its number is written. */
export function zoneCentre(zone: Zone): [number, number] {
  if (zone.shape === "rect") return [(zone.x ?? 0) + (zone.w ?? 0) / 2, (zone.y ?? 0) + (zone.h ?? 0) / 2];
  if (zone.shape === "circle") return [zone.x ?? 0, zone.y ?? 0];
  const pts = zone.points ?? [];
  return [pts.reduce((s, p) => s + p[0], 0) / (pts.length || 1), pts.reduce((s, p) => s + p[1], 0) / (pts.length || 1)];
}

/** A point clicked on an image, in the image's own pixels. */
export function imagePoint(e: MouseEvent<Element>, width: number, height: number): [number, number] {
  const box = e.currentTarget.getBoundingClientRect();
  const x = ((e.clientX - box.left) / (box.width || 1)) * width;
  const y = ((e.clientY - box.top) / (box.height || 1)) * height;
  return [Math.round(Math.max(0, Math.min(width, x))), Math.round(Math.max(0, Math.min(height, y)))];
}

export const blankGap = () => ({ kind: "short", answers: [{ text: "", fraction: 1, feedback: "" }], case_sensitive: false, weight: 1 });

const blankChoice = (fraction: number) => ({ text: "", fraction, feedback: "" });

/** A new question's settings, by type, as quizzes/schemas.py describes them. */
export function blankData(qtype: QType): QuestionData {
  switch (qtype) {
    case "multichoice":
      return { single: true, shuffle: true, choices: [blankChoice(1), blankChoice(0), blankChoice(0)] };
    case "truefalse":
      return { correct: true, feedback_true: "", feedback_false: "" };
    case "matching":
      return { pairs: [0, 1, 2].map(() => ({ prompt: "", answer: "" })), extra_answers: [], shuffle: true };
    case "ordering":
      return { items: [0, 1, 2].map(() => ({ text: "" })), grading: "absolute_position" };
    case "shortanswer":
      return { answers: [{ text: "", fraction: 1, feedback: "" }], case_sensitive: false };
    case "numerical":
      return { answers: [{ value: "", tolerance: 0, fraction: 1, feedback: "" }], units: [], unit_mode: "none", unit_penalty: 0.1 };
    case "cloze":
      return { gaps: {} };
    case "essay":
      return { min_words: null, max_words: null, response_template: "", grader_info: "" };
    case "file":
      return { allowed_extensions: ["pdf", "docx", "jpg", "jpeg", "png"], max_size_mb: 10, grader_info: "" };
    case "image_label":
      return { image_width: 0, image_height: 0, mode: "drop_zones", labels: [{ id: "a", text: "" }], zones: [] };
  }
}

/** The gap numbers written [[1]], [[2]] ... in a fill-in-the-blanks text, each once. */
export const gapKeys = (text: string) => [...new Set([...text.matchAll(/\[\[(\d{1,3})\]\]/g)].map((m) => m[1]))];

/** What a screen reader is told as the time passes 5 minutes and 1 minute left; null between. */
export function announcement(remaining: number, said: Set<number>): string | null {
  let message: string | null = null;
  for (const mark of [300, 60]) {
    if (remaining > mark || said.has(mark)) continue;
    said.add(mark);
    // An attempt opened with under a minute left is told once, not twice.
    if (mark === 300 && remaining <= 60) continue;
    const minutes = Math.ceil(remaining / 60);
    message = `${minutes} ${minutes === 1 ? "minute" : "minutes"} left.`;
  }
  return message;
}
