import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { LearningPath } from "../../api/types-staff";
import { fakeServer } from "../../test/fetch";
import { course, page, request } from "../../test/staff";
import { MyLearning } from "./MyLearning";
import { Paths } from "./Paths";

describe("My learning (items 5.02 to 5.05)", () => {
  it("lists my courses, my required training with its due date, and my requests, which I may withdraw", async () => {
    const server = fakeServer({
      "GET /staff-development/catalogue/": page([course({ my_status: "enrolled" }), course({ site: 50, title: "Not mine" })]),
      "GET /staff-development/requests/?mine=1": [
        page([request({ person_name: "Marlon Bacchus", approver_name: null, allowed_actions: ["withdraw"] }), request({ id: 6, state: "rejected", decision_comment: "Next term.", allowed_actions: [] })]),
        page([]),
      ],
      "GET /staff-development/required/mine/": {
        body: [
          { id: 1, site: 41, site_title: "Safe use of farm machinery", person: 21, person_name: "Marlon", employee_no: "E0901", campus_code: "MRP", assigned_on: "2026-09-01", due_on: "2026-10-01", completed_on: null, state: "overdue" },
          { id: 2, site: 42, site_title: "First aid in the field", person: 21, person_name: "Marlon", employee_no: "E0901", campus_code: "MRP", assigned_on: "2026-09-01", due_on: "2026-11-01", completed_on: "2026-10-05", state: "done" },
        ],
      },
      "POST /staff-development/requests/5/withdraw/": { body: request({ state: "withdrawn" }) },
    });
    const go = vi.fn();
    render(<MyLearning onNavigate={go} />);
    const mine = await screen.findByRole("list", { name: "My courses" });
    expect(within(mine).getAllByRole("listitem")).toHaveLength(1);
    expect(mine).toHaveTextContent("On the course");

    const required = await screen.findByRole("list", { name: "Required training" });
    expect(within(required).getAllByRole("listitem")[0]).toHaveTextContent("OverdueDue by 01/10/2026");
    expect(within(required).getAllByRole("listitem")[1]).toHaveTextContent("Completed 05/10/2026");
    await userEvent.click(within(required).getByRole("link", { name: "Safe use of farm machinery" }));
    expect(go).toHaveBeenCalledWith("/learning/41");

    const asked = await screen.findByRole("list", { name: "My requests to join" });
    expect(asked).toHaveTextContent("decided by the course administrators");
    expect(asked).toHaveTextContent("Next term.");
    await userEvent.click(within(asked).getByRole("button", { name: "Withdraw the request to join First aid in the field" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Your request to join First aid in the field is withdrawn.");
    expect(server.calls.some((c) => c.method === "POST" && c.path === "/staff-development/requests/5/withdraw/")).toBe(true);
    expect(await screen.findByText("You have not asked to join a course.")).toBeInTheDocument();
  });

  it("says so when there is nothing yet", async () => {
    fakeServer({
      "GET /staff-development/catalogue/": page([course()]),
      "GET /staff-development/requests/?mine=1": page([]),
      "GET /staff-development/required/mine/": { body: [] },
    });
    render(<MyLearning onNavigate={vi.fn()} />);
    expect(await screen.findByText(/You have not joined a course yet/)).toBeInTheDocument();
    expect(await screen.findByText("Nothing is required of you at the moment.")).toBeInTheDocument();
  });
});

const path: LearningPath = {
  id: 3,
  code: "induction",
  title: "New lecturer induction",
  description: "Your first term.",
  audience: "New lecturers",
  is_published: true,
  steps: [
    { position: 1, site: 41, title: "Safe use of farm machinery" },
    { position: 2, site: 42, title: "First aid in the field" },
  ],
};

describe("learning paths (item 5.04)", () => {
  it("lists the paths with how far along the person is, and opens one", async () => {
    fakeServer({
      "GET /staff-development/paths/": page([path, { ...path, id: 4, title: "Farm safety", is_published: false, steps: [path.steps[0]] }]),
      "GET /staff-development/paths/3/progress/": { body: { joined: true, done: 1, total: 2, complete: false, steps: [] } },
      "GET /staff-development/paths/4/progress/": { status: 404, body: { code: "no_person", detail: "No person." } },
    });
    const go = vi.fn();
    render(<Paths id={null} onNavigate={go} />);
    const list = await screen.findByRole("list", { name: "Learning paths" });
    expect(await within(list).findByText("1 of 2 done")).toBeInTheDocument();
    expect(within(list).getByRole("img", { name: "1 of 2 courses done" })).toBeInTheDocument();
    expect(within(list).getByText("Not published")).toBeInTheDocument();
    expect(list).toHaveTextContent("New lecturers · 2 courses");
    expect(list).toHaveTextContent("1 course");
    await userEvent.click(within(list).getByRole("link", { name: "Farm safety" }));
    expect(go).toHaveBeenCalledWith("/learning/paths/4");
  });

  it("shows a path's courses in order, each opening after the one before, and follows it", async () => {
    const before = { joined: false, done: 0, total: 2, complete: false, steps: [
      { position: 1, site: 41, title: "Safe use of farm machinery", state: "open", enrolled: false },
      { position: 2, site: 42, title: "First aid in the field", state: "locked", enrolled: false },
    ] };
    const server = fakeServer({
      "GET /staff-development/paths/3/": { body: path },
      "GET /staff-development/paths/3/progress/": { body: before },
      "POST /staff-development/paths/3/join/": { body: { ...before, joined: true } },
    });
    const go = vi.fn();
    render(<Paths id={3} onNavigate={go} />);
    const steps = await screen.findByRole("list", { name: "Courses on the path" });
    expect(await within(steps).findByText("Opens after the one before")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Follow this path" }));
    expect(await screen.findByRole("status")).toHaveTextContent("You are following the path.");
    expect(screen.queryByRole("button", { name: "Follow this path" })).not.toBeInTheDocument();
    expect(server.calls.some((c) => c.method === "POST")).toBe(true);
    await userEvent.click(within(steps).getByRole("link", { name: "2. First aid in the field" }));
    expect(go).toHaveBeenCalledWith("/learning/42");
  });

  it("says when there are no paths, or the path cannot be loaded", async () => {
    fakeServer({ "GET /staff-development/paths/": page([]), "GET /staff-development/paths/9/": { status: 404, body: { code: "not_found", detail: "Not found." } }, "GET /staff-development/paths/9/progress/": { status: 404, body: {} } });
    const { unmount } = render(<Paths id={null} onNavigate={vi.fn()} />);
    expect(await screen.findByText("There are no learning paths yet.")).toBeInTheDocument();
    unmount();
    render(<Paths id={9} onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});
