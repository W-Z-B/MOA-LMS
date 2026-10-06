import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Me } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { courseReport, rules, staffReport } from "../../test/insights";
import AlertRulesSection from "./AlertRulesSection";
import ReportsSection from "./ReportsSection";

const me = (roles: string[]): Me =>
  ({ id: 1, username: "reader", name: "Report Reader", roles, is_superuser: false, person_kind: "staff" }) as unknown as Me;

function open(roles: string[], routes: Parameters<typeof fakeServer>[0] = {}) {
  const server = fakeServer({
    "GET /reports/courses/": { body: courseReport },
    "GET /reports/staff-development/": { body: staffReport },
    ...routes,
  });
  render(<ReportsSection me={me(roles)} />);
  return server;
}

describe("reports that leave a course (items 6.03, 6.04, 6.06)", () => {
  it("shows the Registrar the courses by campus and programme, with small groups hidden", async () => {
    open(["registrar"]);
    const groups = await screen.findByRole("region", { name: "By campus and programme" });
    const [, esq, mrp] = within(groups).getAllByRole("row");
    expect(esq).toHaveTextContent("ESQDIP-AH10884.58");
    expect(mrp).toHaveTextContent("MRPProgramme not known11HiddenHiddenHiddenHidden");
    const sites = screen.getByRole("region", { name: "Each site" });
    expect(within(sites).getAllByRole("row")[1]).toHaveTextContent("8 (7 accepted, 1 not known)");
    expect(within(sites).getAllByRole("row")[2]).toHaveTextContent("AGR205 Soil Science · no content · not published");
    expect(screen.getByLabelText("Totals")).toHaveTextContent("2 sites1 with no content10 students");
    expect(screen.getByText(/Figures about fewer than 5 people are hidden/)).toBeInTheDocument();
    // Only one report for the Registrar: no choice of report.
    expect(screen.queryByRole("tab", { name: "Staff development" })).not.toBeInTheDocument();
  });

  it("filters the courses report and exports what is shown", async () => {
    const { calls } = open(["course_admin"]);
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByRole("combobox", { name: "Campus" }), "ESQ");
    await user.selectOptions(screen.getByRole("combobox", { name: "Programme" }), "DIP-AH");
    await waitFor(() => expect(calls.some((c) => c.path === "/reports/courses/?campus=ESQ&programme=DIP-AH")).toBe(true));
    expect(screen.getByRole("link", { name: "Export to a spreadsheet" })).toHaveAttribute(
      "href",
      "/api/v1/reports/courses/export/?campus=ESQ&programme=DIP-AH",
    );
  });

  it("gives a head of department both reports, and the staff development report by unit", async () => {
    const { calls } = open(["head_of_department"]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "Staff development" }));
    const units = await screen.findByRole("region", { name: "By unit" });
    const [, farm, library] = within(units).getAllByRole("row");
    expect(farm).toHaveTextContent("FARM622 of 61");
    expect(library).toHaveTextContent("LIBRARYHiddenHiddenHiddenHidden");
    expect(screen.getByRole("list", { name: "Completions by course" })).toHaveTextContent("Fire safety SD-FIREHidden");
    await user.type(screen.getByLabelText("Completed since"), "2026-09-01");
    await waitFor(() => expect(calls.some((c) => c.path === "/reports/staff-development/?since=2026-09-01")).toBe(true));
    expect(screen.getByRole("link", { name: "Export to a spreadsheet" })).toHaveAttribute(
      "href",
      "/api/v1/reports/staff-development/export/?since=2026-09-01",
    );
  });

  it("says when a report is refused", async () => {
    open(["auditor"], { "GET /reports/courses/": { status: 403, body: { code: "permission_denied", detail: "This report is for the roles it was made for." } } });
    expect(await screen.findByRole("alert")).toHaveTextContent("This report is for the roles it was made for.");
  });
});

describe("the early-alert rules for course administrators (item 6.05)", () => {
  it("changes a rule's threshold and window, and says when a value is refused", async () => {
    const { calls } = fakeServer({
      "GET /alert-rules/": { body: rules },
      "PATCH /alert-rules/1/": [{ status: 400, body: { threshold: ["Give a number from 1 to 365."] } }, { body: rules[0] }],
      "PATCH /alert-rules/3/": { body: rules[1] },
    });
    render(<AlertRulesSection />);
    const user = userEvent.setup();
    const thresholds = await screen.findAllByRole("spinbutton", { name: /Threshold/ });
    expect(screen.getAllByRole("spinbutton", { name: "Window (days)" })).toHaveLength(1); // not for no visits
    await user.clear(thresholds[0]);
    await user.type(thresholds[0], "3");
    await user.click(screen.getByRole("button", { name: "Save missed work" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("threshold: Give a number from 1 to 365.");
    await user.click(screen.getByRole("button", { name: "Save missed work" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved.");
    expect(calls.filter((c) => c.method === "PATCH")[1].body).toEqual({ threshold: 3, window_days: 28, is_active: true });
    await user.click(screen.getAllByRole("checkbox", { name: "Used" })[1]);
    await user.click(screen.getByRole("button", { name: "Save no visits" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/alert-rules/3/")?.body).toEqual({ threshold: 14, is_active: true }));
  });
});
