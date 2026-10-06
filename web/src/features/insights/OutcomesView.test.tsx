import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeServer } from "../../test/fetch";
import { evidence, localOutcomes, srmsOutcomes, standings, studentProgress } from "../../test/insights";
import { MyProgress } from "./MyProgress";
import { OutcomesView } from "./OutcomesView";

function open(outcomes = srmsOutcomes, routes: Parameters<typeof fakeServer>[0] = {}) {
  const server = fakeServer({
    "GET /sites/9/outcomes/": { body: outcomes },
    "GET /sites/9/outcome-standings/": { body: standings },
    "GET /sites/9/outcome-evidence/": { body: evidence },
    ...routes,
  });
  render(<OutcomesView siteId={9} />);
  return server;
}

describe("learning outcomes (item 3.11)", () => {
  it("shows the SRMS outcomes with their evidence and each student's standing, without a form to add one", async () => {
    open();
    expect(await screen.findByText(/come from the SRMS course outline for AGR205/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Evidence for LO1" })).toHaveTextContent("Soil profile report");
    expect(screen.getByText("No evidence linked yet.")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Add an outcome" })).not.toBeInTheDocument();
    const table = await screen.findByRole("region", { name: "Standing of each student" });
    const [, ria, andre] = within(table).getAllByRole("row");
    expect(ria).toHaveTextContent("S2026911 Ria RamdialMet (70%)No evidence yet");
    expect(within(andre).getByText("Not yet met (30%)")).toHaveClass("standing-not-yet");
    expect(screen.getByText(/Met at 50% or more of the evidence/)).toBeInTheDocument();
  });

  it("links evidence to an outcome and unlinks it", async () => {
    const { calls } = open(srmsOutcomes, {
      "POST /sites/9/outcomes/32/links/": { status: 201, body: {} },
      "DELETE /outcome-links/61/": { status: 204 },
    });
    const user = userEvent.setup();
    const pick = await screen.findByRole("combobox", { name: "Evidence to link to LO2" });
    await user.selectOptions(pick, "criterion:11");
    await user.click(within(pick.closest("form")!).getByRole("button", { name: "Link" }));
    await waitFor(() => expect(calls.find((c) => c.path === "/sites/9/outcomes/32/links/")?.body).toEqual({ criterion: 11 }));
    await user.click(screen.getByRole("button", { name: "Unlink Soil profile report from LO1" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/outcome-links/61/")).toBe(true));
  });

  it("adds and removes the course's own outcomes while the SRMS has none, and says why one is refused", async () => {
    const { calls } = open(localOutcomes, {
      "POST /sites/9/outcomes/": [{ status: 400, body: { code: ["The site already has an outcome with this code."] } }, { status: 201, body: localOutcomes }],
      "DELETE /outcomes/40/": { status: 204 },
    });
    expect(await screen.findByText(/not linked to an SRMS course outline/)).toBeInTheDocument();
    expect(screen.getByText("This course's own")).toBeInTheDocument();
    const user = userEvent.setup();
    const form = screen.getByRole("form", { name: "Add an outcome" });
    await user.type(within(form).getByRole("textbox", { name: "Code" }), "L1");
    await user.type(within(form).getByRole("textbox", { name: "What the student can do" }), "Name three soils");
    await user.click(within(form).getByRole("button", { name: "Add outcome" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("code: The site already has an outcome with this code.");
    await user.click(within(form).getByRole("button", { name: "Add outcome" }));
    await waitFor(() => expect(calls.filter((c) => c.path === "/sites/9/outcomes/" && c.method === "POST")).toHaveLength(2));
    await user.click(screen.getByRole("button", { name: "Remove outcome" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/outcomes/40/")).toBe(true));
  });

  it("says when a link is refused", async () => {
    open(srmsOutcomes, { "POST /sites/9/outcomes/31/links/": { status: 409, body: { code: "already_linked", detail: "This is already linked to the outcome." } } });
    const user = userEvent.setup();
    const pick = await screen.findByRole("combobox", { name: "Evidence to link to LO1" });
    await user.selectOptions(pick, "assignment:5");
    await user.click(within(pick.closest("form")!).getByRole("button", { name: "Link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This is already linked to the outcome.");
  });
});

describe("my progress (item 6.02)", () => {
  it("shows a student their items, work, marks so far and outcomes, and no alert", async () => {
    fakeServer({ "GET /sites/9/my-progress/": { body: studentProgress } });
    render(<MyProgress siteId={9} />);
    expect(await screen.findByText("Coursework so far")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Items done" })).toHaveAttribute("value", "75");
    expect(screen.getByRole("list", { name: "Your work" })).toHaveTextContent("Take a corePracticalNot yet due");
    expect(screen.getByText("Marks count here once your lecturer releases them.")).toBeInTheDocument();
    expect(screen.queryByText(/alert/i)).not.toBeInTheDocument();
  });

  it("says when progress cannot be loaded", async () => {
    fakeServer({ "GET /sites/9/my-progress/": { status: 403, body: { code: "permission_denied", detail: "My progress is for the site's students." } } });
    render(<MyProgress siteId={9} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("My progress is for the site's students.");
  });
});
