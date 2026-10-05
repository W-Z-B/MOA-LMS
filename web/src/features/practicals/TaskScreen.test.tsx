import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import type { FrameworkTree } from "../../api/types-practicals";
import { fakeServer } from "../../test/fetch";
import { PracticalsTab } from "./PracticalsTab";
import { observation, page, students, task } from "./testData";

const framework: FrameworkTree = {
  id: 2,
  code: "AGR-CROP-L2",
  title: "Crop Production Level 2",
  source: "Council for TVET occupational standard",
  version: "2024.1",
  is_active: true,
  units: [
    {
      id: 21,
      code: "U1",
      title: "Prepare land for planting",
      elements: [{ id: 210, code: "E1.1", title: "Prepare beds", criteria: [{ id: 301, code: "PC1.1.1", text: "Beds are formed to the specified width" }] }],
    },
  ],
};

function open(hash: string, routes: Record<string, unknown> = {}) {
  window.location.hash = hash;
  const server = fakeServer({
    "GET /practical-tasks/": { body: page([task, { ...task, id: 6, title: "Vaccinate broilers", is_published: false, criteria: [], weight: "0.00", counts_in_coursework: false }]) },
    "GET /practical-tasks/5/": { body: task },
    "GET /practical-tasks/5/students/": { body: students },
    "GET /practical-assessors/": { body: page([{ id: 1, site: 9, person: 50, person_name: "Mark Bovell", employee_no: "E0100", note: "Farm manager", is_active: true }]) },
    "GET /site-frameworks/": { body: page([{ id: 1, site: 9, framework: 2, framework_title: "AGR-CROP-L2 v2024.1" }]) },
    "GET /competency-frameworks/2/": { body: framework },
    ...(routes as Record<string, { body?: unknown }>),
  });
  render(<PracticalsTab siteId={9} teaching />);
  return server;
}

afterEach(() => {
  window.location.hash = "";
});

describe("practical tasks for teaching staff (item 3.12)", () => {
  it("lists the tasks and creates one, then opens it for its criteria", async () => {
    const { calls } = open("#/sites/9/practicals", { "POST /practical-tasks/": { status: 201, body: { ...task, id: 8 } } });
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: /Prepare a vegetable bed/ })).toBeInTheDocument();
    expect(screen.getByText(/does not count in coursework/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark Prepare a vegetable bed in the field" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark Vaccinate broilers in the field" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tasks" })).toHaveAttribute("aria-current", "page");

    await user.click(screen.getByRole("button", { name: "New practical task" }));
    await user.type(screen.getByLabelText("Title"), "Measure pond oxygen");
    await user.selectOptions(screen.getByLabelText("Where it is done"), "pond");
    await user.type(screen.getByLabelText("Location"), "Pond 2");
    await user.clear(screen.getByLabelText(/Weight in coursework/));
    await user.type(screen.getByLabelText(/Weight in coursework/), "1");
    await user.type(screen.getByLabelText("Closes"), "2026-10-20T16:00");
    await user.click(screen.getByRole("button", { name: "Create task" }));
    const sent = calls.find((c) => c.method === "POST")!;
    expect(sent.body).toMatchObject({ site: 9, title: "Measure pond oxygen", unit_type: "pond", location: "Pond 2", weight: "1", opens_at: null });
    expect((sent.body as { closes_at: string }).closes_at).toMatch(/^2026-10-20T/);
    expect(window.location.hash).toBe("#/sites/9/practicals/8");
  });

  it("names a field assessor found by search, and removes one", async () => {
    const { calls } = open("#/sites/9/practicals", {
      "GET /search/": { body: { sites: [], content: [], assignments: [], quizzes: [], people: [{ id: 51, title: "Ann Rampersaud", sub: "E0101 · Staff", link: "" }, { id: 31, title: "Kezia Persaud", sub: "S2026901 · Student", link: "" }] } },
      "POST /practical-assessors/": { status: 201, body: {} },
      "DELETE /practical-assessors/1/": { status: 204 },
    });
    const user = userEvent.setup();
    expect(await screen.findByText(/Mark Bovell \(E0100\) · Farm manager/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Find a member of staff"), "ann");
    await user.type(screen.getByLabelText(/Their role here/), "Poultry unit");
    await user.click(screen.getByRole("button", { name: "Find" }));
    expect(screen.queryByText(/Kezia Persaud/)).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Name Ann Rampersaud as an assessor" }));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ site: 9, person: 51, note: "Poultry unit" });
    await user.click(screen.getByRole("button", { name: "Remove Mark Bovell" }));
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/practical-assessors/1/")).toBe(true);
  });

  it("adds a scored criterion and maps one to a performance criterion", async () => {
    const { calls } = open("#/sites/9/practicals/5", {
      "POST /practical-criteria/": { status: 201, body: {} },
      "PATCH /practical-criteria/11/": { body: {} },
    });
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: "Prepare a vegetable bed" })).toBeInTheDocument();
    expect(screen.getByText("Scored 0 to 5, 3 to pass")).toBeInTheDocument();

    await user.type(screen.getByLabelText("What the assessor looks for"), "Rows straight");
    await user.selectOptions(screen.getByLabelText("How it is marked"), "scored");
    await user.clear(screen.getByLabelText("Highest score"));
    await user.type(screen.getByLabelText("Highest score"), "4");
    await user.click(screen.getByLabelText(/Critical: it must be met/));
    await user.click(screen.getByRole("button", { name: "Add criterion" }));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      task: 5,
      position: 3,
      text: "Rows straight",
      kind: "scored",
      is_critical: true,
      max_score: 4,
      pass_score: 3,
    });

    await user.click(await screen.findByRole("button", { name: 'Map "Bed formed to 1.2 m" to performance criteria' }));
    await user.click(screen.getByLabelText(/PC1.1.1 Beds are formed/));
    await user.click(screen.getByRole("button", { name: "Save mapping" }));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ performance_criteria: [301] });
  });

  it("shows the class list with attempts, opens a student's attempts, and releases one or all", async () => {
    const { calls } = open("#/sites/9/practicals/5", {
      "GET /observations/": { body: page([{ ...observation, student: 32, student_name: "Tevin Joseph", is_released: false }]) },
      "POST /observations/70/release/": { body: observation },
      "POST /practical-tasks/5/release/": { body: { released: 1 } },
      "PATCH /practical-tasks/5/": { body: { ...task, is_published: false } },
    });
    const user = userEvent.setup();
    const tevin = (await screen.findByText("Tevin Joseph")).closest("li")!;
    expect(tevin).toHaveTextContent("1 of 2 attempts · latest 3 of 6, critical not met · not released");
    await user.click(within(tevin).getByRole("button", { name: "Attempts of Tevin Joseph" }));
    expect(await screen.findByText("Not yet released to the student.", { exact: false })).toBeInTheDocument();

    await user.click(within(tevin).getByRole("button", { name: "Release to Tevin Joseph" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Released to Tevin Joseph.");
    await user.click(screen.getByRole("button", { name: "Release all (1)" }));
    expect(calls.some((c) => c.method === "POST" && c.path === "/practical-tasks/5/release/")).toBe(true);
    await user.click(screen.getByRole("button", { name: "Unpublish" }));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ is_published: false });

    await user.click(within(screen.getByText("Kezia Persaud").closest("li")!).getByRole("button", { name: "Observe Kezia Persaud" }));
    expect(window.location.hash).toBe("#/sites/9/practicals/5/observe/31");
  });

  it("says when the task cannot be opened", async () => {
    open("#/sites/9/practicals/5", { "GET /practical-tasks/5/": { status: 404, body: { code: "not_found", detail: "Not found." } } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});
