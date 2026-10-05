import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../../test/fetch";
import { page } from "../../test/marking";
import { AccommodationsScreen } from "./AccommodationsScreen";

const held = { id: 3, person: 101, student_no: "S2026911", extra_time_percent: 25, extra_days: 2, other_format: "Large print", reason: "Eyesight", is_active: true };

describe("accommodations kept by course administrators (item 3.23)", () => {
  it("lists what is held, with the reason for course administrators only", async () => {
    fakeServer({ "GET /accommodations/": page([held]) });
    render(<AccommodationsScreen />);
    const row = await screen.findByRole("region", { name: "Accommodation for S2026911" });
    expect(row).toHaveTextContent("25% more time in quizzes · 2 more days for every assignment · Large print");
    expect(row).toHaveTextContent("Reason (course administrators only): Eyesight");
  });

  it("finds a student and adds an accommodation", async () => {
    const { calls } = fakeServer({
      "GET /accommodations/": [page([]), page([held])],
      "GET /search/": { body: { sites: [], content: [], assignments: [], quizzes: [], people: [{ id: 101, title: "Ria Ramdial", sub: "S2026911 · Student", link: "" }, { id: 7, title: "Ria Staff", sub: "E1 · Staff", link: "" }] } },
      "POST /accommodations/": { status: 201, body: held },
    });
    render(<AccommodationsScreen />);
    const user = userEvent.setup();
    expect(await screen.findByText("No accommodations are held.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add an accommodation" }));
    const form = screen.getByRole("form", { name: "New accommodation" });
    await user.click(within(form).getByRole("button", { name: "Save" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("Choose the student first.");
    await user.type(within(form).getByLabelText("Student (name or student number)"), "Ria");
    const found = await within(form).findByRole("list", { name: "Students found" });
    expect(within(found).getAllByRole("button")).toHaveLength(1); // staff are not offered
    await user.click(within(found).getByRole("button", { name: "Ria Ramdial · S2026911 · Student" }));
    await user.clear(within(form).getByLabelText("More days for each assignment"));
    await user.type(within(form).getByLabelText("More days for each assignment"), "2");
    await user.type(within(form).getByLabelText(/^Reason/), "Eyesight");
    await user.click(within(form).getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("region", { name: "Accommodation for S2026911" })).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({ extra_time_percent: 0, extra_days: 2, other_format: "", reason: "Eyesight", is_active: true, person: 101 });
  });

  it("changes and removes one", async () => {
    const { calls } = fakeServer({
      "GET /accommodations/": page([held]),
      "PATCH /accommodations/3/": { body: held },
      "DELETE /accommodations/3/": { status: 204 },
    });
    render(<AccommodationsScreen />);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Change" }));
    const form = screen.getByRole("form", { name: "Change the accommodation for S2026911" });
    await user.click(within(form).getByRole("checkbox", { name: "In force" }));
    await user.click(within(form).getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toMatchObject({ is_active: false });
    await user.click(await screen.findByRole("button", { name: "Remove" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("says when they cannot be read", async () => {
    fakeServer({ "GET /accommodations/": { status: 403, body: { code: "forbidden", detail: "Course administrators only." } } });
    render(<AccommodationsScreen />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Course administrators only.");
  });
});
