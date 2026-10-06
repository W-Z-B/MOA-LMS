import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../../test/fetch";
import { administrator, auditor, courseAdmin, dpo, page, staff } from "../../test/staff";
import { AccessReview } from "./AccessReview";
import { Accounts } from "./Accounts";
import { AdminScreen } from "./AdminScreen";
import { IntegrationRuns } from "./IntegrationRuns";

const sections = (me: typeof staff) => {
  const { unmount } = render(<AdminScreen me={me} path="/admin" onNavigate={vi.fn()} />);
  const nav = screen.queryByRole("navigation", { name: "Admin sections" });
  const labels = nav ? within(nav).getAllByRole("link").map((a) => a.querySelector(".shortcut-title")?.textContent) : [];
  unmount();
  return labels;
};

describe("the console shows each section only to the roles the server allows (items 1.17 to 1.23)", () => {
  it("lists the sections by role, and nothing for anyone else", () => {
    expect(sections(administrator)).toEqual([
      "People to invite",
      "Integration runs",
      "Audit log",
      "Access review",
      "Privacy notice",
      "Correction requests",
      "Retention and disposal",
      "Breach register",
    ]);
    expect(sections(courseAdmin)).toEqual(["Integration runs", "Access review", "Correction requests"]);
    expect(sections(auditor)).toEqual(["Integration runs", "Audit log", "Access review", "Privacy notice", "Correction requests", "Retention and disposal", "Breach register"]);
    expect(sections(dpo)).toEqual(["Privacy notice", "Correction requests", "Retention and disposal", "Breach register"]);
    expect(sections(staff)).toEqual([]);
  });

  it("opens a section from its address, names it in the breadcrumb, and shows nothing at an address not the person's", async () => {
    fakeServer({ "GET /integration-runs/": page([]) });
    const go = vi.fn();
    const { unmount } = render(<AdminScreen me={courseAdmin} path="/admin" onNavigate={go} />);
    await userEvent.click(screen.getByRole("link", { name: /Integration runs/ }));
    expect(go).toHaveBeenCalledWith("/admin/integration");
    unmount();
    const open = render(<AdminScreen me={courseAdmin} path="/admin/integration" onNavigate={go} />);
    expect(screen.getByRole("heading", { name: "Integration runs", level: 1 })).toBeInTheDocument();
    expect(await screen.findByText("No runs match.")).toBeInTheDocument();
    open.unmount();
    render(<AdminScreen me={courseAdmin} path="/admin/audit" onNavigate={go} />);
    expect(screen.getByText("There is nothing here for you.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Audit log" })).not.toBeInTheDocument();
  });
});

