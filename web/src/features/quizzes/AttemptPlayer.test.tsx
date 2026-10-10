import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Attempt } from "../../api/types-quizzes";
import { flush, pendingCount } from "../../app/offlineQueue";
import { fakeServer, offline } from "../../test/fetch";
import { attempt, mcQuestion } from "../../test/quizzes";
import { AttemptPlayer } from "./AttemptPlayer";

const saved = { position: 1, saved: true, stale: false, server_time: "2026-10-05T14:01:00Z", seconds_left: 540 };

function open(routes: Parameters<typeof fakeServer>[0], start: Attempt = attempt()) {
  const server = fakeServer({ "GET /quiz-attempts/30/": { body: start }, ...routes });
  const onBack = vi.fn();
  render(<AttemptPlayer attemptId={30} onBack={onBack} />);
  return { ...server, onBack };
}

const finished = (over: Partial<Attempt> = {}) =>
  attempt({
    state: "finished",
    submitted_at: "2026-10-05T14:05:00Z",
    seconds_left: null,
    is_released: true,
    needs_grading: false,
    score: "1.00",
    percent: "50.00",
    passed: true,
    questions: [{ ...mcQuestion({ response: { choice: "a" } }), awarded: "1.00", state: "correct", feedback: "<p>Yes.</p>" }],
    ...over,
  });

