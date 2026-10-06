import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CertificateTemplate, RequiredTraining as Rule } from "../../api/types-staff";
import { fakeServer } from "../../test/fetch";
import { auditor, course, courseAdmin, page, staff, student } from "../../test/staff";
import { LearningScreen } from "./LearningScreen";
import { learningAddress } from "./address";
import { RequiredTraining } from "./RequiredTraining";
import { Templates } from "./Templates";

const rule = (over: Partial<Rule> = {}): Rule => ({
  id: 1,
  site: 41,
  site_title: "Safe use of farm machinery",
  campus_code: "MRP",
  unit_code: "",
  post_title: "Farm Supervisor",
  applies_to: "Farm Supervisor, Mon Repos",
  due_days: 30,
  renewal_months: 24,
  is_active: true,
  notes: "",
  assigned: 4,
  source: "lms",
  editable: true,
  ...over,
});

const template = (over: Partial<CertificateTemplate> = {}): CertificateTemplate => ({
  id: 1,
  code: "completion",
  version: 2,
  name: "Certificate of completion",
  heading: "Certificate of Completion",
  body: "This is to certify that {{full_name}} completed {{course}}.",
  signatory_name: "",
  signatory_title: "Principal",
  is_active: true,
  fields_used: ["full_name", "course"],
  created_at: "2026-10-01T10:00:00Z",
  ...over,
});

