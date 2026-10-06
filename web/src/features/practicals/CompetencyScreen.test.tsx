import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import type { CompetencySheet, Portfolio } from "../../api/types-practicals";
import { fakeServer } from "../../test/fetch";
import { PracticalsTab } from "./PracticalsTab";
import { observation, page, task } from "./testData";

const sheet: CompetencySheet = {
  site: "AGR101-2026-27-S1-MRP",
  units: [{ id: 21, code: "U1", title: "Prepare land for planting", framework: "AGR-CROP-L2 v2024.1" }],
  rows: [
    {
      person_id: 31,
      student_no: "S2026901",
      name: "Kezia Persaud",
      units: [
        {
          unit_id: 21,
          unit_code: "U1",
          unit_title: "Prepare land for planting",
          framework: "AGR-CROP-L2 v2024.1",
          suggested: "not_yet_competent",
          critical_criteria: [{ id: 11, task: "Prepare a vegetable bed", text: "Bed formed to 1.2 m" }],
          missing_critical: [{ id: 11, task: "Prepare a vegetable bed", text: "Bed formed to 1.2 m" }],
          observations: [77],
          assignments: [],
          result: null,
        },
      ],
    },
  ],
};

const me = (roles: string[]) => ({ id: 1, username: "x", name: "X", roles, is_superuser: false, mfa_required: true, mfa_verified: true, person_id: 1, person_kind: "staff", external_id: "E1" });

function open(hash: string, teaching: boolean, routes: Record<string, unknown> = {}) {
  window.location.hash = hash;
  const server = fakeServer({
    "GET /sites/9/competency/": { body: sheet },
    "GET /site-frameworks/": { body: page([{ id: 1, site: 9, framework: 2, framework_title: "AGR-CROP-L2 v2024.1 Crop Production Level 2" }]) },
    "GET /competency-frameworks/": { body: page([{ id: 2, code: "AGR-CROP-L2", title: "Crop", source: "", version: "2024.1", is_active: true, units: [] }, { id: 3, code: "AGR-LIVE-L2", title: "Livestock Level 2", source: "", version: "1", is_active: true, units: [] }]) },
    "GET /auth/me/": { body: me(["lecturer"]) },
    "GET /observations/": { body: page([observation]) },
    ...(routes as Record<string, { body?: unknown }>),
  });
  render(<PracticalsTab siteId={9} teaching={teaching} />);
  return server;
}

afterEach(() => {
  window.location.hash = "";
});

