import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Site } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { book, page, site, working } from "../../test/marking";
import { GradebookTab } from "./GradebookTab";

function show(as: Site, teaching: boolean, routes: Record<string, unknown> = {}) {
  const server = fakeServer({
    "GET /sites/9/gradebook/": { body: book },
    "GET /sites/9/coursework/working/": { body: working },
    ...(routes as Record<string, { body?: unknown }>),
  });
  render(<GradebookTab site={as} teaching={teaching} />);
  return server;
}

describe("the gradebook (items 2.28 to 2.31, 3.18)", () => {
  it("lists assignments, quizzes, practical tasks, forums and categories, keeps anonymous marks hidden, and shows the SRMS lock", async () => {
    show(site, true);
    const table = await screen.findByRole("region", { name: "Gradebook" });
    const head = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(head).toEqual([
      "Student",
      "Soil profile report / 20",
      "Blind essay / 10",
      "Soil quiz (quiz %)",
      "Take a core (practical %)",
      "Fertiliser debate (forum %)",
      "Reports (%)",
      "Coursework %",
      "SRMS",
    ]);
    const [, ria, andre] = within(table).getAllByRole("row");
    expect(within(ria).getAllByRole("cell").map((c) => c.textContent)).toEqual([
      "S2026911 Ria Ramdial",
      "14",
      "Hidden (anonymous)",
      "80.00",
      "Missing, counted as 0",
      "90.00",
      "70.00",
      "61.50",
      "Accepted 03/10/2026 · locked since 03/10/2026",
    ]);
    expect(andre).toHaveTextContent("Not yet due");
    expect(screen.getByRole("link", { name: "Export to a spreadsheet" })).toHaveAttribute("href", "/api/v1/sites/9/gradebook/export/");
  });

  it("opens the working of a student's total: counted, pending for anonymous marking, zero, penalty and categories", async () => {
    const { calls } = show(site, true);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "How Ria Ramdial's total is worked out" }));
    const panel = await screen.findByRole("region", { name: "How Ria Ramdial's coursework total is worked out" });
    expect(calls.some((c) => c.path === "/sites/9/coursework/working/?person=101")).toBe(true);
    expect(panel).toHaveTextContent("Coursework total for Ria Ramdial (S2026911): 61.50%");
    expect(panel).toHaveTextContent("15 less a late penalty of 1 = 14 out of 20");
    expect(panel).toHaveTextContent("Due 01/10/2026");
    expect(panel).toHaveTextContent("(extended) · handed in late · Reports");
    expect(within(panel).getByText("Pending (anonymous marking)")).toBeInTheDocument();
    expect(within(panel).getByText("Missing, counted as 0")).toBeInTheDocument();
    expect(within(panel).getByText("Dropped (lowest)")).toBeInTheDocument();
    expect(within(panel).getByRole("list", { name: "Categories" })).toHaveTextContent("Reports weight 60, lowest 1 dropped70.00%");
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("region", { name: /coursework total is worked out/ })).not.toBeInTheDocument();
  });

  it("sends the coursework to the SRMS and shows what each student's total became", async () => {
    const sent = {
      site: "AGR205",
      sent_at: "2026-10-05T12:00:00Z",
      accepted: ["S2026911"],
      locked: ["S2026912"],
      unknown: [],
      students: [
        { student_no: "S2026911", percent: "61.50", outcome: "accepted" },
        { student_no: "S2026912", percent: "40.00", outcome: "locked" },
      ],
    };
    const { calls } = show(site, true, { "POST /sites/9/coursework/send/": { body: sent } });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Send coursework to the SRMS" }));
    const result = await screen.findByRole("list", { name: "Each student" });
    expect(screen.getByText(/1 accepted, 1 already locked in the SRMS/)).toBeInTheDocument();
    expect(within(result).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["S2026911: 61.50%Accepted", "S2026912: 40.00%Already locked"]);
    expect(calls.filter((c) => c.path === "/sites/9/gradebook/").length).toBe(2); // shown again, with the lock
  });

  it("says why the SRMS did not take the coursework, and offers no sending on a course it does not hold", async () => {
    show(site, true, { "POST /sites/9/coursework/send/": { status: 502, body: { code: "srms_unavailable", detail: "The SRMS could not take the coursework now." } } });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Send coursework to the SRMS" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The SRMS could not take the coursework now.");
  });

  it("edits the categories with their weights and drop-lowest rule", async () => {
    const reports = { id: 5, site: 9, name: "Reports", weight: "60.00", drop_lowest: 0, position: 1 };
    const { calls } = show({ ...site, source: "local" }, true, {
      "GET /grade-categories/": page([reports]),
      "PATCH /grade-categories/5/": { body: reports },
      "POST /grade-categories/": { status: 201, body: reports },
      "DELETE /grade-categories/5/": { status: 204 },
    });
    const user = userEvent.setup();
    expect(await screen.findByRole("region", { name: "Gradebook" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send coursework to the SRMS" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Categories and weights" }));
    const reportsForm = await screen.findByRole("form", { name: "Category Reports" });
    await user.clear(within(reportsForm).getByLabelText("Drop lowest"));
    await user.type(within(reportsForm).getByLabelText("Drop lowest"), "1");
    await user.click(within(reportsForm).getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ name: "Reports", weight: "60", drop_lowest: 1 });

    const added = screen.getByRole("form", { name: "New category" });
    await user.type(within(added).getByLabelText("New category"), "Practicals");
    await user.type(within(added).getByLabelText("Weight"), "40");
    await user.click(within(added).getByRole("button", { name: "Add" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ site: 9, name: "Practicals", weight: "40", drop_lowest: 0, position: 2 });
    await user.click(within(reportsForm).getByRole("button", { name: "Remove" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("shows a student their own row and how their total is worked out", async () => {
    const own = { ...book, rows: [book.rows[0]] };
    show({ ...site, my_role: "student" }, false, { "GET /sites/9/gradebook/": { body: own } });
    const table = await screen.findByRole("region", { name: "Gradebook" });
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(within(table).queryByRole("columnheader", { name: "SRMS" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Export to a spreadsheet" })).not.toBeInTheDocument();
    const panel = await screen.findByRole("region", { name: "How your coursework total is worked out" });
    expect(panel).toHaveTextContent("Coursework total: 61.50%");
    expect(panel).toHaveTextContent("15 less a late penalty of 1 = 14 out of 20");
  });

  it("says when the gradebook cannot be loaded, and when nobody is enrolled", async () => {
    fakeServer({ "GET /sites/9/gradebook/": { status: 403, body: { code: "forbidden", detail: "You are not a member of this course." } } });
    const { unmount } = render(<GradebookTab site={site} teaching />);
    expect(await screen.findByRole("alert")).toHaveTextContent("You are not a member of this course.");
    unmount();
    fakeServer({ "GET /sites/9/gradebook/": { body: { ...book, rows: [] } } });
    render(<GradebookTab site={site} teaching />);
    expect(await screen.findByText("No students in this course.")).toBeInTheDocument();
  });
});