describe("answering an attempt (items 3.03 and 4.02)", () => {
  it("shows the questions and the time left, and saves each answer as it is given", async () => {
    const { calls } = open({ "PUT /quiz-attempts/30/answers/1/": { body: saved } });
    expect(await screen.findByRole("heading", { name: "Question 1" })).toBeInTheDocument();
    expect(screen.getByRole("timer")).toHaveTextContent(/^(10:00|9:59)$/);
    await userEvent.click(screen.getByRole("radio", { name: "Nitrogen" }));
    const question = screen.getByRole("region", { name: "Question 1" });
    expect(await within(question).findByText("Sent")).toBeInTheDocument();
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.path).toBe("/quiz-attempts/30/answers/1/");
    expect(put.body).toMatchObject({ response: { choice: "a" } });
    expect((put.body as { client_saved_at: string }).client_saved_at).toMatch(/^\d{4}-/);
    // The server's time left sets the countdown again.
    expect(screen.getByRole("timer")).toHaveTextContent(/^(9:00|8:59)$/);
  });

  it("keeps an answer on the device without a connection, then shows it sent", async () => {
    open({ "PUT /quiz-attempts/30/answers/1/": [offline, { body: saved }] });
    await userEvent.click(await screen.findByRole("radio", { name: "Nitrogen" }));
    const question = screen.getByRole("region", { name: "Question 1" });
    expect(await within(question).findByText(/Waiting to send/)).toBeInTheDocument();
    expect(pendingCount()).toBe(1);
    await act(() => flush());
    expect(await within(question).findByText("Sent")).toBeInTheDocument();
    expect(pendingCount()).toBe(0);
  });

  it("saves typed answers after a pause, not at every key", async () => {
    const { calls } = open({ "PUT /quiz-attempts/30/answers/2/": { body: { ...saved, position: 2 } } });
    fireEvent.change(await screen.findByLabelText("Your answer"), { target: { value: "chloro" } });
    fireEvent.change(screen.getByLabelText("Your answer"), { target: { value: "chlorophyll" } });
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT")).toHaveLength(1), { timeout: 2000 });
    expect(calls.find((c) => c.method === "PUT")!.body).toMatchObject({ response: { text: "chlorophyll" } });
  });

  it("says why an answer was not taken, and shows the submitted attempt when time is up", async () => {
    open({
      "PUT /quiz-attempts/30/answers/1/": [
        { status: 400, body: { code: "invalid_answer", detail: "That choice is not one of the options." } },
        { status: 409, body: { code: "time_up", detail: "Time is up. Your saved answers have been submitted." } },
      ],
      "GET /quiz-attempts/30/": [{ body: attempt() }, { body: finished() }],
    });
    await userEvent.click(await screen.findByRole("radio", { name: "Nitrogen" }));
    expect(await screen.findByText(/Not saved: That choice is not one of the options/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "Sand" }));
    expect(await screen.findByText("Time is up. Your saved answers have been submitted.")).toBeInTheDocument();
    expect(await screen.findByText(/Score/)).toBeInTheDocument();
  });

  it("asks before submitting, says how many have no answer, then shows the review", async () => {
    const { calls } = open({ "POST /quiz-attempts/30/submit/": { body: finished() } });
    await userEvent.click(await screen.findByRole("button", { name: "Finish attempt…" }));
    const confirm = screen.getByRole("region", { name: "Submit your answers?" });
    expect(confirm).toHaveTextContent("2 of 2 questions have no answer.");
    await userEvent.click(within(confirm).getByRole("button", { name: "Back to the questions" }));
    expect(screen.queryByRole("region", { name: "Submit your answers?" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Finish attempt…" }));
    await userEvent.click(screen.getByRole("button", { name: "Submit my answers" }));
    expect(await screen.findByText(/Attempt 1: submitted/)).toBeInTheDocument();
    expect(screen.getByText("50.00%")).toBeInTheDocument();
    expect(screen.getByText("Passed")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/quiz-attempts/30/submit/")).toBe(true);
  });

  it("will not submit while answers still wait on the device", async () => {
    const { calls } = open({ "PUT /quiz-attempts/30/answers/1/": offline });
    await userEvent.click(await screen.findByRole("radio", { name: "Nitrogen" }));
    await screen.findByText(/Waiting to send/);
    await userEvent.click(screen.getByRole("button", { name: "Finish attempt…" }));
    await userEvent.click(screen.getByRole("button", { name: "Submit my answers" }));
    expect(await screen.findByText(/Some answers are still waiting to send/)).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/submit/"))).toBe(false);
  });

  it("moves between pages freely, or only forward when the quiz says so", async () => {
    const two = [mcQuestion(), { ...mcQuestion(), position: 2, page: 2, text: "<p>Second page question</p>" }];
    const { calls } = open({}, attempt({ questions: two, last_page: 2 }));
    expect(await screen.findByText("Page 1 of 2")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("Second page question")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(screen.getByText("Which is a plant nutrient?")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/next-page/"))).toBe(false);
  });

  it("asks the server for the next page of a quiz with no going back", async () => {
    const sequential = attempt({ navigation: "sequential", last_page: 2, questions: [mcQuestion()] });
    const next = attempt({ navigation: "sequential", current_page: 2, last_page: 2, questions: [{ ...mcQuestion(), position: 2, page: 2, text: "<p>Page two</p>" }] });
    open({ "POST /quiz-attempts/30/next-page/": [{ status: 409, body: { code: "time_up", detail: "Time is up." } }, { body: next }] }, sequential);
    expect(await screen.findByText(/You cannot go back to an earlier page/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Previous page" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Finish attempt…" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Time is up.");
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Page two")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Finish attempt…" })).toBeInTheDocument();
  });

  it("sends a file at once, and asks for a connection when there is none", async () => {
    const file = mcQuestion({ qtype: "file", data: { allowed_extensions: ["pdf"], max_size_mb: 5 } });
    open({ "POST /quiz-attempts/30/answers/1/file/": [{ body: saved }, offline] }, attempt({ questions: [file] }));
    const input = await screen.findByLabelText(/Your file/);
    await userEvent.upload(input, new File(["%PDF"], "plan.pdf", { type: "application/pdf" }));
    expect(await screen.findByText("Uploaded: plan.pdf")).toBeInTheDocument();
    await userEvent.upload(input, new File(["%PDF"], "plan2.pdf", { type: "application/pdf" }));
    expect(await screen.findByText(/No connection. Choose the file again/)).toBeInTheDocument();
  });

  it("submits by itself when the time runs out", async () => {
    const { calls } = open({ "POST /quiz-attempts/30/submit/": { body: finished({ auto_submitted: true }) } }, attempt({ seconds_left: 0 }));
    expect(await screen.findByText(/submitted automatically when the time ran out/)).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/submit/"))).toBe(true);
  });

  it("reads the time left again when the connection returns", async () => {
    const { calls } = open({ "GET /quiz-attempts/30/": [{ body: attempt() }, { body: attempt({ seconds_left: 120 }) }] });
    await screen.findByRole("timer");
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    await waitFor(() => expect(screen.getByRole("timer")).toHaveTextContent(/^(2:00|1:59)$/));
    expect(calls.filter((c) => c.method === "GET")).toHaveLength(2);
  });

  it("says when the attempt cannot be opened, and goes back", async () => {
    const { onBack } = open({ "GET /quiz-attempts/30/": { status: 404, body: { detail: "Not found." } } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
    expect(onBack).not.toHaveBeenCalled();
  });
});

describe("secure exam mode (item 3.25)", () => {
  it("shows the deterrent notice and reports one focus-lost/resumed pair per excursion", async () => {
    const { calls } = open(
      { "POST /quiz-attempts/30/integrity-event/": { status: 204 } },
      attempt({ is_secure_exam: true }),
    );
    expect(await screen.findByText(/Secure exam sitting/)).toBeInTheDocument();
    expect(screen.getByText(/not a lockdown browser/)).toBeInTheDocument();

    window.dispatchEvent(new Event("blur"));
    window.dispatchEvent(new Event("blur")); // a second signal for the same excursion is not reported again
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith("/integrity-event/"))).toHaveLength(1));
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith("/integrity-event/"))).toHaveLength(2));
    const kinds = calls.filter((c) => c.path.endsWith("/integrity-event/")).map((c) => (c.body as { kind: string }).kind);
    expect(kinds).toEqual(["focus_lost", "focus_resumed"]);
  });

  it("reports copy, paste and the right-click menu, and turns their default action off", async () => {
    const { calls } = open(
      { "POST /quiz-attempts/30/integrity-event/": { status: 204 } },
      attempt({ is_secure_exam: true }),
    );
    await screen.findByText(/Secure exam sitting/);
    const copy = new Event("copy", { cancelable: true });
    const paste = new Event("paste", { cancelable: true });
    const contextMenu = new Event("contextmenu", { cancelable: true });
    document.dispatchEvent(copy);
    document.dispatchEvent(paste);
    document.dispatchEvent(contextMenu);
    expect(copy.defaultPrevented).toBe(true);
    expect(paste.defaultPrevented).toBe(true);
    expect(contextMenu.defaultPrevented).toBe(true);
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith("/integrity-event/"))).toHaveLength(3));
    const kinds = calls.filter((c) => c.path.endsWith("/integrity-event/")).map((c) => (c.body as { kind: string }).kind);
    expect(kinds).toEqual(["copy_attempted", "paste_attempted", "context_menu_blocked"]);
  });

  it("reports nothing for an ordinary quiz", async () => {
    const { calls } = open({}, attempt({ is_secure_exam: false }));
    await screen.findByRole("heading", { name: "Question 1" });
    expect(screen.queryByText(/Secure exam sitting/)).not.toBeInTheDocument();
    window.dispatchEvent(new Event("blur"));
    document.dispatchEvent(new Event("copy", { cancelable: true }));
    expect(calls.some((c) => c.path.endsWith("/integrity-event/"))).toBe(false);
  });
});