describe("competency for assessors (item 3.13)", { timeout: 15_000 }, () => {
  it("lists each student's units with the suggestion, and follows another framework", async () => {
    const { calls } = open("#/sites/9/practicals/competency", true, { "POST /site-frameworks/": { status: 201, body: {} } });
    const user = userEvent.setup();
    expect(await screen.findByText("AGR-CROP-L2 v2024.1 Crop Production Level 2")).toBeInTheDocument();
    expect(await screen.findByText("suggests not yet competent")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import a framework" })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Follow a framework"), "3");
    await user.click(screen.getByRole("button", { name: "Follow" }));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ site: 9, framework: 3 });
    await user.click(screen.getByRole("button", { name: "Record for Kezia Persaud" }));
    expect(window.location.hash).toBe("#/sites/9/practicals/competency/31");
  });

  it("records a result, and shows the server's reason when competent is refused", async () => {
    const { calls } = open("#/sites/9/practicals/competency/31", true, {
      "POST /competency-results/": [
        {
          status: 409,
          body: {
            code: "criteria_not_met",
            detail: "Not every critical criterion for U1 has been passed in a released observation. Still to pass: Prepare a vegetable bed: Bed formed to 1.2 m.",
          },
        },
        { status: 201, body: {} },
      ],
    });
    const user = userEvent.setup();
    const form = await screen.findByRole("form", { name: "U1 Prepare land for planting" });
    expect(within(form).getByText("Not yet competent", { selector: "strong" })).toBeInTheDocument();
    expect(within(form).getByText(/Still to pass:/)).toBeInTheDocument();
    expect(await within(form).findByLabelText(/Prepare a vegetable bed, attempt 1 \(5 of 6\)/)).toBeChecked();

    await user.click(within(form).getByLabelText("Competent"));
    await user.click(within(form).getByRole("button", { name: "Record U1" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("Still to pass: Prepare a vegetable bed: Bed formed to 1.2 m.");

    await user.click(within(form).getByLabelText("Not yet competent"));
    await user.type(within(form).getByLabelText("Comments"), "Bed too narrow; reassess next week.");
    await user.click(within(form).getByRole("button", { name: "Record U1" }));
    expect(await within(form).findByRole("status")).toHaveTextContent("Not yet competent recorded for U1.");
    const last = calls.filter((c) => c.method === "POST").at(-1)!;
    expect(last.body).toMatchObject({ site: 9, student: 31, unit: 21, status: "not_yet_competent", evidence_observations: [77] });
  });

  it("lets a course administrator import a framework from a CSV file", async () => {
    const { calls } = open("#/sites/9/practicals/competency", true, {
      "GET /auth/me/": { body: me(["course_admin"]) },
      "POST /competency-frameworks/import/": { status: 201, body: { id: 4, code: "AGR-AQUA-L2", title: "Aquaculture", source: "", version: "1", is_active: true, units: [] } },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Import a framework" }));
    await user.type(screen.getByLabelText("Code"), "AGR-AQUA-L2");
    await user.type(screen.getByLabelText("Title"), "Aquaculture");
    await user.upload(screen.getByLabelText("CSV file"), new File(["unit_code,unit_title"], "aqua.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Imported AGR-AQUA-L2 v1 Aquaculture.");
    const sent = calls.find((c) => c.method === "POST")!.body as FormData;
    expect(sent.get("code")).toBe("AGR-AQUA-L2");
    expect((sent.get("csv") as File).name).toBe("aqua.csv");
  });
});

describe("a student's practicals (items 3.12, 3.13 and 5.15)", { timeout: 15_000 }, () => {
  const studentSheet: CompetencySheet = {
    ...sheet,
    rows: [{ ...sheet.rows[0], units: [{ ...sheet.rows[0].units[0], suggested: undefined, result: { id: 1, status: "competent", assessor: "Marlon Bacchus", decided_on: "2026-10-05" } }] }],
  };

  it("shows released observations with criteria, comments and photos, and the competency result", async () => {
    open("#/sites/9/practicals", false, {
      "GET /practical-tasks/": { body: page([task]) },
      "GET /sites/9/competency/": { body: studentSheet },
    });
    expect(await screen.findByRole("heading", { name: "Prepare a vegetable bed: attempt 1" })).toBeInTheDocument();
    expect(screen.getByText("Every critical criterion met.")).toBeInTheDocument();
    expect(screen.getByText("Fine tilth")).toBeInTheDocument();
    expect(screen.getByText("Good, even bed.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "bed.jpg" })).toHaveAttribute("src", "/api/v1/observation-photos/3/download/");
    expect(await screen.findByText("Competent")).toBeInTheDocument();
    expect(screen.getByText("Marlon Bacchus, 05/10/2026")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Competency" })).not.toBeInTheDocument();
  });

  it("reads the portfolio and offers it to download as a page or as data", async () => {
    const portfolio: Portfolio = {
      student: { student_no: "S2026901", name: "Kezia Persaud" },
      generated_at: "2026-10-05T16:00:00Z",
      sites: [
        {
          site: { id: 9, code: "AGR101", title: "Introduction to Crop Production", term: "2026-27-S1" },
          logbook: [{ date: "2026-10-04", unit_type: "Fish pond", unit: "Pond 2", task: "Fed fingerlings", hours: "2.50", signed_by: "Marlon Bacchus", photos: [] }],
          logbook_hours: [{ unit_type: "pond", label: "Fish pond", signed_hours: "2.50", waiting_hours: "0.00" }],
          observations: [{ task: "Prepare a vegetable bed", attempt: 1, assessor: "Marlon Bacchus", observed_at: "2026-10-05T14:00:00Z", score: "5 of 6", critical_passed: true, comments: "", photos: [] }],
          competencies: [{ unit_code: "U1", unit_title: "Prepare land for planting", status: "Competent", assessor: "Marlon Bacchus", decided_on: "2026-10-05", framework: "AGR-CROP-L2" }],
        },
      ],
    };
    open("#/sites/9/practicals/portfolio", false, { "GET /portfolio/": { body: portfolio } });
    expect(await screen.findByText(/Fed fingerlings/)).toBeInTheDocument();
    expect(screen.getByText("Hours signed off: Fish pond 2.50")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download this course (page to print)" })).toHaveAttribute("href", "/api/v1/portfolio/?site=9&as=html");
    expect(screen.getByRole("link", { name: "Download as data (JSON)" })).toHaveAttribute("download", "practical-portfolio.json");
    expect(screen.getByRole("link", { name: "Portfolio" })).toHaveAttribute("aria-current", "page");
  });
});