describe("people to invite (item 1.22)", () => {
  it("counts who would be invited first, then sends the invitations", async () => {
    const server = fakeServer({
      "GET /reference/campuses/": { body: [{ id: 1, code: "MRP", name: "Mon Repos Campus" }] },
      "GET /auth/accounts/uninvited/?campus_code=MRP&term_code=2026-27-S1": { body: { count: 12, without_email: 2 } },
      "POST /auth/accounts/invite/": { body: { invited: 12, emailed: 11, in_use: 0 } },
    });
    render(<Accounts />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "See who would be invited" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Name a campus, a term, or both.");
    await user.selectOptions(screen.getByLabelText("Campus"), await screen.findByRole("option", { name: "Mon Repos Campus" }));
    await user.type(screen.getByLabelText("Term code"), "2026-27-S1");
    await user.click(screen.getByRole("button", { name: "See who would be invited" }));
    expect(await screen.findByText(/12 people/)).toBeInTheDocument();
    expect(screen.getByText(/2 records have no email address/)).toBeInTheDocument();
    expect(server.calls.some((c) => c.method === "POST")).toBe(false); // the count sends nothing
    await user.click(screen.getByRole("button", { name: "Send 12 invitations" }));
    expect(await screen.findByText("12 invitations sent for campus MRP, term 2026-27-S1. 1 could not be emailed: check the addresses.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ campus_code: "MRP", term_code: "2026-27-S1" });
  });
});

describe("integration runs (item 1.23)", () => {
  it("lists the runs with what was refused, narrowed by kind and to those with failures", async () => {
    const run = {
      id: 3,
      kind: "training_push",
      kind_name: "Training completions to the HRMS",
      trigger: "schedule",
      started_at: "2026-10-05T02:00:00Z",
      finished_at: "2026-10-05T02:01:00Z",
      ok: 4,
      failed: 2,
      errors: [{ ref: "lms:SD-101:E0999", code: "unknown_employee", detail: "The HRMS does not know E0999." }],
      stopped: "",
    };
    const server = fakeServer({
      "GET /integration-runs/": page([run, { ...run, id: 4, failed: 0, errors: [], finished_at: null, stopped: "The HRMS could not be reached." }]),
      "GET /integration-runs/?kind=marks_push&failed=true": page([]),
    });
    render(<IntegrationRuns />);
    const list = await screen.findByRole("list", { name: "Integration runs" });
    expect(within(list).getAllByRole("listitem")[0]).toHaveTextContent("4 sent, 2 refused");
    expect(within(list).getByRole("list", { name: "Refused in run 3" })).toHaveTextContent("lms:SD-101:E0999 unknown_employeeThe HRMS does not know E0999.");
    expect(list).toHaveTextContent("The first 1 row is listed.");
    expect(list).toHaveTextContent("Stopped: The HRMS could not be reached.");
    await userEvent.selectOptions(screen.getByLabelText("Kind"), "marks_push");
    await userEvent.click(screen.getByLabelText("Only runs with failures"));
    expect(await screen.findByText("No runs match.")).toBeInTheDocument();
    expect(server.calls.at(-1)?.path).toBe("/integration-runs/?kind=marks_push&failed=true");
  });
});

describe("the access review (item 1.21)", () => {
  const review = {
    last_review: null,
    role_holders: [{ username: "ayesha.ramdin", name: "Ayesha Ramdin", role: "administrator", role_name: "Administrator", campus_code: "", given: "2026-09-01T10:00:00Z", last_sign_in: null, account_active: false }],
    teaching_staff: [{ site_code: "AGR101", site_title: "Crops", term_code: "2026-27-S1", employee_no: "E0901", name: "Marlon Bacchus", site_role: "Lecturer", person_active: false, last_sign_in: "2026-10-01T10:00:00Z" }],
  };

  it("lists who holds a role and who teaches, and signs it off with notes", async () => {
    const server = fakeServer({
      "GET /auth/access-review/": [
        { body: review },
        { body: { ...review, last_review: { id: 1, reviewed_by: "Ayesha Ramdin", reviewed_at: "2026-10-05T10:00:00Z", role_holders: 1, teaching_staff: 1, notes: "Removed a leaver." } } },
      ],
      "POST /auth/access-review/sign-off/": { status: 201, body: {} },
    });
    render(<AccessReview me={administrator} />);
    expect(await screen.findByText("The review has not been signed off yet.")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Role holders" })).toHaveTextContent("Account closed");
    expect(screen.getByRole("list", { name: "Role holders" })).toHaveTextContent("never signed in");
    expect(screen.getByRole("list", { name: "Teaching staff" })).toHaveTextContent("No longer on the staff");
    await userEvent.type(screen.getByLabelText("What was changed or queried"), "Removed a leaver.");
    await userEvent.click(screen.getByRole("button", { name: "Sign off the review" }));
    expect(await screen.findByRole("status")).toHaveTextContent("The review is signed off.");
    expect(await screen.findByText(/Signed off .* by Ayesha Ramdin: 1 role grants and 1 teaching places./)).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ notes: "Removed a leaver." });
  });

  it("lets the auditor read it without signing off, and says when it cannot be loaded", async () => {
    fakeServer({ "GET /auth/access-review/": [{ body: { ...review, teaching_staff: [] } }, { status: 403, body: { code: "permission_denied", detail: "You do not hold a role that permits this action." } }] });
    const { unmount } = render(<AccessReview me={auditor} />);
    expect(await screen.findByText("Nobody teaches a site yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign off the review" })).not.toBeInTheDocument();
    unmount();
    render(<AccessReview me={auditor} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("You do not hold a role");
  });
});
