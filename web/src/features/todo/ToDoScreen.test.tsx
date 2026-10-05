import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { WaitingItem } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { ToDoScreen } from "./ToDoScreen";

const item = (over: Partial<WaitingItem>): WaitingItem => ({
  kind: "submission",
  kind_name: "Work to mark",
  title: "Germination trial report: 2 to mark",
  since: "2026-09-20T10:00:00Z",
  due_at: null,
  waited_days: 15,
  overdue: true,
  link: "/sites/9/assignments",
  site_title: "Introduction to Crop Production",
  ...over,
});

describe("To do (item 2.07)", () => {
  it("lists what waits, oldest first, how long it has waited, marks the overdue, and opens each where it is done", async () => {
    fakeServer({
      "GET /to-do/": {
        body: [
          item({}),
          item({ kind: "takedown", kind_name: "Takedown request to review", title: "Soil map: copied", waited_days: 1, overdue: false, link: "/sites/9", since: "2026-10-04T10:00:00Z" }),
          item({ kind: "assignment", kind_name: "Work due", title: "Field notebook check", due_at: "2026-10-08T14:00:00Z", overdue: false, waited_days: 0 }),
        ],
      },
    });
    const go = vi.fn();
    render(<ToDoScreen onNavigate={go} />);
    expect(await screen.findByText("3 things wait for you, oldest first; 1 overdue.")).toBeInTheDocument();
    const rows = within(screen.getByRole("list", { name: "Waiting for you" })).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Work to mark");
    expect(rows[0]).toHaveTextContent("Waiting since 20/09/2026, 15 days · Introduction to Crop Production");
    expect(within(rows[0]).getByText("Overdue")).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent("Waiting since 04/10/2026, 1 day");
    expect(within(rows[1]).queryByText("Overdue")).not.toBeInTheDocument();
    expect(rows[2]).toHaveTextContent(/Due 08\/10\/2026/);
    await userEvent.click(within(rows[1]).getByRole("button", { name: "Open: Soil map: copied" }));
    expect(go).toHaveBeenCalledWith("/sites/9");
  });

  it("says when nothing is waiting", async () => {
    fakeServer({ "GET /to-do/": { body: [] } });
    render(<ToDoScreen onNavigate={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Nothing is waiting for you" })).toBeInTheDocument();
    expect(screen.getByText("Nothing is waiting for you.")).toBeInTheDocument();
  });

  it("says when the list cannot be loaded", async () => {
    fakeServer({ "GET /to-do/": { status: 500, body: { code: "error", detail: "Server error." } } });
    render(<ToDoScreen onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
  });
});
