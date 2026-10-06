import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Conversation, ConversationDetail } from "../../api/types-talk";
import { FrameContext } from "../../app/frame";
import { flush, pending, pendingCount } from "../../app/offlineQueue";
import { fakeServer, offline } from "../../test/fetch";
import { conduct, sites } from "../forums/fixtures";
import { MessagesLink } from "./MessagesLink";
import { MessagesScreen } from "./MessagesScreen";

const conversation = (over: Partial<Conversation> = {}): Conversation => ({
  id: 12,
  site: 9,
  site_code: "AGR101-2026-27-S1-MRP",
  audience: "direct",
  subject: "Field trip on Friday",
  group: null,
  last_message_at: "2026-10-05T09:00:00Z",
  unread: 2,
  may_send: true,
  ...over,
});

const detail = (over: Partial<ConversationDetail> = {}): ConversationDetail => ({
  conversation: conversation({ unread: 0 }),
  participants: [
    { name: "Kezia Persaud", last_read_at: "2026-10-05T09:00:00Z", may_send: true },
    { name: "Marlon Bacchus", last_read_at: "2026-10-05T09:30:00Z", may_send: true },
  ],
  messages: [
    { id: 1, sender_name: "Kezia Persaud", mine: true, body: "<p>May I bring my own boots?</p>", created_at: "2026-10-05T09:00:00Z", client_sent_at: null, read_by: ["Marlon Bacchus"] },
    { id: 2, sender_name: "Marlon Bacchus", mine: false, body: "<p>Yes, please do.</p>", created_at: "2026-10-05T09:20:00Z", client_sent_at: null, read_by: [] },
  ],
  ...over,
});

function open(conversationId: number | null, routes: Record<string, unknown>, query = "") {
  const server = fakeServer(routes as Parameters<typeof fakeServer>[0]);
  const onNavigate = vi.fn();
  render(
    <FrameContext.Provider value={{ setCrumb: vi.fn(), decided: vi.fn() }}>
      <MessagesScreen conversationId={conversationId} query={query} onNavigate={onNavigate} />
    </FrameContext.Provider>,
  );
  return { ...server, onNavigate };
}

