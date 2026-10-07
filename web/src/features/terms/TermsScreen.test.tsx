import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Term } from "../../api/types-terms";
import { FrameContext } from "../../app/frame";
import { fakeServer } from "../../test/fetch";
import TermsScreen from "./TermsScreen";

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });
const sent = (calls: { method: string; path: string; body: unknown }[], method: string, path: string) =>
  calls.filter((c) => c.method === method && c.path === path).at(-1)?.body;

const term = (over: Partial<Term> = {}): Term => ({
  id: 1,
  code: "2026-27-S1",
  name: "Semester 1",
  starts_on: "2026-09-01",
  ends_on: "2026-12-11",
  closes_on: "2026-12-23",
  grace_days: null,
  grace_days_applied: 2,
  source: "local",
  source_name: "Entered in the LMS",
  phase: "teaching",
  locks_at: "2026-12-26T00:00:00-04:00",
  archive_due_on: "2027-12-26",
  closed_at: null,
  archived_at: null,
  site_count: 3,
  ...over,
});

function shown() {
  const setCrumb = vi.fn();
  render(
    <FrameContext.Provider value={{ setCrumb, decided: vi.fn() }}>
      <TermsScreen />
    </FrameContext.Provider>,
  );
  return setCrumb;
}

describe("the term calendar (item 7.12)", () => {
  it("lists terms with their dates and phase, and a term's courses with their archives", async () => {
    fakeServer({
      "GET /terms/": { body: page([term(), term({ id: 2, code: "2025-26-S2", name: "Semester 2", phase: "closed", site_count: 1 })]) },
      "GET /terms/missing/": { body: [] },
      "GET /terms/2/sites/": {
        body: [
          { id: 9, code: "AGR101-2025-26-S2-MRP", title: "Crop Science", phase: "archived", archive: 4, archive_size: 3 * 1024 * 1024, archive_made_at: "2026-10-01T04:30:00Z" },
          { id: 10, code: "AGR102-2025-26-S2-MRP", title: "Soils", phase: "closed", archive: null, archive_size: null, archive_made_at: null },
        ],
      },
    });
    const setCrumb = shown();
    expect(setCrumb).toHaveBeenCalledWith("Terms");
    const first = (await screen.findByRole("heading", { name: /2026-27-S1 Semester 1/ })).closest("li")!;
    expect(within(first).getByText("Teaching")).toBeInTheDocument();
    expect(within(first).getByText(/Teaching 01\/09\/2026 to 11\/12\/2026 · last day for work 23\/12\/2026, then 2 days of grace/)).toBeInTheDocument();
    expect(within(first).getByText(/archived from 26\/12\/2027 · 3 courses/)).toBeInTheDocument();
    const second = screen.getByRole("heading", { name: /2025-26-S2/ }).closest("li")!;
    const toggle = within(second).getByRole("button", { name: "Show the courses of 2025-26-S2" });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(await within(second).findByRole("link", { name: "Crop Science" })).toHaveAttribute("href", "#/sites/9");
    expect(within(second).getByRole("link", { name: "Download the archive (3 MB)" })).toHaveAttribute("href", "/api/v1/site-archives/4/download/");
    expect(within(second).getByText(/AGR102-2025-26-S2-MRP · Closed, read-only/)).toBeInTheDocument();
    await userEvent.click(within(second).getByRole("button", { name: "Hide the courses of 2025-26-S2" }));
    expect(within(second).queryByRole("link", { name: "Crop Science" })).not.toBeInTheDocument();
  });

  it("adds a term for a code that courses use but the calendar lacks, and shows a refusal", async () => {
    const { calls } = fakeServer({
      "GET /terms/": [{ body: page([]) }, { body: page([term()]) }],
      "GET /terms/missing/": [{ body: [{ term_code: "2026-27-S1", sites: 3 }] }, { body: [] }],
      "POST /terms/": [{ status: 400, body: { closes_on: ["Sites cannot close before teaching ends."] } }, { status: 201, body: term() }],
    });
    shown();
    expect(await screen.findByText(/These term codes have courses but no dates/)).toBeInTheDocument();
    expect(screen.getByText("No terms yet. Add the current term so its courses close on time.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add 2026-27-S1" }));
    expect(screen.getByLabelText("Term code")).toHaveValue("2026-27-S1");
    await userEvent.type(screen.getByLabelText("Name"), "Semester 1");
    await userEvent.type(screen.getByLabelText("Teaching starts"), "2026-09-01");
    await userEvent.type(screen.getByLabelText("Teaching ends"), "2026-12-11");
    await userEvent.type(screen.getByLabelText("Last day for work"), "2026-12-01");
    await userEvent.click(screen.getByRole("button", { name: "Save the term" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("closes on: Sites cannot close before teaching ends.");
    await userEvent.clear(screen.getByLabelText("Last day for work"));
    await userEvent.type(screen.getByLabelText("Last day for work"), "2026-12-23");
    await userEvent.type(screen.getByLabelText(/Days of grace/), "3");
    await userEvent.click(screen.getByRole("button", { name: "Save the term" }));
    expect(sent(calls, "POST", "/terms/")).toEqual({
      code: "2026-27-S1",
      name: "Semester 1",
      starts_on: "2026-09-01",
      ends_on: "2026-12-11",
      closes_on: "2026-12-23",
      grace_days: 3,
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Saved the term 2026-27-S1.");
    expect(await screen.findByRole("heading", { name: /2026-27-S1 Semester 1/ })).toBeInTheDocument();
  });

  it("changes only the close and grace of a term from the SRMS, and removes a local term", async () => {
    const srms = term({ source: "srms", source_name: "From the SRMS", grace_days: 1 });
    const local = term({ id: 3, code: "2027-SUMMER", name: "Summer school", site_count: 0 });
    const { calls } = fakeServer({
      "GET /terms/": { body: page([srms, local]) },
      "GET /terms/missing/": { body: [] },
      "PATCH /terms/1/": { body: srms },
      "DELETE /terms/3/": { status: 204 },
    });
    shown();
    await userEvent.click(await screen.findByRole("button", { name: "Change the term 2026-27-S1" }));
    expect(screen.getByText(/its code, name and teaching dates are set there/)).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Remove the term" })).not.toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText(/Days of grace/));
    await userEvent.click(screen.getByRole("button", { name: "Save the term" }));
    expect(sent(calls, "PATCH", "/terms/1/")).toEqual({ closes_on: "2026-12-23", grace_days: null });
    await userEvent.click(await screen.findByRole("button", { name: "Change the term 2027-SUMMER" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove the term" }));
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/terms/3/")).toBe(true);
    expect(await screen.findByRole("status")).toHaveTextContent("Removed the term 2027-SUMMER.");
  });

  it("cancels a change, hides Change on an archived term, and says when the calendar cannot be read", async () => {
    fakeServer({
      "GET /terms/": [{ body: page([term({ phase: "archived", archived_at: "2027-12-26T04:30:00Z" })]) }],
      "GET /terms/missing/": { status: 500, body: { detail: "Down" } },
    });
    shown();
    await screen.findByText("Archived");
    expect(screen.queryByRole("button", { name: /Change the term/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add a term" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Add a term" })).toBeInTheDocument();

    fakeServer({ "GET /terms/": { status: 403, body: { code: "permission_denied", detail: "You do not hold a role that permits this action." } } });
    shown();
    expect(await screen.findByText("You do not hold a role that permits this action.")).toBeInTheDocument();
  });

  it("says when a term's courses cannot be read, or there are none", async () => {
    fakeServer({
      "GET /terms/": { body: page([term(), term({ id: 2, code: "2025-26-S2" })]) },
      "GET /terms/missing/": { body: [] },
      "GET /terms/1/sites/": { status: 500, body: { detail: "The server could not answer." } },
      "GET /terms/2/sites/": { body: [] },
    });
    shown();
    await userEvent.click(await screen.findByRole("button", { name: "Show the courses of 2026-27-S1" }));
    expect(await screen.findByText("The server could not answer.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show the courses of 2025-26-S2" }));
    expect(await screen.findByText("No course uses this term code.")).toBeInTheDocument();
  });
});
