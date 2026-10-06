import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ThreadDetail } from "../../api/types-talk";
import { FrameContext } from "../../app/frame";
import { fakeServer } from "../../test/fetch";
import { conduct, forum, postOf, thread } from "./fixtures";
import { ThreadScreen } from "./ThreadScreen";

const detail = (over: Partial<ThreadDetail> = {}): ThreadDetail => ({
  thread: thread(),
  posts: [postOf()],
  replies_hidden: false,
  subscribed: true,
  moderator: false,
  ...over,
});

function open(routes: Record<string, unknown>) {
  const server = fakeServer(routes as Parameters<typeof fakeServer>[0]);
  const setCrumb = vi.fn();
  render(
    <FrameContext.Provider value={{ setCrumb, decided: vi.fn() }}>
      <ThreadScreen forumId={3} threadId={7} />
    </FrameContext.Provider>,
  );
  return { ...server, setCrumb };
}

describe("a discussion in a question-and-answer forum (items 4.08, 4.09)", () => {
  it("hides others' answers until the student posts their own, after accepting the conduct statement", async () => {
    const { calls, setCrumb } = open({
      "GET /forums/3/": { body: forum({ forum_type: "question" }) },
      "GET /threads/7/": [
        { body: detail({ replies_hidden: true }) },
        {
          body: detail({
            posts: [
              postOf(),
              postOf({ id: 71, parent: 70, author_name: "Kezia Persaud", body: "<p>45 cm</p>", can_edit: true, created_at: new Date().toISOString() }),
              postOf({ id: 72, parent: 70, author_name: "Tevin Joseph", body: "<p>Half a metre</p>" }),
            ],
          }),
        },
      ],
      "GET /conduct-statements/current/": { body: conduct(false) },
      "POST /conduct-statements/current/accept/": { body: conduct(true) },
      "POST /threads/7/replies/": { status: 201, body: postOf({ id: 71 }) },
    });
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: "Spacing of tomato plants", level: 1 })).toBeInTheDocument();
    await waitFor(() => expect(setCrumb).toHaveBeenCalledWith("Spacing of tomato plants"));
    expect(screen.getByText(/post your answer to see what others have written/)).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "I accept these rules" }));
    await user.type(await screen.findByLabelText("Your answer"), "45 cm");
    await user.click(screen.getByRole("button", { name: "Post your answer" }));
    expect(calls.find((c) => c.path === "/threads/7/replies/")?.body).toEqual({ body: "<p>45 cm</p>", body_format: "html" });
    expect(await screen.findByText("Your answer is posted. Others' answers are shown now.")).toBeInTheDocument();
    expect(await screen.findByText("Half a metre")).toBeInTheDocument();
    // Their own post can be changed for 30 minutes; others' can be reported.
    const mine = screen.getByRole("article", { name: "Post by Kezia Persaud" });
    expect(within(mine).getByText(/You can change or remove your post until/)).toBeInTheDocument();
    expect(within(mine).queryByRole("button", { name: "Report" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("article", { name: "Post by Tevin Joseph" })).getByRole("button", { name: "Report" })).toBeInTheDocument();
  });
});