describe("required training (item 5.05)", () => {
  it("lists what is required of whom, assigns it now, requires a new course, and reports who is overdue", async () => {
    const server = fakeServer({
      "GET /staff-development/required/": [page([rule(), rule({ id: 2, is_active: false, renewal_months: null })]), page([rule({ assigned: 5 })])],
      "GET /staff-development/required/overdue/": page([
        { id: 1, site: 41, site_title: "Safe use of farm machinery", person: 22, person_name: "Joy Lall", employee_no: "E0201", campus_code: "MRP", assigned_on: "2026-08-01", due_on: "2026-09-01", completed_on: null, state: "overdue" },
      ]),
      "GET /staff-development/required/overdue/?campus_code=ESQ": page([]),
      "GET /staff-development/catalogue/": page([course()]),
      "POST /staff-development/required/1/assign/": [{ body: { assigned: 1 } }, { body: { assigned: 0 } }],
      "POST /staff-development/required/": { status: 201, body: rule({ applies_to: "everyone on the staff", assigned: 12 }) },
    });
    render(<RequiredTraining me={courseAdmin} />);
    const list = await screen.findByRole("list", { name: "Requirements" });
    expect(within(list).getAllByRole("listitem")[0]).toHaveTextContent("For Farm Supervisor, Mon Repos · within 30 days · again every 24 months · 4 assigned");
    expect(within(list).getAllByRole("listitem")[1]).toHaveTextContent("Not in force");
    expect(within(list).getAllByRole("button", { name: /^Assign now/ })).toHaveLength(1);
    await userEvent.click(within(list).getByRole("button", { name: "Assign now: Safe use of farm machinery" }));
    expect(await screen.findByText("Safe use of farm machinery: assigned to 1 more.")).toBeInTheDocument();
    await userEvent.click(within(await screen.findByRole("list", { name: "Requirements" })).getByRole("button", { name: /^Assign now/ }));
    expect(await screen.findByText("Everyone it covers has it already.")).toBeInTheDocument();

    const overdue = await screen.findByRole("list", { name: "Overdue required training" });
    expect(overdue).toHaveTextContent("Joy Lall E0201Due 01/09/2026Safe use of farm machinery · MRP");
    await userEvent.type(screen.getByLabelText("Campus code"), "esq");
    expect(await screen.findByText("Nobody is overdue.")).toBeInTheDocument();

    await screen.findByRole("option", { name: "Safe use of farm machinery" });
    await userEvent.selectOptions(screen.getByLabelText("Course"), "41");
    await userEvent.type(screen.getByLabelText("Taken again every (months; empty: once)"), "12");
    await userEvent.click(screen.getByRole("button", { name: "Require it" }));
    expect(await screen.findByText("Safe use of farm machinery is required of everyone on the staff: 12 assigned.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "POST" && c.path === "/staff-development/required/")?.body).toEqual({
      site: 41,
      campus_code: "",
      unit_code: "",
      post_title: "",
      due_days: 30,
      renewal_months: 12,
      notes: "",
    });
  });

  it("shows who keeps each requirement, and changes only those kept in the LMS (decision D13)", async () => {
    const server = fakeServer({
      "GET /staff-development/required/": [
        page([rule(), rule({ id: 2, site_title: "First aid", source: "hrms", editable: false })]),
        page([rule({ is_active: false }), rule({ id: 2, site_title: "First aid", source: "hrms", editable: false })]),
      ],
      "GET /staff-development/required/overdue/": page([]),
      "GET /staff-development/catalogue/": page([course()]),
      "PATCH /staff-development/required/1/": { body: rule({ is_active: false }) },
    });
    render(<RequiredTraining me={courseAdmin} />);
    const list = await screen.findByRole("list", { name: "Requirements" });
    const [ours, theirs] = within(list).getAllByRole("listitem");
    expect(ours).toHaveTextContent("Kept in the LMS");
    expect(theirs).toHaveTextContent("From the HRMS");
    expect(theirs).toHaveTextContent("Kept in the HRMS: change it there.");
    expect(within(theirs).queryByRole("button", { name: /^Stop requiring/ })).not.toBeInTheDocument();
    expect(within(theirs).getByRole("button", { name: "Assign now: First aid" })).toBeInTheDocument();
    await userEvent.click(within(ours).getByRole("button", { name: "Stop requiring: Safe use of farm machinery" }));
    expect(await screen.findByText("Safe use of farm machinery: no longer required.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({ is_active: false });
    const again = await screen.findByRole("list", { name: "Requirements" });
    expect(within(again).getByRole("button", { name: "Require again: Safe use of farm machinery" })).toBeInTheDocument();
  });

  it("lets the auditor read it, without changing anything", async () => {
    fakeServer({
      "GET /staff-development/required/": page([]),
      "GET /staff-development/required/overdue/": page([]),
    });
    render(<RequiredTraining me={auditor} />);
    expect(await screen.findByText("Nothing is required yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Require it" })).not.toBeInTheDocument();
  });
});

describe("certificate templates (item 5.08)", () => {
  it("saves a change as the next version, and a new template", async () => {
    const server = fakeServer({
      "GET /certificate-templates/": page([template()]),
      "GET /certificate-templates/?versions=all": page([template(), template({ id: 0, version: 1, is_active: false, fields_used: [] })]),
      "POST /certificate-templates/1/new-version/": [
        { status: 400, body: { body: ["Unknown field: nickname."] } },
        { status: 201, body: template({ id: 2, version: 3 }) },
      ],
      "POST /certificate-templates/": { status: 201, body: template({ id: 5, code: "farm-safety", name: "Farm safety" }) },
    });
    render(<Templates me={courseAdmin} />);
    const list = await screen.findByRole("list", { name: "Templates" });
    expect(list).toHaveTextContent("Certificate of completion completion, version 2");
    expect(list).toHaveTextContent("uses full_name, course");
    await userEvent.click(within(list).getByRole("button", { name: "Change: Certificate of completion" }));
    expect(within(list).getByLabelText("Wording")).toHaveAccessibleDescription(/double braces/);
    await userEvent.click(within(list).getByRole("button", { name: "Save as a new version" }));
    expect(await within(list).findByRole("alert")).toHaveTextContent("body: Unknown field: nickname.");
    await userEvent.click(within(list).getByRole("button", { name: "Save as a new version" }));
    expect(await screen.findByText("Certificate of completion is saved as version 3.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.path.endsWith("/new-version/"))?.body).toMatchObject({ name: "Certificate of completion", is_active: true });

    await userEvent.click(screen.getByRole("button", { name: "New template" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: "New template" }));
    await userEvent.type(screen.getByLabelText("Code (letters, numbers and dashes)"), "farm-safety");
    await userEvent.type(screen.getByLabelText("Name"), "Farm safety");
    await userEvent.type(screen.getByLabelText("Wording"), "Completed.");
    await userEvent.click(screen.getByRole("button", { name: "Save the template" }));
    expect(await screen.findByText("Farm safety is saved.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "POST" && c.path === "/certificate-templates/")?.body).toMatchObject({ code: "farm-safety", name: "Farm safety" });

    await userEvent.click(screen.getByLabelText("Show every version"));
    expect(await screen.findByText("Not in use")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Change/ })).not.toBeInTheDocument();
  });

  it("lets the auditor read the templates only", async () => {
    fakeServer({ "GET /certificate-templates/": page([template()]) });
    render(<Templates me={auditor} />);
    expect(await screen.findByRole("list", { name: "Templates" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("the staff-development screen", () => {
  afterEach(() => vi.restoreAllMocks());

  it("reads its addresses, including the server's own links", () => {
    expect(learningAddress("/learning")).toEqual({ tab: "catalogue", id: null });
    expect(learningAddress("/staff-development")).toEqual({ tab: "catalogue", id: null });
    expect(learningAddress("/staff-development/41")).toEqual({ tab: "course", id: 41 });
    expect(learningAddress("/learning/41?x=1")).toEqual({ tab: "course", id: 41 });
    expect(learningAddress("/staff-development/requests/5")).toEqual({ tab: "approvals", id: 5 });
    expect(learningAddress("/staff-development/requests")).toEqual({ tab: "approvals", id: null });
    expect(learningAddress("/certificates")).toEqual({ tab: "certificates", id: null });
    expect(learningAddress("/learning/paths/3")).toEqual({ tab: "paths", id: 3 });
    expect(learningAddress("/learning/paths")).toEqual({ tab: "paths", id: null });
    expect(learningAddress("/learning/templates")).toEqual({ tab: "templates", id: null });
    expect(learningAddress("/learning/nonsense")).toBeNull();
    expect(learningAddress("/sites/4")).toBeNull();
  });

  it("gives members of staff their tabs, course administrators theirs too, and students nothing", async () => {
    fakeServer({ "GET /staff-development/catalogue/": page([course()]), "GET /certificates/": page([]) });
    const go = vi.fn();
    const { unmount } = render(<LearningScreen me={staff} path="/learning" onNavigate={go} />);
    const tabs = screen.getByRole("navigation", { name: "Staff development" });
    expect(within(tabs).getAllByRole("link").map((a) => a.textContent)).toEqual(["Catalogue", "My learning", "Learning paths", "Certificates", "Approvals"]);
    expect(within(tabs).getByRole("link", { name: "Catalogue" })).toHaveAttribute("aria-current", "page");
    await userEvent.click(within(tabs).getByRole("link", { name: "Certificates" }));
    expect(go).toHaveBeenCalledWith("/learning/certificates");
    unmount();

    const admin = render(<LearningScreen me={courseAdmin} path="/certificates" onNavigate={go} />);
    const theirs = screen.getByRole("navigation", { name: "Staff development" });
    expect(within(theirs).getByRole("link", { name: "Required training" })).toBeInTheDocument();
    expect(within(theirs).getByRole("link", { name: "Certificates" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByRole("heading", { name: "Certificates issued" })).toBeInTheDocument();
    admin.unmount();

    render(<LearningScreen me={student} path="/learning" onNavigate={go} />);
    expect(screen.getByText("Staff-development courses are for members of staff.")).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("opens each part from its address, and never a manager's part for a member of staff", async () => {
    fakeServer({
      "GET /staff-development/catalogue/": page([course()]),
      "GET /staff-development/catalogue/41/": { body: course() },
      "GET /staff-development/requests/?mine=1": page([]),
      "GET /staff-development/required/mine/": { body: [] },
      "GET /staff-development/paths/": page([]),
      "GET /staff-development/requests/?state=submitted": page([]),
      "GET /approvals/delegations/": page([]),
      "GET /staff-development/required/": page([]),
      "GET /staff-development/required/overdue/": page([]),
      "GET /certificate-templates/": page([]),
    });
    const cases: [typeof staff, string, string][] = [
      [staff, "/learning/41", "Safe use of farm machinery"],
      [staff, "/learning/mine", "My courses"],
      [staff, "/learning/paths", "Learning paths"],
      [staff, "/staff-development/requests/5", "Waiting for your decision"],
      [staff, "/learning/required", "Catalogue"],
      [courseAdmin, "/learning/required", "Overdue"],
      [courseAdmin, "/learning/templates", "Certificate templates"],
    ];
    for (const [who, path, heading] of cases) {
      const { unmount } = render(<LearningScreen me={who} path={path} onNavigate={vi.fn()} />);
      expect(await screen.findByRole("heading", { name: heading, level: 2 })).toBeInTheDocument();
      unmount();
    }
  });
});