describe("messages (item 4.11)", () => {
  it("lists conversations with what is unread and which are notices", async () => {
    open(null, {
      "GET /conversations/": { body: [conversation(), conversation({ id: 13, audience: "site", subject: "Lab closed", unread: 0, may_send: false })] },
    });
    const list = await screen.findByRole("list", { name: "Conversations" });
    const rows = within(list).getAllByRole("link");
    expect(rows[0]).toHaveTextContent("Field trip on Friday");
    expect(rows[0]).toHaveTextContent("2 unread");
    expect(rows[1]).toHaveTextContent("Notice to the whole course");
  });

  it("lets a student write to the teaching staff after accepting the conduct statement", async () => {
    const { calls, onNavigate } = open(null, {
      "GET /conversations/": { body: [] },
      "GET /sites/": { body: sites() },
      "GET /conversations/recipients/": { body: [{ person_id: 30, name: "Marlon Bacchus", role: "lecturer" }] },
      "GET /conduct-statements/current/": { body: conduct(false) },
      "POST /conduct-statements/current/accept/": { body: conduct(true) },
      "POST /conversations/": { status: 201, body: conversation({ id: 14 }) },
    });
    const user = userEvent.setup();
    expect(await screen.findByText("No messages yet.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New message" }));
    await user.click(await screen.findByRole("button", { name: "I accept these rules" }));
    // On one course only, the course is chosen already.
    await waitFor(() => expect(screen.getByLabelText("Course")).toHaveValue("9"));
    await user.click(await screen.findByLabelText(/Marlon Bacchus/));
    await user.type(screen.getByLabelText("Subject"), "Boots");
    await user.type(screen.getByLabelText("Message"), "May I bring my own?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    const sent = calls.find((c) => c.method === "POST" && c.path === "/conversations/")!;
    expect(sent.body).toMatchObject({ site: 9, audience: "direct", subject: "Boots", body: "<p>May I bring my own?</p>", body_format: "html", recipients: [30] });
    expect(sent.headers.get("Idempotency-Key")).toMatch(/[0-9a-f-]{36}/);
    expect(onNavigate).toHaveBeenCalledWith("/messages/14");
  });

  it("lets teaching staff send a notice to a group", async () => {
    const { calls } = open(
      null,
      {
        "GET /conversations/": { body: [] },
        "GET /sites/": { body: sites({ my_role: "lecturer" }) },
        "GET /conversations/recipients/": { body: [{ person_id: 21, name: "Kezia Persaud", role: "student" }] },
        "GET /groups/": { body: { count: 1, next: null, previous: null, results: [{ id: 4, site: 9, name: "Lab group A", members: [] }] } },
        "GET /conduct-statements/current/": { body: conduct(true) },
        "POST /conversations/": { status: 201, body: conversation() },
      },
      "site=9",
    );
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText("A group, as a notice"));
    await user.selectOptions(await screen.findByLabelText("Group"), "4");
    expect(screen.getByText(/Students read a notice but do not reply/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Subject"), "Lab moved");
    await user.type(screen.getByLabelText("Message"), "Room 4 today.");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ audience: "group", group: 4, subject: "Lab moved" });
  });

  it("shows a conversation with read receipts, marks it read, and keeps a message without a connection until it is sent", async () => {
    const { calls } = open(12, {
      "GET /conversations/12/": [{ body: detail() }, { body: detail() }],
      "POST /conversations/12/read/": { body: { last_read_at: "2026-10-05T10:00:00Z" } },
      "GET /conduct-statements/current/": { body: conduct(true) },
      "POST /conversations/12/messages/": [offline, { status: 201, body: {} }],
    });
    const user = userEvent.setup();
    const messages = await screen.findByRole("list", { name: "Messages" });
    expect(within(messages).getAllByRole("listitem")[0]).toHaveTextContent("Read");
    expect(within(messages).getAllByRole("listitem")[1]).toHaveTextContent("Yes, please do.");
    expect(calls.some((c) => c.path === "/conversations/12/read/")).toBe(true);

    await user.type(await screen.findByLabelText("Your message"), "Thank you");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Waiting to send. It is sent when the connection returns.")).toBeInTheDocument();
    expect(pendingCount()).toBe(1);
    const key = pending()[0].idempotencyKey;
    expect(key).toBeTruthy();
    await flush();
    expect(await screen.findByText("Sent")).toBeInTheDocument();
    const tries = calls.filter((c) => c.method === "POST" && c.path === "/conversations/12/messages/");
    expect(tries).toHaveLength(2);
    expect(tries[1].headers.get("Idempotency-Key")).toBe(key);
  });

  it("says a notice takes no replies and offers to write to the staff", async () => {
    const { onNavigate } = open(13, {
      "GET /conversations/13/": { body: detail({ conversation: conversation({ id: 13, audience: "site", may_send: false }) }) },
      "POST /conversations/13/read/": { body: {} },
    });
    expect(await screen.findByText(/This is a notice from the teaching staff/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Write to the teaching staff" }));
    expect(onNavigate).toHaveBeenCalledWith("/messages?site=9");
  });

  it("says when a conversation cannot be opened", async () => {
    open(99, { "GET /conversations/99/": { status: 404, body: { detail: "Not found." } }, "POST /conversations/99/read/": { status: 404, body: {} } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});

describe("the header's Messages link", () => {
  it("counts unread messages across conversations", async () => {
    fakeServer({ "GET /conversations/": { body: [conversation(), conversation({ id: 13, unread: 1 })] } });
    const go = vi.fn();
    render(<MessagesLink path="/" onNavigate={go} />);
    const link = await screen.findByRole("link", { name: "Messages, 3 unread" });
    await userEvent.click(link);
    expect(go).toHaveBeenCalledWith("/messages");
  });
});
