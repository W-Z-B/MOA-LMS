import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { PostReport } from "../../api/types-talk";
import { fakeServer } from "../../test/fetch";
import { DiscussionTab } from "./DiscussionTab";
import { forum, sites } from "./fixtures";
import { ForumsScreen } from "./ForumsScreen";

const report: PostReport = {
  id: 11,
  post: 72,
  thread: 7,
  forum: 3,
  site: 9,
  reason: "Advertising a shop",
  status: "open",
  created_at: "2026-10-05T09:00:00Z",
  reviewed_at: null,
  review_note: "",
};

describe("a course's Discussion tab (items 4.08 to 4.10)", () => {
  it("lists the forums a student can see, each with its kind, and no authoring", async () => {
    fakeServer({
      "GET /forums/": { body: [forum(), forum({ id: 4, title: "Week 2 questions", forum_type: "question", threads: 0, subscribed: true })] },
    });
    render(<DiscussionTab siteId={9} teaching={false} />);
    const list = await screen.findByRole("list", { name: "Forums" });
    const links = within(list).getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "#/forums/3");
    expect(links[0]).toHaveTextContent("General discussion · 1 discussion");
    expect(links[1]).toHaveTextContent("Question and answer · 0 discussions · You get notices");
    expect(screen.queryByRole("button", { name: "New forum" })).not.toBeInTheDocument();
  });

  it("lets teaching staff add a graded forum, and review reports: removing needs a reason", async () => {
    const { calls } = fakeServer({
      "GET /forums/": [{ body: [] }, { body: [forum({ forum_type: "graded" })] }],
      "POST /forums/": { status: 201, body: forum() },
      "GET /post-reports/": [{ body: { count: 1, next: null, previous: null, results: [report, { ...report, id: 12, site: 99 }] } }, { body: [] }],
      "POST /post-reports/11/review/": { body: { ...report, status: "removed" } },
    });
    const user = userEvent.setup();
    render(<DiscussionTab siteId={9} teaching />);
    expect(await screen.findByText("No forums yet. Add one for the class.")).toBeInTheDocument();

    // The queue shows this course's reports only.
    const queue = await screen.findByRole("region", { name: "Reports waiting for review" });
    expect(within(queue).getAllByText(/Advertising a shop/)).toHaveLength(1);
    expect(within(queue).getByRole("link", { name: "Open the post" })).toHaveAttribute("href", "#/forums/3/threads/7");
    await user.click(within(queue).getByRole("button", { name: "Remove the post" }));
    expect(within(queue).getByRole("alert")).toHaveTextContent("Say why the post is removed");
    await user.type(within(queue).getByLabelText("Reason or note"), "Advertising is not allowed");
    await user.click(within(queue).getByRole("button", { name: "Remove the post" }));
    expect(calls.find((c) => c.path === "/post-reports/11/review/")?.body).toEqual({ decision: "remove", note: "Advertising is not allowed" });

    await user.click(screen.getByRole("button", { name: "New forum" }));
    await user.type(screen.getByLabelText("Title"), "Field trip discussion");
    await user.selectOptions(screen.getByLabelText("Kind of forum"), "graded");
    expect(screen.getByText(/earn a participation mark/)).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Weight in coursework"));
    await user.type(screen.getByLabelText("Weight in coursework"), "5");
    await user.click(screen.getByRole("button", { name: "Add forum" }));
    expect(calls.find((c) => c.method === "POST" && c.path === "/forums/")?.body).toMatchObject({
      site: 9,
      title: "Field trip discussion",
      forum_type: "graded",
      weight: "5",
      max_mark: "10",
      body_format: "text",
    });
    expect(await screen.findByRole("link", { name: /Crop questions/ })).toBeInTheDocument();
  });

  it("says why a forum could not be added, and keeps the form", async () => {
    fakeServer({
      "GET /forums/": { body: [] },
      "GET /post-reports/": { body: [] },
      "POST /forums/": { status: 400, body: { weight: ["Only a graded forum counts towards coursework."] } },
    });
    const user = userEvent.setup();
    render(<DiscussionTab siteId={9} teaching />);
    await user.click(await screen.findByRole("button", { name: "New forum" }));
    await user.type(screen.getByLabelText("Title"), "Notes");
    await user.click(screen.getByRole("button", { name: "Add forum" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("weight: Only a graded forum counts towards coursework.");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "New forum" })).toBeInTheDocument();
  });
});

describe("Discussion across courses (#/forums)", () => {
  it("groups the forums by course, with the reports for those who moderate", async () => {
    fakeServer({
      "GET /sites/": { body: sites({ my_role: "lecturer" }) },
      "GET /forums/": { body: [forum()] },
      "GET /post-reports/": { body: [report] },
      "POST /post-reports/11/review/": { body: { ...report, status: "restored" } },
    });
    const user = userEvent.setup();
    render(<ForumsScreen />);
    expect(await screen.findByRole("heading", { name: "Introduction to Crop Production" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Introduction to Crop Production" })).toHaveAttribute("href", "#/sites/9/discussion");
    expect(screen.getByRole("link", { name: /Crop questions/ })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Keep the post" }));
  });

  it("says when no course has a forum", async () => {
    fakeServer({ "GET /sites/": { body: sites() }, "GET /forums/": { body: [] } });
    render(<ForumsScreen />);
    expect(await screen.findByText("None of your courses has a forum yet.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Reports waiting for review" })).not.toBeInTheDocument();
  });

  it("says when the forums cannot be read", async () => {
    fakeServer({ "GET /sites/": { body: sites() }, "GET /forums/": { status: 500, body: { detail: "Server error" } } });
    render(<ForumsScreen />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error");
  });
});
