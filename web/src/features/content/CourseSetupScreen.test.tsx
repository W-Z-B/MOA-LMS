import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FrameContext } from "../../app/frame";
import { fakeServer } from "../../test/fetch";
import CourseSetupScreen from "./CourseSetupScreen";
import { toLocalInput } from "./dates";
import { contents, item, module } from "./fixtures";

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });
const earlier = { ...contents([]).site, id: 4, title: "Soils and Plant Nutrition (2025-26)", code: "AGR102-2025-26-S1-MRP" };
const studying = { ...contents([]).site, id: 5, title: "Something I study", code: "X", my_role: "student" };
const dates = [
  { kind: "assignment", id: 3, title: "Soil report", field: "opens_at", value: "2026-10-01T13:00:00Z" },
  { kind: "assignment", id: 3, title: "Soil report", field: "due_at", value: "2026-10-15T13:00:00Z" },
  { kind: "item", id: 11, title: "Soil texture", field: "available_from", value: null },
];
const storage = {
  used_bytes: 1.7 * 1024 ** 3,
  allowance_bytes: 2 * 1024 ** 3,
  percent: 85,
  warning: "This course has used 85% of its 2 GB storage allowance.",
  largest_files: [{ id: 31, title: "Field video", module: "Week 1", filename: "field.pdf", file_size: 300 * 1024 * 1024 }],
};

function open(empty: boolean, routes: Record<string, unknown> = {}, role: "lecturer" | "student" = "lecturer") {
  const course = contents(empty ? [] : [module(1, "Week 1: Soils", [item(11, 1, "Soil texture")])], role);
  const server = fakeServer({
    "GET /sites/9/contents/": { body: course },
    "GET /sites/": { body: page([course.site, earlier, studying]) },
    "GET /site-templates/": { body: page([{ id: 1, name: "GSA standard", description: "", structure: { modules: [] }, is_default: true }]) },
    "GET /sites/9/dates/": { body: dates },
    "GET /sites/9/storage/": { body: storage },
    ...(routes as Record<string, { body?: unknown }>),
  });
  const setCrumb = vi.fn();
  render(
    <FrameContext.Provider value={{ setCrumb, decided: vi.fn() }}>
      <CourseSetupScreen siteId={9} />
    </FrameContext.Provider>,
  );
  return { ...server, setCrumb };
}

const sent = (calls: { method: string; path: string; body: unknown }[], method: string, path: string) =>
  calls.find((c) => c.method === method && c.path === path)?.body;