describe("the review (item 3.05)", () => {
  it("shows only what the review options let through", async () => {
    open({}, finished({ score: null, percent: null, passed: null, is_released: false, questions: [mcQuestion({ response: { choice: "a" } })] }));
    expect(await screen.findByText("Your answers are in. Your mark is shown here when it is released.")).toBeInTheDocument();
    expect(screen.getByText("Nitrogen", { selector: "p" , exact: false })).toBeInTheDocument();
    expect(screen.queryByText(/Right answer/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Mark:/)).not.toBeInTheDocument();
  });

  it("shows marks, right answers and feedback once allowed", async () => {
    const q = { ...mcQuestion({ response: { choice: "b" } }), awarded: "0.00", state: "incorrect" as const, right_answer: { choice: "a" }, feedback: "<p>Not quite.</p>", general_feedback: "<p>Nitrogen feeds leaves.</p>", comment: "See week 1." };
    open({}, finished({ questions: [q], passed: false, overall_feedback: "Revise soils." }));
    expect(await screen.findByText("Not correct")).toBeInTheDocument();
    expect(screen.getByText("Not passed")).toBeInTheDocument();
    expect(screen.getByText(/Right answer:/).parentElement).toHaveTextContent("Right answer: Nitrogen");
    expect(screen.getByText("Not quite.")).toBeInTheDocument();
    expect(screen.getByText("Nitrogen feeds leaves.")).toBeInTheDocument();
    expect(screen.getByText("Marker's comment: See week 1.")).toBeInTheDocument();
    expect(screen.getByText("Revise soils.")).toBeInTheDocument();
  });

  it("says when answers wait to be marked, or marks are held back", async () => {
    open({}, finished({ score: null, percent: null, passed: null, needs_grading: true }));
    expect(await screen.findByText(/Some answers are waiting to be marked/)).toBeInTheDocument();
  });

  it("says when a released result keeps its marks back", async () => {
    open({}, finished({ score: null, percent: null, passed: null, is_released: true }));
    expect(await screen.findByText("Your answers are in. This quiz does not show marks yet.")).toBeInTheDocument();
  });
});
