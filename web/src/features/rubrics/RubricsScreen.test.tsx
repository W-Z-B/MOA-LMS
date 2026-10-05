import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Rubric } from "../../api/types-marking";
import { FrameContext } from "../../app/frame";
import { fakeServer } from "../../test/fetch";
import { page, rubric } from "../../test/marking";
import { RubricsScreen } from "./RubricsScreen";

const library: Rubric = { ...rubric, id: 40, site: null, title: "GSA practical report rubric" };

function show(siteId: number | null, routes: Record<string, unknown> = {}) {
  const server = fakeServer({
    "GET /rubrics/?site=9": page([rubric]),
    "GET /rubrics/?library=1": page([library]),
    ...(routes as Record<string, { body?: unknown }>),
  });
  const setCrumb = vi.fn();
  render(
    <FrameContext.Provider value={{ setCrumb, decided: vi.fn() }}>
      <RubricsScreen siteId={siteId} />
    </FrameContext.Provider>,
  );
  return { ...server, setCrumb };
}

describe("rubrics and marking guides (items 3.09, 3.10)", () => {
  it("lists the course's rubrics, and copies one from the GSA library to the course", async () => {
    const { calls, setCrumb } = show(9, { "POST /rubrics/40/copy/": { status: 201, body: { ...library, id: 41, site: 9 } } });
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: "Rubrics and marking guides", level: 1 })).toBeInTheDocument();
    await vi.waitFor(() => expect(setCrumb).toHaveBeenCalledWith("Rubrics and marking guides"));
    expect(screen.getByText("Rubric: Soil profile report rubric")).toBeInTheDocument();
    const shelf = await screen.findByRole("region", { name: "The GSA library" });
    await user.click(within(shelf).getByRole("button", { name: "Copy GSA practical report rubric to this course" }));
    expect(await screen.findByText("Copied “GSA practical report rubric” to this course.")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/rubrics/40/copy/")!.body).toEqual({ site: 9 });
  });

  it("writes a new scored rubric with criteria and levels", async () => {
    const { calls } = show(9, { "POST /rubrics/": { status: 201, body: rubric } });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "New rubric" }));
    const form = screen.getByRole("form", { name: "New rubric" });
    await user.type(within(form).getByLabelText("Title"), "Field notebook");
    await user.type(within(form).getByLabelText("Criterion 1 title"), "Completeness");
    await user.type(within(form).getByLabelText("Level 1 of criterion 1"), "Gaps");
    await user.type(within(form).getByLabelText("Level 2 of criterion 1"), "Most days");
    await user.type(within(form).getByLabelText("Level 3 of criterion 1"), "Every day");
    await user.click(within(form).getByRole("button", { name: "Remove level 2 of criterion 1" }));
    await user.click(within(form).getByRole("button", { name: "Add a criterion" }));
    await user.type(within(form).getByLabelText("Criterion 2 title"), "Neatness");
    await user.click(within(form).getByRole("button", { name: "Remove criterion 2" }));
    await user.click(within(form).getByRole("button", { name: "Save the rubric" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/rubrics/")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toEqual({
      site: 9,
      title: "Field notebook",
      description: "",
      kind: "scored",
      criteria: [
        {
          title: "Completeness",
          description: "",
          max_points: null,
          levels: [
            { points: "0", description: "Gaps" },
            { points: "10", description: "Every day" },
          ],
        },
      ],
    });
  });

  it("turns a rubric into a marking guide with a maximum for each criterion, when changing it", async () => {
    const { calls } = show(9, { "PATCH /rubrics/4/": { body: rubric } });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Change" }));
    const form = screen.getByRole("form", { name: "Change Soil profile report rubric" });
    await user.selectOptions(within(form).getByLabelText("Kind"), "guide");
    await user.clear(within(form).getByLabelText("Maximum points for criterion 1"));
    await user.type(within(form).getByLabelText("Maximum points for criterion 1"), "12");
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    const body = calls.find((c) => c.method === "PATCH")!.body as { kind: string; criteria: { max_points: string; levels: unknown[] }[]; site?: number };
    expect(body.kind).toBe("guide");
    expect(body.site).toBeUndefined();
    expect(body.criteria[0]).toMatchObject({ max_points: "12", levels: [] });
  });

  it("keeps a rubric that marks were given with: no change, no deletion; the library for course administrators", async () => {
    fakeServer({ "GET /rubrics/?library=1": page([{ ...library, in_use: true }]) });
    render(<RubricsScreen siteId={null} />);
    expect(await screen.findByRole("heading", { name: "GSA rubric library", level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/Marks were given with it/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Copy" })).not.toBeInTheDocument();
  });

  it("deletes a rubric after asking, and says why one could not go", async () => {
    show(9, { "DELETE /rubrics/4/": { status: 403, body: { code: "forbidden", detail: "An assignment still uses it." } } });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("An assignment still uses it.");
  });
});
