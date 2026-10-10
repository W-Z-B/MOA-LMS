import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { SimilarityReport } from "../../api/types-assess";
import { fakeServer } from "../../test/fetch";
import { SimilarityPanel } from "./SimilarityPanel";

const STATEMENT = "Overlap is evidence for a person to judge, not a verdict.";

const report = (change: Partial<SimilarityReport> = {}): SimilarityReport => ({
  status: "done",
  statement: STATEMENT,
  overall_percent: "62.50",
  word_count: 240,
  attempt_number: 2,
  checked_at: "2026-10-05T14:00:00Z",
  notes: ["photo.jpg was not read: photographs and scans carry no text to compare."],
  matches: [
    {
      id: 7,
      percent: "62.50",
      shared_words: 150,
      other: { known: false, label: "Another GSA submission, 2025", year: 2025, site: null, assignment: null, student: null, submission: null },
      passages: [{ mine: "walk the field in a zigzag pattern", theirs: "Walk the field in a zigzag pattern", words: 7 }],
    },
    {
      id: 8,
      percent: "10.00",
      shared_words: 24,
      other: { known: true, label: "Andre Fung (S2026912), Soil profile report, AGR205", year: 2026, site: "AGR205", assignment: "Soil profile report", student: "Andre Fung (S2026912)", submission: 22 },
      passages: [{ mine: "cores at the same depth", theirs: "cores at the same depth", words: 5 }],
    },
  ],
  ...change,
});

describe("the similarity report beside the mark (item 3.20)", () => {
  it("loads only when opened, says what overlap is, and shows the passages side by side", async () => {
    const { calls } = fakeServer({ "GET /submissions/21/similarity/": { body: report() } });
    const user = userEvent.setup();
    render(<SimilarityPanel submissionId={21} />);
    expect(calls).toHaveLength(0);
    await user.click(screen.getByText("Similarity with other GSA work"));
    expect(await screen.findByText(STATEMENT)).toBeInTheDocument();
    expect(screen.getByText("62.5% found in other GSA work")).toBeInTheDocument();
    expect(screen.getByText(/photo.jpg was not read/)).toBeInTheDocument();
    const unknown = screen.getByRole("list", { name: "Matching passages with Another GSA submission, 2025" });
    expect(within(unknown).getByText("walk the field in a zigzag pattern")).toBeInTheDocument();
    expect(within(unknown).getByText("Walk the field in a zigzag pattern")).toBeInTheDocument();
    expect(screen.getByText(/Named only to staff who teach that course too/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "10% shared with Andre Fung (S2026912), Soil profile report, AGR205" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "How to read this report" })).toHaveAttribute("href", "#/help/assessment-and-ai");
    expect(calls.filter((c) => c.method === "GET")).toHaveLength(1);
  });

  it("checks again on request and says when nothing could be read or nothing matches", async () => {
    const { calls } = fakeServer({
      "GET /submissions/21/similarity/": { body: report({ status: "no_text", overall_percent: null, matches: [], notes: [] }) },
      "POST /submissions/21/similarity/": { body: report({ matches: [], overall_percent: "0.00" }) },
    });
    const user = userEvent.setup();
    render(<SimilarityPanel submissionId={21} />);
    await user.click(screen.getByText("Similarity with other GSA work"));
    expect(await screen.findByText("No text could be read from this work, so it was not compared.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Check again now" }));
    expect(await screen.findByText("No passage matches any other GSA work.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(true);
  });

  it("says when the report is refused", async () => {
    fakeServer({ "GET /submissions/21/similarity/": { status: 403, body: { code: "permission_denied", detail: "Similarity reports are for the course's teaching staff." } } });
    const user = userEvent.setup();
    render(<SimilarityPanel submissionId={21} />);
    await user.click(screen.getByText("Similarity with other GSA work"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Similarity reports are for the course's teaching staff.");
  });
});
