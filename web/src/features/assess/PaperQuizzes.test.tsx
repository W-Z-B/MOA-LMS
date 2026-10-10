import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Paper, PaperGrid } from "../../api/types-assess";
import { fakeServer } from "../../test/fetch";
import { PaperQuizzes } from "./PaperQuizzes";

const paper: Paper = { id: 4, quiz: 12, title: "Mid-term on paper", sat_on: "2026-10-14", versions: ["A", "B"], questions: 2, keyed: 0 };
const grid: PaperGrid = {
  ...paper,
  columns: {
    A: [
      { number: 1, qtype: "multichoice", hint: "One letter, A to C" },
      { number: 2, qtype: "essay", hint: "Marks given, 0 to 5.00, or ? to mark later" },
    ],
    B: [
      { number: 1, qtype: "essay", hint: "Marks given, 0 to 5.00, or ? to mark later" },
      { number: 2, qtype: "multichoice", hint: "One letter, A to C" },
    ],
  },
  rows: [
    { student_no: "S2026901", name: "Kezia Persaud", version: "", answers: [], attempt: null, score: null, max_score: null, needs_marking: false },
    { student_no: "S2026902", name: "Tevin Joseph", version: "B", answers: ["?", "A"], attempt: 9, score: "1.0000", max_score: "6.0000", needs_marking: true },
  ],
};

describe("paper quizzes (item 3.24)", () => {
  it("makes a paper, offers each part of each version to print, and keys answers on the grid", async () => {
    const { calls } = fakeServer({
      "GET /quizzes/12/papers/": [{ body: [] }, { body: [paper] }],
      "POST /quizzes/12/papers/": { body: paper },
      "GET /quiz-papers/4/grid/": { body: grid },
      "POST /quiz-papers/4/grid/": { body: { saved: 1, errors: [{ student_no: "S2026902", detail: "Question 2: give one letter." }] } },
    });
    const user = userEvent.setup();
    render(<PaperQuizzes quizId={12} />);
    expect(await screen.findByText("No papers yet.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Title"), "Mid-term on paper");
    await user.click(screen.getByRole("button", { name: "Make the paper" }));
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({ title: "Mid-term on paper", versions: 2 });
    expect(await screen.findByRole("heading", { name: "Mid-term on paper" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Question paper (B)" })).toHaveAttribute("href", "/api/v1/quiz-papers/4/pdf/?version=B&part=questions");
    expect(screen.getByRole("link", { name: "Marking key (A)" })).toHaveAttribute("href", "/api/v1/quiz-papers/4/pdf/?version=A&part=key");

    // The grid opens for the paper just made.
    const table = await screen.findByRole("region", { name: "Answers keyed in" });
    expect(within(table).getByText("1 / 6")).toBeInTheDocument();
    expect(within(table).getByText("To mark")).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Save the answers keyed" });
    expect(save).toBeDisabled();
    await user.type(within(table).getByLabelText("Question 1, Kezia Persaud"), "B");
    await user.type(within(table).getByLabelText("Question 2, Kezia Persaud"), "4");
    await user.click(save);
    const sent = calls.find((c) => c.method === "POST" && c.path === "/quiz-papers/4/grid/")!;
    expect(sent.body).toEqual({ rows: [{ student_no: "S2026901", version: "A", answers: ["B", "4"] }] });
    expect(await screen.findByText("1 answer sheet saved and marked.")).toBeInTheDocument();
    expect(screen.getByText("S2026902: Question 2: give one letter.")).toBeInTheDocument();
  });

  it("keys answers from a CSV file and deletes a paper with nothing keyed", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { calls } = fakeServer({
      "GET /quizzes/12/papers/": [{ body: [paper] }, { body: [paper] }, { body: [] }],
      "GET /quiz-papers/4/grid/": { body: grid },
      "POST /quiz-papers/4/upload/": { body: { saved: 2, errors: [] } },
      "DELETE /quiz-papers/4/": { status: 204 },
    });
    const user = userEvent.setup();
    render(<PaperQuizzes quizId={12} />);
    await user.click(await screen.findByRole("button", { name: "Key answers" }));
    await user.upload(await screen.findByLabelText(/Or send a CSV file/), new File(["student_no,version,q1\n"], "marks.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: "Key from the file" }));
    expect(await screen.findByText("2 answer sheets saved and marked.")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/quiz-papers/4/upload/")!.body).toBeInstanceOf(FormData);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("No papers yet.")).toBeInTheDocument();
  });

  it("says why a quiz cannot go on paper", async () => {
    fakeServer({
      "GET /quizzes/12/papers/": { body: [] },
      "POST /quizzes/12/papers/": { status: 400, body: { code: "not_printable", detail: "Question 2 (Fill in the blanks) cannot be answered on paper." } },
    });
    const user = userEvent.setup();
    render(<PaperQuizzes quizId={12} />);
    await user.type(await screen.findByLabelText("Title"), "Test");
    await user.click(screen.getByRole("button", { name: "Make the paper" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot be answered on paper");
  });
});
