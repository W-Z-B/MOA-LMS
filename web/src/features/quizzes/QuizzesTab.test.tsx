import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import type { Attempt, AttemptSummary } from "../../api/types-quizzes";
import { fakeServer } from "../../test/fetch";
import { attempt, mcQuestion, page, quiz } from "../../test/quizzes";
import { QuizzesTab } from "./QuizzesTab";

const status = { attempts_used: 0, attempts_allowed: 2, closes_at: null, time_limit_minutes: 12, in_progress_attempt: null, grade_state: "none" as const, grade_percent: null };

function at(hash: string) {
  window.location.hash = hash;
}

afterEach(() => at(""));

const summary = (over: Partial<AttemptSummary> = {}): AttemptSummary => ({
  id: 30,
  quiz: 12,
  student_no: "S2026901",
  student_name: "Kezia Persaud",
  number: 1,
  state: "finished",
  started_at: "2026-10-05T14:00:00Z",
  deadline: null,
  submitted_at: "2026-10-05T14:05:00Z",
  auto_submitted: false,
  score: "1.50",
  max_score: "2.0000",
  percent: "75.00",
  needs_grading: false,
  is_released: true,
  ...over,
});

describe("the Quizzes tab for a student (feature 10)", () => {
  it("lists the quizzes with where the student stands, and opens one", async () => {
    at("#/sites/9/quizzes");
    fakeServer({
      "GET /quizzes/": { body: page([quiz({ my_status: status }), quiz({ id: 13, title: "Pests", closes_at: "2026-10-09T14:00:00Z", time_limit_minutes: null, is_practice: true, my_status: { ...status, in_progress_attempt: 4 } })]) },
    });
    render(<QuizzesTab siteId={9} teaching={false} />);
    expect(await screen.findByRole("link", { name: "Soils check" })).toHaveAttribute("href", "#/sites/9/quizzes/12");
    expect(screen.getByText("Open")).toBeInTheDocument();
    expect(screen.getByText("In progress")).toBeInTheDocument();
    expect(screen.getByText(/No closing date · 12 minutes · 2 marks/)).toBeInTheDocument();
    expect(screen.getByText(/Closes .* · No time limit · Practice: does not count/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Question banks" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("New quiz")).not.toBeInTheDocument();
  });

  it("shows a quiz's rules and the student's attempts, and starts an attempt", async () => {
    at("#/sites/9/quizzes/12");
    const { calls } = fakeServer({
      "GET /quizzes/12/": { body: quiz({ my_status: { ...status, attempts_used: 1 } }) },
      "GET /quizzes/12/attempts/": { body: [summary()] },
      "POST /quizzes/12/start/": [{ status: 409, body: { code: "closed", detail: "The quiz has closed." } }, { status: 201, body: attempt({ id: 31 }) }],
      "GET /quiz-attempts/31/": { body: attempt({ id: 31 }) },
    });
    render(<QuizzesTab siteId={9} teaching={false} />);
    expect(await screen.findByRole("heading", { name: "Soils check" })).toBeInTheDocument();
    expect(screen.getByText(/Time limit: 12 minutes/)).toBeInTheDocument();
    expect(screen.getByText("Attempts: 1 of 2 used; your highest attempt counts")).toBeInTheDocument();
    expect(screen.getByText("Pass mark: 50%")).toBeInTheDocument();
    expect(screen.getByText(/1.50 out of 2 \(75.00%\)/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start another attempt" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The quiz has closed.");
    await userEvent.click(screen.getByRole("button", { name: "Start another attempt" }));
    await waitFor(() => expect(window.location.hash).toBe("#/sites/9/quizzes/12/attempts/31"));
    expect(await screen.findByRole("heading", { name: "Question 1" })).toBeInTheDocument();
    expect(calls.filter((c) => c.path === "/quizzes/12/start/")).toHaveLength(2);
  });

  it("continues the attempt in progress, and offers no start when nothing is left", async () => {
    at("#/sites/9/quizzes/12");
    fakeServer({
      "GET /quizzes/12/": { body: quiz({ my_status: { ...status, in_progress_attempt: 31, attempts_used: 1 } }) },
      "GET /quizzes/12/attempts/": { body: [summary({ id: 31, state: "in_progress", submitted_at: null, score: null, percent: null })] },
    });
    render(<QuizzesTab siteId={9} teaching={false} />);
    await userEvent.click(await screen.findByRole("button", { name: "Continue my attempt" }));
    expect(window.location.hash).toBe("#/sites/9/quizzes/12/attempts/31");
  });

  it("offers no start on a closed quiz, and reviews a past attempt", async () => {
    at("#/sites/9/quizzes/12");
    fakeServer({
      "GET /quizzes/12/": { body: quiz({ is_practice: true, closes_at: "2026-01-01T00:00:00Z", my_status: { ...status, attempts_allowed: 0, attempts_used: 1 } }) },
      "GET /quizzes/12/attempts/": { body: [summary({ percent: null, auto_submitted: true })] },
      "GET /quiz-attempts/30/": { body: attempt({ state: "finished", submitted_at: "2026-10-05T14:05:00Z", questions: [mcQuestion()] }) },
    });
    render(<QuizzesTab siteId={9} teaching={false} />);
    expect(await screen.findByText(/Practice: as many attempts as you like/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Start/ })).not.toBeInTheDocument();
    expect(screen.getByText(/time ran out\) · mark not shown yet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Review attempt 1" }));
    expect(await screen.findByText(/Attempt 1: submitted/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /All quizzes/ }));
    expect(window.location.hash).toBe("#/sites/9/quizzes/12");
  });

  it("says when a quiz cannot be opened", async () => {
    at("#/sites/9/quizzes/12");
    fakeServer({ "GET /quizzes/12/": { status: 404, body: { detail: "Not found." } }, "GET /quizzes/12/attempts/": { body: [] } });
    render(<QuizzesTab siteId={9} teaching={false} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });

  it("never opens the banks for a student", async () => {
    at("#/sites/9/quizzes/banks");
    fakeServer({ "GET /quizzes/": { body: page([]) } });
    render(<QuizzesTab siteId={9} teaching={false} />);
    expect(await screen.findByText("No quizzes yet.")).toBeInTheDocument();
  });
});

describe("the Quizzes tab for teaching staff", () => {
  it("lists every quiz, draft or published, and makes a new one", async () => {
    at("#/sites/9/quizzes");
    const { calls } = fakeServer({
      "GET /quizzes/": { body: page([quiz(), quiz({ id: 13, title: "Draft one", is_published: false, is_practice: true })]) },
      "POST /quizzes/": [{ status: 400, body: { title: ["This field may not be blank."] } }, { status: 201, body: quiz({ id: 14 }) }],
      "GET /quizzes/14/": { body: quiz({ id: 14 }) },
      "GET /quiz-slots/": { body: page([]) },
      "GET /question-banks/": { body: page([]) },
    });
    render(<QuizzesTab siteId={9} teaching />);
    expect(await screen.findByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("Published")).toBeInTheDocument();
    expect(screen.getByText("Practice")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("New quiz"), "Week 2 check");
    await userEvent.click(screen.getByRole("button", { name: "Create quiz" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("title: This field may not be blank.");
    await userEvent.click(screen.getByRole("button", { name: "Create quiz" }));
    await waitFor(() => expect(window.location.hash).toBe("#/sites/9/quizzes/14/questions"));
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ site: 9, title: "Week 2 check" });
    expect(await screen.findByText("No questions yet.")).toBeInTheDocument();
  });

  it("opens the question banks", async () => {
    at("#/sites/9/quizzes");
    fakeServer({ "GET /quizzes/": { body: page([]) }, "GET /question-banks/": { body: page([]) } });
    render(<QuizzesTab siteId={9} teaching />);
    await userEvent.click(await screen.findByRole("button", { name: "Question banks" }));
    expect(await screen.findByRole("heading", { name: "Question banks" })).toBeInTheDocument();
  });

  it("says when the quizzes cannot be loaded", async () => {
    at("#/sites/9/quizzes");
    fakeServer({ "GET /quizzes/": { status: 500, body: { detail: "Server error." } } });
    render(<QuizzesTab siteId={9} teaching />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
  });

  it("marks an attempt and releases its result", async () => {
    at("#/sites/9/quizzes/12/attempts/30");
    const essay = { ...mcQuestion({ position: 1, qtype: "essay", data: {}, response: { text: "Rotation breaks pest cycles." } }), awarded: null, state: "needs_marking" as const, needs_manual: true };
    const marked = { ...essay, awarded: "1.00", state: "correct" as const, comment: "Good." };
    const base: Attempt = attempt({ state: "finished", submitted_at: "2026-10-05T14:05:00Z", needs_grading: true, score: "0.00", questions: [essay] });
    const done: Attempt = { ...base, needs_grading: false, score: "1.00", percent: "100.00", questions: [marked] };
    const { calls } = fakeServer({
      "GET /quiz-attempts/30/": { body: base },
      "POST /quiz-attempts/30/answers/1/mark/": [{ status: 400, body: { code: "out_of_range", detail: "The mark must be from 0 to 1.00." } }, { body: done }],
      "POST /quiz-attempts/30/release/": { body: { ...done, is_released: true } },
    });
    render(<QuizzesTab siteId={9} teaching />);
    expect(await screen.findByText("Needs marking")).toBeInTheDocument();
    expect(screen.getByText("Rotation breaks pest cycles.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Mark out of 1"), "1");
    await userEvent.type(screen.getByLabelText("Comment for the student"), "Good.");
    await userEvent.click(screen.getByRole("button", { name: "Save the mark for question 1" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The mark must be from 0 to 1.00.");
    await userEvent.click(screen.getByRole("button", { name: "Save the mark for question 1" }));
    expect(await screen.findByText("Not released")).toBeInTheDocument();
    expect(calls.find((c) => c.path.endsWith("/mark/"))!.body).toEqual({ mark: "1", comment: "Good." });
    await userEvent.click(screen.getByRole("button", { name: "Release this result" }));
    expect(await screen.findByText("Result released. The student has been told.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Change the mark for question 1" }));
    expect(screen.getByLabelText("Mark out of 1")).toHaveValue(1);
    await userEvent.click(screen.getByRole("button", { name: /Back to the quiz/ }));
    expect(window.location.hash).toBe("#/sites/9/quizzes/12/results");
  });

  it("says when an attempt is still in progress, or cannot be opened", async () => {
    at("#/sites/9/quizzes/12/attempts/30");
    fakeServer({ "GET /quiz-attempts/30/": [{ body: attempt() }] });
    const { unmount } = render(<QuizzesTab siteId={9} teaching />);
    expect(await screen.findByText(/still in progress/)).toBeInTheDocument();
    unmount();
    fakeServer({ "GET /quiz-attempts/30/": { status: 403, body: { detail: "No." } } });
    render(<QuizzesTab siteId={9} teaching />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No.");
  });
});
