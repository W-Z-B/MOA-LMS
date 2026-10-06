/** How assignment settings and results are said to people, and the form fields' date handling. */

import type { AssignmentDetail, ItemState, MarkShown } from "../../api/types-marking";

/** An ISO time as a datetime-local field holds it, in the device's time: "2026-10-08T14:00". */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const at = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

/** A datetime-local value back to an ISO time; empty stays empty (null). */
export const fromLocalInput = (value: string): string | null => (value ? new Date(value).toISOString() : null);

/** "38", "38.5": a mark as people write it, never "38.00". */
export const plainMark = (value: string | null | undefined) => (value == null ? "" : String(Number(value)));

/** The late rule in words, as the student reads it before handing in (item 2.35). */
export function penaltyRule(a: Pick<AssignmentDetail, "late_penalty" | "late_penalty_percent" | "late_penalty_cap" | "allow_late">): string {
  if (!a.allow_late) return "Work cannot be handed in after the due date.";
  if (a.late_penalty === "none") return "Late work is accepted without a penalty.";
  const unit = a.late_penalty === "per_day" ? "day" : "hour";
  const cap = a.late_penalty_cap != null && a.late_penalty_cap !== "" ? `, at most ${plainMark(a.late_penalty_cap)}%` : "";
  return `Late work loses ${plainMark(a.late_penalty_percent)}% of the maximum mark for each ${unit} or part of a ${unit} late${cap}.`;
}

/** "14 out of 20", and the penalty that made it so: "late penalty 1 (5%) taken from 15". */
export function markWords(mark: MarkShown, max: string): { result: string; penalty: string | null } {
  const result = `${plainMark(mark.mark)} out of ${plainMark(max)}`;
  const penalty =
    Number(mark.penalty) > 0
      ? `Late penalty: ${plainMark(mark.penalty)} (${plainMark(mark.penalty_percent)}% of the maximum) taken from ${plainMark(mark.raw_mark)}.`
      : null;
  return { result, penalty };
}

export const STATE_WORDS: Record<ItemState, string> = {
  graded: "Counted",
  zero: "Missing, counted as 0",
  pending: "Pending",
  not_due: "Not yet due",
  dropped: "Dropped (lowest)",
};

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** The extensions a file picker offers for the kinds an assignment accepts. */
export const ACCEPT: Record<string, string> = {
  pdf: ".pdf",
  jpeg: ".jpg,.jpeg",
  png: ".png",
  webp: ".webp",
  heic: ".heic,.heif",
  docx: ".docx",
  xlsx: ".xlsx",
  pptx: ".pptx",
};

export const acceptFor = (kinds: string[]) => (kinds.length ? kinds : Object.keys(ACCEPT)).map((k) => ACCEPT[k]).join(",");
