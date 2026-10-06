import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ParticipationRow } from "../../api/types-talk";
import { FrameContext } from "../../app/frame";
import { fakeServer } from "../../test/fetch";
import { conduct, forum, sites, thread } from "./fixtures";
import { ForumScreen } from "./ForumScreen";

const row = (over: Partial<ParticipationRow> = {}): ParticipationRow => ({
  person_id: 21,
  student_no: "S2026901",
  name: "Kezia Persaud",
  posts: 3,
  mark: null,
  feedback: "",
  rubric_id: null,
  is_released: false,
  ...over,
});

function open(routes: Record<string, unknown>) {
  const server = fakeServer(routes as Parameters<typeof fakeServer>[0]);
  const setCrumb = vi.fn();
  const onNavigate = vi.fn();
  render(
    <FrameContext.Provider value={{ setCrumb, decided: vi.fn() }}>
      <ForumScreen forumId={3} onNavigate={onNavigate} />
    </FrameContext.Provider>,
  );
  return { ...server, setCrumb, onNavigate };
}

describe("a forum (item 4.08)", () => {
  it("names itself, lists its discussions with pins and locks, and subscribes", async () => {
    const { calls, setCrumb } = open({
      "GET /sites/": { body: sites() },
      "GET /forums/3/": { body: forum() },
      "GET /forums/3/threads/": { body: [thread({ is_pinned: true }), thread({ id: 8, title: "Mulching", is_locked: true, replies: 0, last_post_at: null })] },
      "POST /forums/3/subscribe/": { body: { subscribed: true } },
    });
    expect(await screen.findByRole("heading", { name: "Crop questions", level: 1 })).toBeInTheDocument();
    await waitFor(() => expect(setCrumb).toHaveBeenCalledWith("Crop questions"));
    expect(screen.getByRole("link", { name: "Introduction to Crop Production" })).toHaveAttribute("href", "#/sites/9/discussion");
    const list = screen.getByRole("list", { name: "Discussions" });
    expect(within(list).getAllByRole("link")[0]).toHaveTextContent("Spacing of tomato plants");
    expect(within(list).getAllByRole("link")[0]).toHaveTextContent("Pinned");
    expect(within(list).getAllByRole("link")[1]).toHaveTextContent("Locked");
    await userEvent.click(screen.getByRole("button", { name: "Get notices of new posts" }));
    expect(await screen.findByRole("button", { name: "Stop notices" })).toHaveAttribute("aria-pressed", "true");
    expect(calls.some((c) => c.path === "/forums/3/subscribe/")).toBe(true);
  });

  it("asks a student to accept the conduct statement before their first post, then starts the discussion", async () => {
    const { calls, onNavigate } = open({
      "GET /sites/": { body: sites() },
      "GET /forums/3/": { body: forum() },
      "GET /forums/3/threads/": { body: [] },
      "GET /conduct-statements/current/": { body: conduct(false) },
      "POST /conduct-statements/current/accept/": { body: conduct(true) },
      "POST /forums/3/threads/": { status: 201, body: thread({ id: 9 }) },
    });
    const user = userEvent.setup();
    expect(await screen.findByText("No discussions yet.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start a discussion" }));
    expect(await screen.findByRole("heading", { name: "Rules for forums and messages" })).toBeInTheDocument();
    expect(screen.getByText("Keep to the course.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Your post")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "I accept these rules" }));
    await user.type(await screen.findByLabelText("Title"), "Watering in the dry season");
    await user.type(screen.getByLabelText("Your post"), "How often should we **water**?");
    await user.click(screen.getByRole("button", { name: "Post" }));
    expect(calls.find((c) => c.method === "POST" && c.path === "/forums/3/threads/")?.body).toEqual({
      title: "Watering in the dry season",
      body: "<p>How often should we <strong>water</strong>?</p>",
      body_format: "html",
    });
    expect(onNavigate).toHaveBeenCalledWith("/forums/3/threads/9");
  });

  it("in a question-and-answer forum, lets only teaching staff ask, and explains it to students", async () => {
    open({
      "GET /sites/": { body: sites() },
      "GET /forums/3/": { body: forum({ forum_type: "question" }) },
      "GET /forums/3/threads/": { body: [thread()] },
    });
    expect(await screen.findByText(/Post your answer to see what others have written/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask a question" })).not.toBeInTheDocument();
  });

  it("shows a student their released participation mark in a graded forum", async () => {
    open({
      "GET /sites/": { body: sites() },
      "GET /forums/3/": { body: forum({ forum_type: "graded" }) },
      "GET /forums/3/threads/": { body: [] },
      "GET /forums/3/marks/": { body: [row({ mark: "8.00", feedback: "Thoughtful replies.", is_released: true })] },
    });
    expect(await screen.findByText("Your participation mark: 8.00 out of 10.00. Thoughtful replies.")).toBeInTheDocument();
  });

  it("lets teaching staff give participation marks against each student's posts, and release them", async () => {
    const { calls } = open({
      "GET /sites/": { body: sites({ my_role: "lecturer" }) },
      "GET /forums/3/": { body: forum({ forum_type: "graded" }) },
      "GET /forums/3/threads/": { body: [] },
      "GET /forums/3/marks/": { body: [row(), row({ person_id: 22, name: "Tevin Joseph", student_no: "S2026902", posts: 0 })] },
      "POST /forums/3/marks/": { body: row({ mark: "7.50" }) },
      "POST /forums/3/release-marks/": { body: { released: 1 } },
    });
    const user = userEvent.setup();
    const marks = await screen.findByRole("list", { name: "Students" });
    expect(within(marks).getAllByRole("listitem")[0]).toHaveTextContent("3 posts");
    await user.type(screen.getByLabelText("Mark for Kezia Persaud"), "7.5");
    await user.type(screen.getByLabelText("Feedback for Kezia Persaud"), "Good questions");
    await user.click(within(within(marks).getAllByRole("listitem")[0]).getByRole("button", { name: "Save" }));
    expect(calls.find((c) => c.method === "POST" && c.path === "/forums/3/marks/")?.body).toEqual({
      student: 21,
      mark: "7.5",
      feedback: "Good questions",
    });
    expect(await screen.findByText("Saved Kezia Persaud's mark.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Release marks to students" }));
    expect(await screen.findByText("1 mark released to students.")).toBeInTheDocument();
    // Teaching staff ask in any forum.
    expect(screen.getByRole("button", { name: "Start a discussion" })).toBeInTheDocument();
  });

  it("says when the forum cannot be opened", async () => {
    open({ "GET /sites/": { body: sites() }, "GET /forums/3/": { status: 404, body: { detail: "Not found." } }, "GET /forums/3/threads/": { body: [] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});