describe("a discussion (items 4.08, 4.09)", () => {
  it("lets the author change their post within the window", async () => {
    const { calls } = open({
      "GET /forums/3/": { body: forum() },
      "GET /threads/7/": { body: detail({ posts: [postOf({ can_edit: true, created_at: new Date().toISOString(), body: "<p>Plant <strong>45 cm</strong> apart</p>" })] }) },
      "GET /conduct-statements/current/": { body: conduct(true) },
      "PATCH /posts/70/": { body: postOf() },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Change" }));
    const box = screen.getByLabelText("Change your post");
    expect(box).toHaveValue("Plant **45 cm** apart");
    await user.type(box, " in rows");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ body: "<p>Plant <strong>45 cm</strong> apart in rows</p>", body_format: "html" });
    expect(await screen.findByText("Your post is changed.")).toBeInTheDocument();
  });

  it("reports someone else's post with the rule it breaks, and replies to one post", async () => {
    const { calls } = open({
      "GET /forums/3/": { body: forum() },
      "GET /threads/7/": { body: detail({ posts: [postOf(), postOf({ id: 72, parent: 70, author_name: "Tevin Joseph", body: "<p>Buy seeds at my shop</p>" })] }) },
      "GET /conduct-statements/current/": { body: conduct(true) },
      "POST /posts/72/report/": { status: 201, body: {} },
      "POST /threads/7/replies/": { status: 201, body: postOf({ id: 73 }) },
    });
    const user = userEvent.setup();
    const tevin = await screen.findByRole("article", { name: "Post by Tevin Joseph" });
    await user.click(within(tevin).getByRole("button", { name: "Report" }));
    await user.type(screen.getByLabelText("Which rule does it break?"), "Advertising");
    await user.click(screen.getByRole("button", { name: "Send report" }));
    expect(calls.find((c) => c.path === "/posts/72/report/")?.body).toEqual({ reason: "Advertising" });
    expect(await screen.findByText("Reported. A moderator will review it.")).toBeInTheDocument();

    await user.click(within(screen.getByRole("article", { name: "Post by Tevin Joseph" })).getByRole("button", { name: "Reply" }));
    expect(screen.getByText(/Replying to Tevin Joseph/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your reply"), "Please keep to the course.");
    await user.click(screen.getByRole("button", { name: "Post reply" }));
    expect(calls.find((c) => c.path === "/threads/7/replies/")?.body).toEqual({
      body: "<p>Please keep to the course.</p>",
      body_format: "html",
      parent: 72,
    });
  });

  it("lets a moderator pin, lock, and remove a post with a reason everyone sees", async () => {
    const { calls } = open({
      "GET /forums/3/": { body: forum() },
      "GET /threads/7/": [
        { body: detail({ moderator: true, posts: [postOf(), postOf({ id: 72, parent: 70, author_name: "Tevin Joseph", hidden: true })] }) },
        {
          body: detail({
            moderator: true,
            posts: [postOf(), postOf({ id: 72, parent: 70, author_name: "Tevin Joseph", removed: true, body: "", removed_reason: "Advertising" })],
          }),
        },
      ],
      "GET /conduct-statements/current/": { body: conduct(true) },
      "POST /threads/7/pin/": { body: thread({ is_pinned: true }) },
      "POST /threads/7/lock/": { body: thread({ is_locked: true }) },
      "POST /posts/72/remove/": { body: postOf() },
    });
    const user = userEvent.setup();
    const tevin = await screen.findByRole("article", { name: "Post by Tevin Joseph" });
    expect(within(tevin).getByText("Hidden while a report is reviewed")).toBeInTheDocument();
    await user.click(within(tevin).getByRole("button", { name: "Remove" }));
    await user.type(screen.getByLabelText(/Why is it removed/), "Advertising");
    await user.click(screen.getByRole("button", { name: "Remove post" }));
    expect(calls.find((c) => c.path === "/posts/72/remove/")?.body).toEqual({ reason: "Advertising" });
    expect(await screen.findByText("This post was removed: Advertising")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Pin to the top" }));
    expect(calls.find((c) => c.path === "/threads/7/pin/")?.body).toEqual({ value: true });
    await user.click(screen.getByRole("button", { name: "Lock" }));
    expect(calls.find((c) => c.path === "/threads/7/lock/")?.body).toEqual({ value: true });
    expect(await screen.findByText("The discussion is locked.")).toBeInTheDocument();
  });

  it("takes no replies from students in a locked discussion, and shows the server's refusals", async () => {
    open({
      "GET /forums/3/": { body: forum() },
      "GET /threads/7/": { body: detail({ thread: thread({ is_locked: true }), posts: [postOf({ hidden: true, body: "" })] }) },
    });
    expect(await screen.findByText("This discussion is locked: no new replies.")).toBeInTheDocument();
    expect(screen.getByText("This post is hidden while a moderator reviews a report.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reply" })).not.toBeInTheDocument();
  });

  it("asks again for the conduct statement when a new version is in force", async () => {
    open({
      "GET /forums/3/": { body: forum() },
      "GET /threads/7/": { body: detail() },
      "GET /conduct-statements/current/": [{ body: conduct(true) }, { body: conduct(false) }],
      "POST /threads/7/replies/": { status: 403, body: { code: "conduct_not_accepted", detail: "Read and accept the conduct statement before you post." } },
    });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Your reply"), "Thanks");
    await user.click(screen.getByRole("button", { name: "Post reply" }));
    expect(await screen.findByRole("button", { name: "I accept these rules" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Read and accept the conduct statement");
  });

  it("says when the discussion cannot be opened", async () => {
    open({ "GET /forums/3/": { body: forum() }, "GET /threads/7/": { status: 404, body: { detail: "Not found." } } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});
