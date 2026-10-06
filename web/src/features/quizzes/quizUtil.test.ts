import { describe, expect, it } from "vitest";
import type { QType } from "../../api/types-quizzes";
import { quizAddress } from "../../app/router";
import { fakeServer } from "../../test/fetch";
import { quiz } from "../../test/quizzes";
import { describeResponse, isAnswered } from "./describe";
import { announcement, blankData, categoryTree, formatLeft, gapKeys, getAll, imagePoint, plainText, studentState, toLocalInput, zoneCentre } from "./quizUtil";

describe("addresses inside the Quizzes tab (item 2.10)", () => {
  it("gives the list, the banks, each part of a quiz and an attempt an address", () => {
    expect(quizAddress("/sites/4/quizzes")).toEqual({ view: "list" });
    expect(quizAddress("/sites/4/quizzes/banks")).toEqual({ view: "banks" });
    expect(quizAddress("/sites/4/quizzes/12")).toEqual({ view: "quiz", quizId: 12, section: "settings" });
    expect(quizAddress("/sites/4/quizzes/12/statistics")).toEqual({ view: "quiz", quizId: 12, section: "statistics" });
    expect(quizAddress("/sites/4/quizzes/12/nonsense")).toEqual({ view: "quiz", quizId: 12, section: "settings" });
    expect(quizAddress("/sites/4/quizzes/12/attempts/30")).toEqual({ view: "attempt", quizId: 12, attemptId: 30 });
    expect(quizAddress("/sites/4/quizzes/what")).toEqual({ view: "list" });
  });
});

describe("where a quiz stands for a student", () => {
  const now = new Date("2026-10-05T12:00:00Z");
  const status = { attempts_used: 0, attempts_allowed: 2, closes_at: null, time_limit_minutes: 10, in_progress_attempt: null, grade_state: "none" as const, grade_percent: null };
  it("says in progress, result, not open yet, closed, waiting for a result, used up or open", () => {
    expect(studentState(quiz({ my_status: { ...status, in_progress_attempt: 3 } }), now).label).toBe("In progress");
    expect(studentState(quiz({ my_status: { ...status, attempts_used: 1, grade_state: "graded", grade_percent: "80.00" } }), now).label).toBe("Result 80.00%");
    expect(studentState(quiz({ opens_at: "2026-10-06T12:00:00Z", my_status: status }), now).label).toMatch(/^Opens /);
    expect(studentState(quiz({ closes_at: "2026-10-01T12:00:00Z", my_status: status }), now).label).toBe("Closed");
    expect(studentState(quiz({ my_status: { ...status, attempts_used: 1, closes_at: "2026-10-01T12:00:00Z" } }), now).label).toBe("Closed: submitted");
    expect(studentState(quiz({ my_status: { ...status, attempts_used: 1, grade_state: "pending" } }), now).label).toBe("Submitted: result to come");
    expect(studentState(quiz({ my_status: { ...status, attempts_used: 2 } }), now).label).toBe("No attempts left");
    expect(studentState(quiz({ my_status: { ...status, attempts_used: 1 } }), now).label).toBe("Open: try again");
    expect(studentState(quiz({ my_status: status }), now)).toEqual({ label: "Open", tone: "approved" });
  });
});

describe("small rules", () => {
  it("reads every page of a list", async () => {
    fakeServer({
      "GET /question-banks/": { body: { count: 2, next: "https://lms.example/api/v1/question-banks/?page=2", previous: null, results: [{ id: 1 }] } },
      "GET /question-banks/?page=2": { body: { count: 2, next: null, previous: null, results: [{ id: 2 }] } },
    });
    expect(await getAll<{ id: number }>("/question-banks/")).toEqual([{ id: 1 }, { id: 2 }]);
  });

  it("writes the time left as minutes and seconds, with hours when there are any", () => {
    expect(formatLeft(65)).toBe("1:05");
    expect(formatLeft(0.2)).toBe("0:01");
    expect(formatLeft(-4)).toBe("0:00");
    expect(formatLeft(3725)).toBe("1:02:05");
  });

  it("tells a screen reader at five minutes and at one minute, once each", () => {
    const said = new Set<number>();
    expect(announcement(400, said)).toBeNull();
    expect(announcement(299, said)).toBe("5 minutes left.");
    expect(announcement(200, said)).toBeNull();
    expect(announcement(59, said)).toBe("1 minute left.");
    expect(announcement(30, said)).toBeNull();
    // Opened with under a minute left: told once.
    expect(announcement(45, new Set())).toBe("1 minute left.");
    expect(announcement(170, new Set())).toBe("3 minutes left.");
  });

  it("puts a date in a date-and-time field, in local time", () => {
    expect(toLocalInput(null)).toBe("");
    expect(toLocalInput("2026-10-05T14:30:00")).toBe("2026-10-05T14:30");
  });

  it("orders categories as a tree", () => {
    const rows = categoryTree([
      { id: 2, bank: 1, parent: 1, name: "Clay", position: 1 },
      { id: 1, bank: 1, parent: null, name: "Soils", position: 1 },
      { id: 3, bank: 1, parent: null, name: "Animals", position: 2 },
    ]);
    expect(rows.map((r) => [r.category.name, r.depth])).toEqual([
      ["Soils", 0],
      ["Clay", 1],
      ["Animals", 0],
    ]);
  });

  it("finds the middle of a zone and a clicked point on an image", () => {
    expect(zoneCentre({ shape: "rect", x: 10, y: 20, w: 40, h: 60 })).toEqual([30, 50]);
    expect(zoneCentre({ shape: "circle", x: 5, y: 6, r: 3 })).toEqual([5, 6]);
    expect(zoneCentre({ shape: "polygon", points: [[0, 0], [6, 0], [0, 6]] })).toEqual([2, 2]);
    const target = { getBoundingClientRect: () => ({ left: 100, top: 50, width: 200, height: 100 }) };
    expect(imagePoint({ clientX: 200, clientY: 100, currentTarget: target } as never, 400, 200)).toEqual([200, 100]);
    expect(imagePoint({ clientX: 900, clientY: 0, currentTarget: target } as never, 400, 200)).toEqual([400, 0]);
  });

  it("reads gap numbers and plain text", () => {
    expect(gapKeys("The [[1]] is [[2]], [[1]] again")).toEqual(["1", "2"]);
    expect(plainText("<p>Which <strong>soil</strong></p>\n<p>holds water?</p>")).toBe("Which soil holds water?");
  });

  it("starts every type of question with settings of the right shape", () => {
    const types: QType[] = ["multichoice", "truefalse", "matching", "ordering", "shortanswer", "numerical", "cloze", "essay", "file", "image_label"];
    for (const t of types) expect(blankData(t)).toBeTypeOf("object");
    expect(blankData("multichoice").choices).toHaveLength(3);
    expect(blankData("image_label").labels[0].id).toBe("a");
  });
});

