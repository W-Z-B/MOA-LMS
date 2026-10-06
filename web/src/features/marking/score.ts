/** The marking screen's previews of what the server works out when the mark is saved. */

import type { AssignmentDetail, Rubric, RubricScore, WorkSubmission } from "../../api/types-marking";

/** The mark a scored rubric or marking guide fills from the scores, scaled to the maximum (rubrics.services.score). */
export function filledMark(rubric: Rubric, scores: RubricScore[], maxMark: string): string | null {
  if (rubric.kind === "descriptive") return null;
  const ids = rubric.criteria.map((c) => c.id);
  if (ids.some((id) => !scores.find((s) => s.criterion === id && (rubric.kind === "guide" ? s.points !== null && s.points !== "" : s.level !== null))))
    return null;
  const total = scores.reduce((sum, s) => sum + Number(s.points ?? 0), 0);
  const possible = Number(rubric.max_points);
  if (!possible) return "0";
  return String(Math.round(((total / possible) * Number(maxMark) + Number.EPSILON) * 100) / 100);
}

/** The share of the maximum the late rule takes for this hand-in, as the server works it (rules.penalty_percent). */
export function penaltyPercent(a: AssignmentDetail, s: WorkSubmission): number {
  if (a.late_penalty === "none") return 0;
  const late = new Date(s.submitted_at).getTime() - new Date(s.due_at).getTime();
  if (late <= 0) return 0;
  const period = a.late_penalty === "per_day" ? 86_400_000 : 3_600_000;
  const cap = a.late_penalty_cap != null ? Number(a.late_penalty_cap) : 100;
  return Math.min(Number(a.late_penalty_percent) * Math.ceil(late / period), cap, 100);
}
