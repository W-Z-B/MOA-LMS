/** Small helpers shared by the forums, messages, groups, classes and calendar screens. */

import { useEffect, useState } from "react";
import { get } from "../../api/client";
import type { Paginated, Site } from "../../api/types";
import type { ForumType } from "../../api/types-talk";

/** A list endpoint's rows, whether it pages its answer or not. */
export const rows = <T>(answer: Paginated<T> | T[]): T[] => (Array.isArray(answer) ? answer : answer.results);

/** The course sites this person can open, for naming a site and for choosing one. */
export function useSites(): Site[] {
  const [sites, setSites] = useState<Site[]>([]);
  useEffect(() => {
    get<Paginated<Site> | Site[]>("/sites/")
      .then((answer) => setSites(rows(answer)))
      .catch(() => setSites([]));
  }, []);
  return sites;
}

export const FORUM_TYPE: Record<ForumType, { label: string; explain: string }> = {
  general: { label: "General discussion", explain: "Anyone on the course may start a discussion and reply." },
  question: {
    label: "Question and answer",
    explain: "Teaching staff ask the questions. Post your answer to see what others have written.",
  },
  graded: {
    label: "Graded discussion",
    explain: "Your posts here earn a participation mark from your teaching staff.",
  },
};

/** "2026-10-05T14:30" for a datetime-local field, in the device's time. */
export function localInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const at = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

/** A datetime-local value as an ISO moment for the server; null when empty. */
export const fromLocalInput = (value: string): string | null => (value ? new Date(value).toISOString() : null);

/** "14:00" in the device's time. */
export const clock = (iso: string) => new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
