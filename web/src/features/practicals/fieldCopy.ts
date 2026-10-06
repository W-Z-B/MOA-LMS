/**
 * A copy of a practical task and its class list, kept on the phone when the checklist is opened with
 * signal, so the lecturer can go on marking where there is none (items 3.12 and 3.15). It holds the
 * lecturer's own class only, and is removed when they sign out (ADR 0011).
 */

import type { PracticalTask, TaskStudent } from "../../api/types-practicals";

export interface FieldCopy {
  task: PracticalTask;
  students: TaskStudent[];
  at: string;
}

const PREFIX = "gsa-lms.practicals.field.";

export function keepCopy(copy: FieldCopy) {
  try {
    localStorage.setItem(PREFIX + copy.task.id, JSON.stringify(copy));
  } catch {
    /* storage full or unavailable: the page still works while it stays open */
  }
}

export function readCopy(taskId: number): FieldCopy | null {
  try {
    return JSON.parse(localStorage.getItem(PREFIX + taskId) ?? "null");
  } catch {
    return null;
  }
}

/** On signing out: no class list stays on the phone. */
export function clearFieldCopies() {
  try {
    Object.keys(localStorage)
      .filter((key) => key.startsWith(PREFIX))
      .forEach((key) => localStorage.removeItem(key));
  } catch {
    /* nothing kept */
  }
}
