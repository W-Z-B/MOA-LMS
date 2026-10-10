import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { QuizSection } from "../../app/router";
import { fakeServer } from "../../test/fetch";
import { bank, page, question, quiz } from "../../test/quizzes";
import { QuizManage } from "./QuizManage";

function open(section: QuizSection, routes: Parameters<typeof fakeServer>[0], over = {}) {
  const server = fakeServer({ "GET /quizzes/12/": { body: quiz(over) }, ...routes });
  const onOpen = vi.fn();
  const onBack = vi.fn();
  render(<QuizManage siteId={9} quizId={12} section={section} onOpen={onOpen} onBack={onBack} />);
  return { ...server, onOpen, onBack };
}

describe("a quiz's settings and publishing (items 3.02 and 3.03)", () => {
  it("saves every setting as the API names it", async () => {
    const { calls } = open("settings", { "PATCH /quizzes/12/": { body: quiz({ title: "Soils check 2" }) } });
    const title = await screen.findByLabelText("Title");
    await userEvent.clear(title);
    await userEvent.type(title, "Soils check 2");
    await userEvent.clear(screen.getByLabelText(/Time limit in minutes/));
    await userEvent.clear(screen.getByLabelText(/Pass mark/));
    await userEvent.selectOptions(screen.getByLabelText("Which attempt counts"), "last");
    await userEvent.selectOptions(screen.getByLabelText("Moving between pages"), "sequential");
    await userEvent.selectOptions(screen.getByLabelText("The right answers"), "never");
    await userEvent.click(screen.getByLabelText(/Shuffle the questions/));
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")!.body).toMatchObject({
      title: "Soils check 2",
      time_limit_minutes: null,
      pass_mark: null,
      grading_method: "last",
      navigation: "sequential",
      review_correct: "never",
      shuffle_questions: true,
      attempts_allowed: 2,
      opens_at: null,
      questions_per_page: 0,
    });
  });

  it("sends secure exam mode, and disables attempts and the practice option while it is on (item 3.25)", async () => {
    const { calls } = open("settings", {
      "PATCH /quizzes/12/": { body: quiz({ is_secure_exam: true, attempts_allowed: 1 }) },
    });
    const secure = await screen.findByLabelText(/Secure exam:/);
    const practice = screen.getByLabelText(/Practice quiz:/);
    expect(screen.getByLabelText(/Attempts allowed/)).not.toBeDisabled();
    await userEvent.click(secure);
    expect(screen.getByLabelText(/Attempts allowed/)).toBeDisabled();
    expect(practice).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")!.body).toMatchObject({ is_secure_exam: true });
  });

  it("lists every reason the server gives for not publishing", async () => {
    open("settings", {
      "PATCH /quizzes/12/": [
        { status: 400, body: { is_published: ["Add at least one question.", "The quiz closes before it opens."] } },
        { body: quiz({ is_published: true }) },
      ],
    }, { is_published: false });
    await userEvent.click(await screen.findByRole("button", { name: "Publish to students" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The quiz cannot be published yet:");
    expect(within(alert).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Add at least one question.", "The quiz closes before it opens."]);
    await userEvent.click(screen.getByRole("button", { name: "Publish to students" }));
    expect(await screen.findByRole("button", { name: "Unpublish" })).toBeInTheDocument();
    expect(screen.getByText("Students on this course can see it.")).toBeInTheDocument();
  });

  it("deletes the quiz after asking, and says when saving fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { onBack } = open("settings", {
      "DELETE /quizzes/12/": { status: 204 },
      "PATCH /quizzes/12/": { status: 400, body: { closes_at: ["The quiz must close after it opens."] } },
    });
    await userEvent.click(await screen.findByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("closes at: The quiz must close after it opens.");
    await userEvent.click(screen.getByRole("button", { name: "Delete quiz" }));
    await waitFor(() => expect(onBack).toHaveBeenCalled());
  });

  it("gives each part of the quiz an address", async () => {
    open("settings", {});
    const parts = await screen.findByRole("navigation", { name: "Parts of the quiz" });
    expect(within(parts).getByRole("link", { name: "Settings" })).toHaveAttribute("aria-current", "page");
    expect(within(parts).getByRole("link", { name: "Statistics" })).toHaveAttribute("href", "#/sites/9/quizzes/12/statistics");
  });

  it("says when the quiz cannot be opened", async () => {
    fakeServer({ "GET /quizzes/12/": { status: 404, body: { detail: "Not found." } } });
    render(<QuizManage siteId={9} quizId={12} section="settings" onOpen={vi.fn()} onBack={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});

describe("a quiz's questions (item 3.02)", () => {
  const cats = page([{ id: 3, bank: 1, parent: null, name: "Soils", position: 1 }]);
  const routes = (slots: unknown[]) => ({
    "GET /quiz-slots/": { body: page(slots) },
    "GET /question-banks/": { body: page([bank(), bank({ id: 2, site: 44, name: "Another course" })]) },
    "GET /questions/": { body: page([question(), question({ id: 6, name: "Clay holds water", qtype: "truefalse" as const, tags: ["clay"], category: null })]) },
    "GET /question-categories/": { body: cats },
  });

  it("lists fixed and random entries, and adds a chosen question", async () => {
    const slots = [
      { id: 1, quiz: 12, position: 1, question: 5, category: null, random_count: 1, include_subcategories: true, tag: "", mark: null },
      { id: 2, quiz: 12, position: 2, question: null, category: 3, random_count: 2, include_subcategories: false, tag: "clay", mark: "2.00" },
    ];
    const { calls } = open("questions", { ...routes(slots), "POST /quiz-slots/": { status: 201, body: {} } });
    expect(await screen.findByText("1. Plant nutrients")).toBeInTheDocument();
    expect(screen.getByText("2. 2 random from “Soils” tagged clay")).toBeInTheDocument();
    expect(screen.getByText("This category only")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add questions" }));
    const add = screen.getByRole("region", { name: "Add questions" });
    // Only this site's banks and department banks are offered.
    expect(within(add).getAllByRole("option").map((o) => o.textContent)).not.toContain("Another course (AGR101)");
    expect(within(add).getByRole("button", { name: "Add “Plant nutrients”" })).toBeDisabled();
    await userEvent.type(within(add).getByLabelText("Tag (optional)"), "clay");
    expect(within(add).queryByText("Plant nutrients")).not.toBeInTheDocument();
    await userEvent.click(within(add).getByRole("button", { name: "Add “Clay holds water”" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ quiz: 12, position: 3, question: 6 }));
  });

  it("adds random questions from a category", async () => {
    const { calls } = open("questions", { ...routes([]), "POST /quiz-slots/": { status: 201, body: {} } });
    await userEvent.click(await screen.findByRole("button", { name: "Add questions" }));
    await userEvent.click(screen.getByLabelText("Random questions for each attempt"));
    await userEvent.selectOptions(screen.getByLabelText("Category"), "3");
    await userEvent.clear(screen.getByLabelText("How many"));
    await userEvent.type(screen.getByLabelText("How many"), "3");
    await userEvent.click(screen.getByLabelText("Include the categories inside it"));
    await userEvent.click(screen.getByRole("button", { name: "Add random questions" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({ quiz: 12, position: 1, category: 3, random_count: 3, include_subcategories: false, tag: "" }),
    );
  });

  it("moves, re-marks and removes entries, and shows the refusal once students have started", async () => {
    const slots = [
      { id: 1, quiz: 12, position: 1, question: 5, category: null, random_count: 1, include_subcategories: true, tag: "", mark: null },
      { id: 2, quiz: 12, position: 2, question: 6, category: null, random_count: 1, include_subcategories: true, tag: "", mark: null },
    ];
    const { calls } = open("questions", {
      ...routes(slots),
      "PATCH /quiz-slots/2/": { body: {} },
      "PATCH /quiz-slots/1/": { body: {} },
      "DELETE /quiz-slots/1/": { status: 409, body: { code: "has_attempts", detail: "Students have attempted this quiz; its questions can no longer change." } },
    });
    await userEvent.click(await screen.findByRole("button", { name: "Move up: Clay holds water" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(2));
    expect(calls.filter((c) => c.method === "PATCH").map((c) => [c.path, c.body])).toEqual([
      ["/quiz-slots/2/", { position: 1 }],
      ["/quiz-slots/1/", { position: 2 }],
    ]);
    const mark = screen.getAllByLabelText("Mark")[0];
    await userEvent.clear(mark);
    await userEvent.type(mark, "2");
    await userEvent.tab();
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH" && (c.body as { mark?: string }).mark === "2")).toBe(true));
    await userEvent.click(screen.getByRole("button", { name: "Remove: Plant nutrients" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Students have attempted this quiz");
  });

  it("points to the banks when there are none", async () => {
    open("questions", { "GET /quiz-slots/": { body: page([]) }, "GET /question-banks/": { body: page([]) } });
    await userEvent.click(await screen.findByRole("button", { name: "Add questions" }));
    expect(screen.getByRole("link", { name: "Question banks" })).toHaveAttribute("href", "#/sites/9/quizzes/banks");
  });
});

describe("extra time for one student (item 3.23)", () => {
  it("lists, adds and removes overrides for the course's students", async () => {
    const row = { id: 4, quiz: 12, student: 21, student_no: "S2026901", student_name: "Kezia Persaud", extra_minutes: 15, extra_attempts: 1, closes_at: "2026-10-09T14:00:00Z", reason: "Clinic" };
    const { calls } = open("students", {
      "GET /quiz-overrides/": [{ body: page([row]) }, { body: page([row]) }],
      "GET /sites/9/members/": {
        body: [
          { membership_id: 1, person_id: 21, external_id: "S2026901", name: "Kezia Persaud", role: "student" },
          { membership_id: 2, person_id: 22, external_id: "S2026902", name: "Tevin Joseph", role: "student" },
          { membership_id: 3, person_id: 9, external_id: "E0901", name: "Marlon Bacchus", role: "lecturer" },
        ],
      },
      "POST /quiz-overrides/": [{ status: 400, body: { student: ["This person is not a student of the course."] } }, { status: 201, body: {} }],
      "DELETE /quiz-overrides/4/": { status: 204 },
    });
    expect(await screen.findByText(/15 more minutes · 1 more attempts · closes for them .* · Clinic/)).toBeInTheDocument();
    const student = screen.getByLabelText("Student");
    // Only students without an override yet are offered.
    expect(within(student).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose…", "Tevin Joseph (S2026902)"]);
    await userEvent.selectOptions(student, "22");
    await userEvent.clear(screen.getByLabelText("Extra minutes"));
    await userEvent.type(screen.getByLabelText("Extra minutes"), "20");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("student: This person is not a student of the course.");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(2));
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ quiz: 12, student: 22, extra_minutes: 20, extra_attempts: 0, closes_at: null, reason: "" });
    await userEvent.click(screen.getByRole("button", { name: "Remove extra time for Kezia Persaud" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });
});

describe("marking, results and statistics (items 3.04 to 3.06)", () => {
  it("lists answers waiting to be marked, opens one, and releases what is ready", async () => {
    const { onOpen } = open("marking", {
      "GET /quizzes/12/marking-queue/": { body: [{ attempt: 30, position: 2, student_no: "S2026901", student_name: "Kezia Persaud", question: "Crop rotation", qtype: "essay", max_mark: "4.00", submitted_at: "2026-10-05T14:05:00Z" }] },
      "POST /quizzes/12/release/": { body: { released: 3, awaiting_marking: 1 } },
    }, { auto_release: false });
    expect(await screen.findByText(/Question 2: Crop rotation · Essay · out of 4/)).toBeInTheDocument();
    expect(screen.getByText("You release results when you are ready.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Mark question 2 for Kezia Persaud" }));
    expect(onOpen).toHaveBeenCalledWith("12/attempts/30");
    await userEvent.click(screen.getByRole("button", { name: "Release marked results" }));
    expect(await screen.findByRole("status")).toHaveTextContent("3 results released. 1 still needs marking first.");
  });

  it("says when nothing waits, and when release fails", async () => {
    open("marking", { "GET /quizzes/12/marking-queue/": { body: [] }, "POST /quizzes/12/release/": { status: 403, body: { detail: "Only teaching staff." } } });
    expect(await screen.findByText("Nothing waits to be marked.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Release marked results" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only teaching staff.");
  });

  it("lists every attempt with its state and score", async () => {
    const base = { quiz: 12, student_no: "S2026901", student_name: "Kezia Persaud", started_at: "2026-10-05T14:00:00Z", deadline: null, submitted_at: "2026-10-05T14:05:00Z", max_score: "2.0000", auto_submitted: false };
    const { onOpen } = open("results", {
      "GET /quizzes/12/attempts/": {
        body: [
          { ...base, id: 30, number: 1, state: "finished", score: "1.50", percent: "75.00", needs_grading: false, is_released: true, auto_submitted: true },
          { ...base, id: 31, number: 2, state: "finished", score: null, percent: null, needs_grading: true, is_released: false },
          { ...base, id: 32, number: 3, state: "finished", score: "2.00", percent: "100.00", needs_grading: false, is_released: false },
          { ...base, id: 33, number: 4, state: "in_progress", score: null, percent: null, needs_grading: false, is_released: false },
        ],
      },
    });
    const table = await screen.findByRole("table");
    expect(within(table).getByText("1.50 / 2 (75.00%)")).toBeInTheDocument();
    expect(within(table).getByText("Needs marking")).toBeInTheDocument();
    expect(within(table).getByText("Marked, not released")).toBeInTheDocument();
    expect(within(table).getByText("In progress")).toBeInTheDocument();
    expect(within(table).getByText("(time ran out)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open attempt 2 by Kezia Persaud" }));
    expect(onOpen).toHaveBeenCalledWith("12/attempts/31");
  });

  it("says when no one has attempted it", async () => {
    open("results", { "GET /quizzes/12/attempts/": { body: [] } });
    expect(await screen.findByText("No one has attempted this quiz yet.")).toBeInTheDocument();
  });

  it("shows facility, discrimination and the answers given, with a bar for each", async () => {
    open("statistics", {
      "GET /quizzes/12/statistics/": {
        body: {
          quiz: 12,
          attempts: 4,
          mean_percent: 62.5,
          median_percent: 60,
          pass_rate: 75,
          questions: [
            { question_id: 5, name: "Plant nutrients", qtype: "multichoice", positions: [1], answered: 4, facility_index: 75, discrimination_index: 12.5, responses: [{ response: "a", count: 3 }, { response: "b", count: 1 }] },
            { question_id: 6, name: "Clay holds water", qtype: "truefalse", positions: [2], answered: 4, facility_index: 50, discrimination_index: null, responses: [] },
          ],
        },
      },
      "GET /questions/5/": { body: question() },
    });
    expect(await screen.findByText("4 submitted attempts")).toBeInTheDocument();
    expect(screen.getByText("Average 62.5%")).toBeInTheDocument();
    expect(screen.getByText("Passed 75.0%")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("75.0%")).toBeInTheDocument();
    expect(within(table).getByText("12.5%")).toBeInTheDocument();
    expect(within(table).getByText("weak")).toBeInTheDocument();
    // Options are counted by id; their wording comes from the question.
    expect(await screen.findByText("Nitrogen")).toBeInTheDocument();
    expect(screen.getByText("Sand")).toBeInTheDocument();
  });

  it("waits for submitted attempts before showing statistics", async () => {
    open("statistics", { "GET /quizzes/12/statistics/": { body: { quiz: 12, attempts: 0, mean_percent: null, median_percent: null, pass_rate: null, questions: [] } } });
    expect(await screen.findByText(/Statistics appear once students have submitted/)).toBeInTheDocument();
  });
});
