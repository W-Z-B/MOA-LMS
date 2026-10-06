/**
 * An answer in words, for the review page and the marking screen: "Nitrogen", "Loam → holds water",
 * "9.81 m/s²". Works with what a student is sent (choices in their shown order, prompts) and with what teaching
 * staff are sent (the question's settings in full).
 */

import type { QType, QuestionData } from "../../api/types-quizzes";
import { plainText } from "./quizUtil";

type Response = Record<string, unknown> | null | undefined;

const textOf = (rows: { id: string; text?: string }[] | undefined, id: unknown) =>
  plainText(rows?.find((r) => r.id === id)?.text ?? String(id ?? ""));

function prompts(data: QuestionData): { id: string; text: string }[] {
  if (Array.isArray(data.prompts)) return data.prompts;
  return (data.pairs ?? []).map((p: { id: string; prompt: string }) => ({ id: p.id, text: p.prompt }));
}

export function describeResponse(qtype: QType, data: QuestionData, response: Response): string {
  if (!response) return "No answer";
  switch (qtype) {
    case "multichoice": {
      const ids = "choice" in response ? [response.choice] : ((response.choices as unknown[]) ?? []);
      const chosen = ids.filter((id) => id !== null && id !== undefined);
      return chosen.length ? chosen.map((id) => textOf(data.choices, id)).join("; ") : "No answer";
    }
    case "truefalse":
      return response.answer === true ? "True" : response.answer === false ? "False" : "No answer";
    case "matching": {
      const matches = (response.matches as Record<string, string>) ?? {};
      const rows = prompts(data)
        .filter((p) => matches[p.id])
        .map((p) => `${plainText(p.text)} → ${matches[p.id]}`);
      return rows.length ? rows.join("; ") : "No answer";
    }
    case "ordering": {
      const order = (response.order as string[]) ?? [];
      return order.length ? order.map((id, i) => `${i + 1}. ${textOf(data.items, id)}`).join("; ") : "No answer";
    }
    case "shortanswer":
    case "essay":
      return String(response.text ?? "").trim() || "No answer";
    case "numerical": {
      const value = `${response.value ?? ""} ${response.unit ?? ""}`.trim();
      return value || "No answer";
    }
    case "cloze": {
      const gaps = (response.gaps as Record<string, string>) ?? {};
      const keys = Object.keys(gaps).sort((a, b) => Number(a) - Number(b));
      return keys.length ? keys.map((k) => `gap ${k}: ${gaps[k]}`).join("; ") : "No answer";
    }
    case "file":
      return String(response.filename ?? "") || "No file";
    case "image_label": {
      const labels: { id: string; text: string }[] = data.labels ?? [];
      if (response.zones) {
        const zones = response.zones as Record<string, string>;
        const zoneIds: string[] = (data.zones ?? []).map((z: { id: string }) => z.id);
        const rows = zoneIds.filter((z) => zones[z]).map((z) => `zone ${zoneIds.indexOf(z) + 1}: ${textOf(labels, zones[z])}`);
        return rows.length ? rows.join("; ") : "No answer";
      }
      const placed = (response.placements as { label: string; x: number; y: number }[]) ?? [];
      return placed.length
        ? placed.map((p) => `${textOf(labels, p.label)} at ${Math.round(p.x)}, ${Math.round(p.y)}`).join("; ")
        : "No answer";
    }
  }
  return "";
}

/** Whether a response holds an answer at all, for the "unanswered" count before submitting. */
export function isAnswered(qtype: QType, response: Response): boolean {
  if (!response) return false;
  const filled = (value: unknown) =>
    Array.isArray(value) ? value.length > 0 : value && typeof value === "object" ? Object.keys(value).length > 0 : value !== undefined && value !== null && value !== "";
  switch (qtype) {
    case "multichoice":
      return filled(response.choice) || filled(response.choices);
    case "truefalse":
      return typeof response.answer === "boolean";
    case "matching":
      return filled(response.matches);
    case "ordering":
      return filled(response.order);
    case "numerical":
      return filled(response.value);
    case "cloze":
      return filled(response.gaps);
    case "file":
      return filled(response.filename);
    case "image_label":
      return filled(response.zones) || filled(response.placements);
    default:
      return filled(String(response.text ?? "").trim());
  }
}
