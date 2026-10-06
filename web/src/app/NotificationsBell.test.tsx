import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Notification } from "../api/types";
import { fakeServer } from "../test/fetch";
import { NotificationsBell } from "./NotificationsBell";

const note = (over: Partial<Notification>): Notification => ({
  id: 1,
  kind: "info",
  title: "AGR101: Welcome to the course",
  body: "",
  link: "/sites/1",
  created_at: "2026-10-05T12:00:00Z",
  read_at: null,
  ...over,
});

describe("Notifications", () => {
  it("shows the unread count, marks an item read and follows its link", async () => {
    const server = fakeServer({
      "GET /notifications/": [
        {
          body: {
            unread: 1,
            results: [note({}), note({ id: 2, title: "Marked: Soil report", read_at: "2026-10-04T12:00:00Z" })],
          },
        },
        { body: { unread: 0, results: [] } },
      ],
      "POST /notifications/1/read/": { body: { id: 1, read: true } },
    });
    const onNavigate = vi.fn();
    render(<NotificationsBell onNavigate={onNavigate} />);
    await userEvent.click(await screen.findByRole("button", { name: "Notifications, 1 unread" }));
    expect(screen.getByRole("dialog", { name: "Notifications" })).toBeInTheDocument();
    expect(screen.getByText("Marked: Soil report")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Welcome to the course/ }));
    expect(server.calls.some((c) => c.method === "POST" && c.path === "/notifications/1/read/")).toBe(true);
    expect(onNavigate).toHaveBeenCalledWith("/sites/1");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("marks everything read at once, and says when there is nothing", async () => {
    const server = fakeServer({
      "GET /notifications/": [
        { body: { unread: 2, results: [note({}), note({ id: 2 })] } },
        { body: { unread: 0, results: [] } },
      ],
      "POST /notifications/read-all/": { body: { marked: 2 } },
    });
    render(<NotificationsBell onNavigate={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: "Notifications, 2 unread" }));
    await userEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    expect(server.calls.some((c) => c.path === "/notifications/read-all/")).toBe(true);
    expect(await screen.findByText("Nothing yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Notifications, 0 unread" })).toBeInTheDocument();
  });
});