describe("an answer in words, for review and marking", () => {
  const choices = { single: true, choices: [{ id: "a", text: "<p>Nitrogen</p>" }, { id: "b", text: "Sand" }] };
  it("names choices, matches, orders, numbers, gaps, files and labels", () => {
    expect(describeResponse("multichoice", choices, { choice: "a" })).toBe("Nitrogen");
    expect(describeResponse("multichoice", choices, { choices: ["a", "b"] })).toBe("Nitrogen; Sand");
    expect(describeResponse("multichoice", choices, { choice: null })).toBe("No answer");
    expect(describeResponse("truefalse", {}, { answer: false })).toBe("False");
    expect(describeResponse("truefalse", {}, { answer: true })).toBe("True");
    expect(describeResponse("truefalse", {}, {})).toBe("No answer");
    // A student is sent prompts; teaching staff the pairs.
    expect(describeResponse("matching", { prompts: [{ id: "a", text: "Clay" }] }, { matches: { a: "Holds water" } })).toBe("Clay → Holds water");
    expect(describeResponse("matching", { pairs: [{ id: "a", prompt: "Clay", answer: "x" }] }, { matches: {} })).toBe("No answer");
    expect(describeResponse("ordering", { items: [{ id: "a", text: "Sow" }, { id: "b", text: "Water" }] }, { order: ["b", "a"] })).toBe("1. Water; 2. Sow");
    expect(describeResponse("ordering", {}, { order: [] })).toBe("No answer");
    expect(describeResponse("shortanswer", {}, { text: " humus " })).toBe("humus");
    expect(describeResponse("essay", {}, { text: "" })).toBe("No answer");
    expect(describeResponse("numerical", {}, { value: "9.81", unit: "m/s²" })).toBe("9.81 m/s²");
    expect(describeResponse("numerical", {}, { value: "", unit: "" })).toBe("No answer");
    expect(describeResponse("cloze", {}, { gaps: { "2": "oxygen", "1": "carbon dioxide" } })).toBe("gap 1: carbon dioxide; gap 2: oxygen");
    expect(describeResponse("cloze", {}, { gaps: {} })).toBe("No answer");
    expect(describeResponse("file", {}, { filename: "bed.jpg" })).toBe("bed.jpg");
    expect(describeResponse("file", {}, {})).toBe("No file");
    const labels = { labels: [{ id: "a", text: "Stem" }], zones: [{ id: "z1" }, { id: "z2" }] };
    expect(describeResponse("image_label", labels, { zones: { z2: "a" } })).toBe("zone 2: Stem");
    expect(describeResponse("image_label", labels, { zones: {} })).toBe("No answer");
    expect(describeResponse("image_label", labels, { placements: [{ label: "a", x: 10.4, y: 20.6 }] })).toBe("Stem at 10, 21");
    expect(describeResponse("image_label", labels, { placements: [] })).toBe("No answer");
    expect(describeResponse("essay", {}, null)).toBe("No answer");
  });

  it("knows when a question has an answer", () => {
    expect(isAnswered("multichoice", { choice: "a" })).toBe(true);
    expect(isAnswered("multichoice", { choices: [] })).toBe(false);
    expect(isAnswered("truefalse", { answer: false })).toBe(true);
    expect(isAnswered("matching", { matches: { a: "x" } })).toBe(true);
    expect(isAnswered("ordering", { order: ["a"] })).toBe(true);
    expect(isAnswered("numerical", { value: "" })).toBe(false);
    expect(isAnswered("cloze", { gaps: { "1": "x" } })).toBe(true);
    expect(isAnswered("file", { filename: "a.pdf" })).toBe(true);
    expect(isAnswered("image_label", { placements: [{ label: "a", x: 1, y: 1 }] })).toBe(true);
    expect(isAnswered("essay", { text: "  " })).toBe(false);
    expect(isAnswered("shortanswer", null)).toBe(false);
  });
});