describe("course setup for teaching staff (items 2.17, 2.18 and 2.20)", () => {
  it("offers the standard template to an empty course and applies it", async () => {
    const { calls, setCrumb } = open(true, { "POST /sites/9/apply-template/": { body: { modules: 15 } } });
    expect(await screen.findByRole("heading", { name: "Course setup", level: 1 })).toBeInTheDocument();
    await waitFor(() => expect(setCrumb).toHaveBeenCalledWith("Introduction to Crop Production: setup"));
    const section = screen.getByRole("region", { name: "Start from a template" });
    await waitFor(() => expect(within(section).getByLabelText("Template")).toHaveValue("1"));
    await userEvent.click(within(section).getByRole("button", { name: "Apply template" }));
    expect(sent(calls, "POST", "/sites/9/apply-template/")).toEqual({ template: 1 });
  });

  it("does not offer a template once the course has content", async () => {
    open(false);
    await screen.findByRole("heading", { name: "Course setup", level: 1 });
    expect(screen.queryByRole("region", { name: "Start from a template" })).not.toBeInTheDocument();
  });

  it("copies an earlier course to a new start date, replacing what is there, and reports what came across", async () => {
    const { calls } = open(false, {
      "POST /sites/9/copy-from/": {
        body: { modules: 2, items: 5, assignments: 1, offset_days: 364, missing_files: ["Old map"], left_out: ["Withdrawn notes"] },
      },
    });
    const section = await screen.findByRole("region", { name: "Copy from an earlier course" });
    const source = await within(section).findByLabelText("Course to copy from");
    // Only courses this person teaches, and never this one.
    expect(within(source).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose…", "Soils and Plant Nutrition (2025-26) (AGR102-2025-26-S1-MRP)"]);
    expect(within(section).getByText(/This course already has content/)).toBeInTheDocument();
    await userEvent.selectOptions(source, "4");
    await userEvent.type(within(section).getByLabelText("New start date"), "2027-01-11");
    await userEvent.click(within(section).getByLabelText(/Replace this course's/));
    await userEvent.click(within(section).getByRole("button", { name: "Copy the course" }));
    expect(sent(calls, "POST", "/sites/9/copy-from/")).toEqual({ source: 4, replace_existing: true, start_date: "2027-01-11" });
    const done = await within(section).findByRole("status");
    expect(done).toHaveTextContent("Copied 2 modules, 5 items and 1 assignment; every date moved by 364 days.");
    expect(done).toHaveTextContent("Left out (under review or withdrawn): Withdrawn notes.");
    expect(done).toHaveTextContent("not copied: Old map.");
  });

  it("copies by a number of days, and shows a refusal", async () => {
    const { calls } = open(true, {
      "POST /sites/9/copy-from/": { status: 409, body: { code: "copy_refused", detail: "Students have already worked through this course's content." } },
    });
    const section = await screen.findByRole("region", { name: "Copy from an earlier course" });
    await userEvent.selectOptions(await within(section).findByLabelText("Course to copy from"), "4");
    await userEvent.click(within(section).getByLabelText("By a number of days"));
    const days = within(section).getByLabelText(/Days to move every date/);
    await userEvent.clear(days);
    await userEvent.type(days, "-7");
    await userEvent.click(within(section).getByRole("button", { name: "Copy the course" }));
    expect(sent(calls, "POST", "/sites/9/copy-from/")).toEqual({ source: 4, replace_existing: false, offset_days: -7 });
    expect(await within(section).findByRole("alert")).toHaveTextContent("Students have already worked through");
  });

  it("lists every date, saves the changed ones together, and keeps them when the save is refused", async () => {
    const { calls } = open(false, {
      "PATCH /sites/9/dates/": [
        { status: 400, body: { code: "invalid_date", detail: "“Soil report” would open after it is due." } },
        { body: dates },
      ],
    });
    const section = await screen.findByRole("region", { name: "Dates" });
    const due = await within(section).findByLabelText("Due: Soil report");
    expect(due).toHaveValue(toLocalInput(dates[1].value));
    expect(within(section).getByRole("button", { name: "Save changes" })).toBeDisabled();
    await userEvent.clear(due);
    await userEvent.type(due, "2026-10-20T09:00");
    await userEvent.type(within(section).getByLabelText("Shown from: Soil texture"), "2026-10-05T08:00");
    await userEvent.click(within(section).getByRole("button", { name: "Save 2 changes" }));
    const body = sent(calls, "PATCH", "/sites/9/dates/") as { changes: { kind: string; id: number; field: string; value: string }[] };
    expect(body.changes.map((c) => [c.kind, c.id, c.field])).toEqual([
      ["assignment", 3, "due_at"],
      ["item", 11, "available_from"],
    ]);
    expect(new Date(body.changes[0].value).getTime()).toBe(new Date("2026-10-20T09:00").getTime());
    expect(await within(section).findByRole("alert")).toHaveTextContent("would open after it is due");
    // Nothing was changed: the edits are still there to correct.
    expect(within(section).getByLabelText("Due: Soil report")).toHaveValue("2026-10-20T09:00");
    await userEvent.click(within(section).getByRole("button", { name: "Save 2 changes" }));
    expect(await within(section).findByText("Saved 2 dates.")).toBeInTheDocument();
  });

  it("undoes unsaved changes, and moves every date by a number of days or to a new start", async () => {
    const { calls } = open(false, { "POST /sites/9/shift-dates/": { body: dates } });
    const section = await screen.findByRole("region", { name: "Dates" });
    const due = await within(section).findByLabelText("Due: Soil report");
    await userEvent.clear(due);
    await userEvent.type(due, "2026-10-20T09:00");
    await userEvent.click(within(section).getByRole("button", { name: "Undo changes" }));
    expect(due).toHaveValue(toLocalInput(dates[1].value));

    await userEvent.click(within(section).getByRole("button", { name: "Move every date" }));
    expect(sent(calls, "POST", "/sites/9/shift-dates/")).toEqual({ offset_days: 7 });
    expect(await within(section).findByText("Moved every date by 7 days.")).toBeInTheDocument();
    await userEvent.click(within(section).getByLabelText(/So the first date falls/));
    await userEvent.type(within(section).getByLabelText("New start date"), "2027-01-11");
    await userEvent.click(within(section).getByRole("button", { name: "Move every date" }));
    expect(calls.filter((c) => c.path === "/sites/9/shift-dates/").at(-1)?.body).toEqual({ start_date: "2027-01-11" });
  });

  it("shows storage use with its warning and the largest files", async () => {
    open(false);
    const section = await screen.findByRole("region", { name: "Storage" });
    expect(await within(section).findByText("1.7 GB used of 2 GB (85%).")).toBeInTheDocument();
    expect(within(section).getByText(/used 85% of its 2 GB/)).toBeInTheDocument();
    const table = within(section).getByRole("table");
    expect(within(table).getByText("Field video")).toBeInTheDocument();
    expect(within(table).getByText("300 MB")).toBeInTheDocument();
  });

  it("is for the course's teaching staff only", async () => {
    open(false, {}, "student");
    expect(await screen.findByRole("alert")).toHaveTextContent("Only the course's teaching staff set it up.");
  });

  it("says when the course has no dates and there is nothing to copy from", async () => {
    fakeServer({
      "GET /sites/9/contents/": { body: contents([]) },
      "GET /sites/": { body: page([contents([]).site]) },
      "GET /site-templates/": { body: page([]) },
      "GET /sites/9/dates/": { body: [] },
      "GET /sites/9/storage/": { body: { ...storage, warning: null, largest_files: [] } },
    });
    render(<CourseSetupScreen siteId={9} />);
    expect(await screen.findByText("Nothing on this course has a date yet.")).toBeInTheDocument();
    expect(await screen.findByText("You teach no other course to copy from.")).toBeInTheDocument();
    expect(await screen.findByText(/There is no course template yet/)).toBeInTheDocument();
  });
});
