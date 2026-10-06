/** Small helpers shared by the practicals screens. */

import type { PracticalTask } from "../../api/types-practicals";
import { dmyTime } from "../../app/format";

/** The server takes at most this many files in one request (practicals.uploads.MAX_PHOTOS_PER_REQUEST). */
export const MAX_PHOTOS = 10;

/** A local date and time for an <input type="datetime-local">, now by default. */
export function localDateTime(at = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

export const localDate = (at = new Date()) => localDateTime(at).slice(0, 10);

/** The window of a task, in words. */
export function windowText(task: Pick<PracticalTask, "opens_at" | "closes_at">) {
  if (task.opens_at && task.closes_at) return `open ${dmyTime(task.opens_at)} to ${dmyTime(task.closes_at)}`;
  if (task.closes_at) return `closes ${dmyTime(task.closes_at)}`;
  if (task.opens_at) return `opens ${dmyTime(task.opens_at)}`;
  return "no closing date";
}

export const observationsPath = (taskId: number) => `/practical-tasks/${taskId}/observations/`;
