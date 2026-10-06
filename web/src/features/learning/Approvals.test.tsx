import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Delegation } from "../../api/types-staff";
import { fakeServer } from "../../test/fetch";
import { courseAdmin, page, request, staff } from "../../test/staff";
import { Approvals } from "./Approvals";

const standIn = (over: Partial<Delegation> = {}): Delegation => ({
  id: 2,
  delegator: 21,
  delegator_name: "Marlon Bacchus",
  delegate: 22,
  delegate_name: "Joy Lall",
  starts: "2026-10-01",
  ends: "2099-10-10",
  reason: "Leave",
  cancelled: false,
  in_force: true,
  created_at: "2026-09-30T10:00:00Z",
  ...over,
});

describe("approvals (item 5.02)", () => {
  it("approves a request, and turns one down only with a reason, putting the request from To do first", async () => {
    const server = fakeServer({
      "GET /staff-development/requests/?state=submitted": [
        page([request(), request({ id: 7, person_name: "Ravi Ram", approver: 99, approver_name: "Mark Boss" }), request({ id: 8, allowed_actions: ["withdraw"] })]),
        page([request({ id: 7, person_name: "Ravi Ram" })]),
      ],
      "GET /approvals/delegations/": page([]),
      "POST /staff-development/requests/5/approve/": { body: request({ state: "approved" }) },
      "POST /staff-development/requests/7/reject/": { body: request({ id: 7, state: "rejected" }) },
    });
    render(<Approvals me={staff} highlight={7} />);
    const list = await screen.findByRole("list", { name: "Requests to decide" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2); // my own request (withdraw only) is not mine to decide
    expect(items[0]).toHaveTextContent("Ravi Ram: First aid in the field");
    expect(items[0]).toHaveAttribute("aria-current", "true");
    expect(items[0]).toHaveTextContent("Sent to Mark Boss; you decide as their stand-in.");
    await userEvent.click(within(items[0]).getByRole("button", { name: "Turn down: Ravi Ram, First aid in the field" }));
    expect(await within(items[0]).findByRole("alert")).toHaveTextContent("Say why the request is turned down.");
    await userEvent.click(within(items[1]).getByRole("button", { name: "Approve: Joy Lall, First aid in the field" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Joy Lall is on First aid in the field.");
    expect(server.calls.find((c) => c.path.endsWith("/approve/"))?.body).toEqual({ comment: "" });
    const left = await screen.findByRole("list", { name: "Requests to decide" });
    await userEvent.type(within(left).getByLabelText("Comment (needed to turn it down)"), "Full this term.");
    await userEvent.click(within(left).getByRole("button", { name: /^Turn down/ }));
    expect(await screen.findByText("Ravi Ram's request to join First aid in the field is turned down.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.path.endsWith("/reject/"))?.body).toEqual({ comment: "Full this term." });
  });

  it("names a stand-in found by name, and ends one", async () => {
    const server = fakeServer({
      "GET /staff-development/requests/?state=submitted": page([]),
      "GET /approvals/delegations/": [page([standIn(), standIn({ id: 3, cancelled: true, in_force: false })]), page([standIn({ cancelled: true, in_force: false })])],
      "GET /approvals/colleagues/?q=jo": [{ body: [] }, { body: [{ id: 22, name: "Joy Lall", employee_no: "E0201" }] }],
      "POST /approvals/delegations/": { status: 201, body: standIn() },
      "POST /approvals/delegations/2/end/": { body: standIn({ cancelled: true }) },
    });
    render(<Approvals me={staff} highlight={null} />);
    expect(await screen.findByText("Nothing is waiting for your decision.")).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Stand-ins" });
    expect(within(list).getAllByRole("listitem")[0]).toHaveTextContent("Joy Lall for Marlon BacchusIn force01/10/2026 to 10/10/2099 · Leave");
    expect(within(list).getAllByRole("listitem")[1]).toHaveTextContent("Ended");
    expect(within(list).getAllByRole("button", { name: /^End/ })).toHaveLength(1);

    const user = userEvent.setup();
    await user.click(within(list).getByRole("button", { name: "End: Joy Lall for Marlon Bacchus" }));
    expect(await screen.findByText("Joy Lall no longer stands in for Marlon Bacchus.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Colleague's name or employee number"), "jo");
    await user.click(screen.getByRole("button", { name: "Find" }));
    expect(await screen.findByText("Nobody on the staff matches.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Find" }));
    await user.click(await screen.findByRole("button", { name: "Choose Joy Lall" }));
    await user.click(screen.getByRole("button", { name: "Choose someone else" }));
    await user.click(await screen.findByRole("button", { name: "Choose Joy Lall" }));
    await user.type(screen.getByLabelText("From"), "2026-10-20");
    await user.type(screen.getByLabelText("To"), "2026-10-24");
    await user.type(screen.getByLabelText("Why (leave, travel)"), "Leave");
    await user.click(screen.getByRole("button", { name: "Name the stand-in" }));
    expect(await screen.findByText("Joy Lall stands in for you from 20/10/2026 to 24/10/2026.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.path === "/approvals/delegations/" && c.method === "POST")?.body).toEqual({
      delegate: 22,
      starts: "2026-10-20",
      ends: "2026-10-24",
      reason: "Leave",
    });

  });

  it("lets a course administrator end anyone's stand-in, but not name their own without a staff record", async () => {
    fakeServer({
      "GET /staff-development/requests/?state=submitted": { status: 500, body: { code: "error", detail: "Server error." } },
      "GET /approvals/delegations/": page([standIn({ delegator: 99, delegator_name: "Mark Boss" })]),
    });
    render(<Approvals me={{ ...courseAdmin, person_kind: null }} highlight={null} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error.");
    expect(await screen.findByRole("button", { name: "End: Joy Lall for Mark Boss" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Name a stand-in" })).not.toBeInTheDocument();
  });
});
