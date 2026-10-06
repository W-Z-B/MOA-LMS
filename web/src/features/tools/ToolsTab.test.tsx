import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Module } from "../../api/types";
import type { SiteTools, Tool } from "../../api/types-connect";
import { fakeServer } from "../../test/fetch";
import { ToolsTab } from "./ToolsTab";

const modules: Module[] = [
  { id: 7, site: 9, title: "Week 1: Soils", position: 1, items: [] },
  { id: 8, site: 9, title: "Week 2: Water", position: 2, items: [] },
];

const tool = (over: Partial<Tool> = {}): Tool => ({
  id: 3,
  name: "Crop simulator",
  description: "",
  oidc_login_url: "https://sim.example/login",
  launch_url: "https://sim.example/launch",
  deep_linking_url: "https://sim.example/choose",
  share_name: false,
  share_email: false,
  grades: true,
  class_list: false,
  is_active: true,
  receives: ["An identifier for each person that means nothing outside this tool", "May post scores to the gradebook"],
  can_choose_content: true,
  ...over,
});

const placement = {
  id: 5,
  item: 41,
  module_id: 7,
  tool: 3,
  tool_name: "Crop simulator",
  title: "Maize growth",
  is_published: false,
  launch_url: "/api/lti/launch/41/",
};

const teachingData = (over: Partial<SiteTools> = {}): SiteTools => ({
  teaching: true,
  placements: [placement],
  line_items: [{ id: 2, label: "Maize growth", tool_name: "Crop simulator", placement: 5, score_maximum: "20.00", weight: "0.00", grade_category: null }],
  tools: [tool()],
  ...over,
});

const noCategories = { body: { count: 0, next: null, previous: null, results: [] } };

describe("a student's outside tools (item 6.07)", () => {
  it("lists the tools to open in a new window, and says what they learn", async () => {
    fakeServer({ "GET /sites/9/tools/": { body: { teaching: false, placements: [{ ...placement, is_published: true }], line_items: [], tools: [] } } });
    render(<ToolsTab siteId={9} teaching={false} modules={modules} />);
    const open = await screen.findByRole("link", { name: "Open Maize growth (opens in a new window)" });
    expect(open).toHaveAttribute("href", "/api/lti/launch/41/");
    expect(open).toHaveAttribute("target", "_blank");
    expect(screen.getByText(/a code that stands for you there/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Add a tool" })).not.toBeInTheDocument();
  });

  it("says when there is none, and when the list cannot be read", async () => {
    fakeServer({ "GET /sites/9/tools/": [{ body: { teaching: false, placements: [], line_items: [], tools: [] } }, { status: 500, body: { detail: "Down" } }] });
    const { unmount } = render(<ToolsTab siteId={9} teaching={false} modules={modules} />);
    expect(await screen.findByText("No outside tools on this course yet.")).toBeInTheDocument();
    unmount();
    render(<ToolsTab siteId={9} teaching={false} modules={modules} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Down");
  });
});

describe("teaching staff place tools (item 6.07)", () => {
  it("adds a tool with a gradebook column, showing what it receives, and offers content selection", async () => {
    const { calls } = fakeServer({
      "GET /sites/9/tools/": { body: teachingData() },
      "POST /tool-placements/": { status: 201, body: placement },
      "GET /grade-categories/": noCategories,
    });
    const user = userEvent.setup();
    render(<ToolsTab siteId={9} teaching modules={modules} />);
    expect(await screen.findByText(/Draft: publish it in Content · in Week 1: Soils/)).toBeInTheDocument();
    const receives = screen.getByText("What Crop simulator receives").closest("div")!;
    expect(receives).toHaveTextContent("An identifier for each person that means nothing outside this tool");
    await user.selectOptions(screen.getByLabelText("Module"), "8");
    expect(screen.getByRole("link", { name: "Choose content in Crop simulator (new window)" })).toHaveAttribute(
      "href",
      "/api/lti/choose/?tool=3&module=8",
    );
    await user.type(screen.getByLabelText("Title students see"), "Water budget");
    await user.click(screen.getByLabelText(/sends scores to a gradebook column/));
    await user.clear(screen.getByLabelText("Maximum score"));
    await user.type(screen.getByLabelText("Maximum score"), "25");
    await user.click(screen.getByRole("button", { name: "Add as a draft" }));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ module: 8, tool: 3, title: "Water budget", score_maximum: "25" });
    expect(await screen.findByRole("status")).toHaveTextContent("Added “Water budget” as a draft.");
  });

  it("removes a tool, sets how its column counts, and shows refusals", async () => {
    const { calls } = fakeServer({
      "GET /sites/9/tools/": { body: teachingData() },
      "DELETE /tool-placements/5/": { status: 204 },
      "PATCH /tool-line-items/2/": [{ body: {} }, { status: 400, body: { weight: ["Ensure this value is greater than or equal to 0."] } }],
      "GET /grade-categories/": {
        body: { count: 1, next: null, previous: null, results: [{ id: 4, site: 9, name: "Practical work", weight: "1", drop_lowest: 0, position: 1 }] },
      },
    });
    const user = userEvent.setup();
    render(<ToolsTab siteId={9} teaching modules={modules} />);
    const column = await screen.findByRole("form", { name: "How Maize growth counts" });
    await user.clear(within(column).getByLabelText("Weight"));
    await user.type(within(column).getByLabelText("Weight"), "2");
    await user.selectOptions(await within(column).findByLabelText("Category"), "4");
    await user.click(within(column).getByRole("button", { name: "Save" }));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ weight: "2", grade_category: 4 });
    expect(await screen.findByRole("status")).toHaveTextContent("Saved how “Maize growth” counts.");
    await user.click(within(column).getByRole("button", { name: "Save" }));
    expect(await within(column.closest("li")!).findByRole("alert")).toHaveTextContent("weight: Ensure this value");
    await user.click(screen.getByRole("button", { name: "Remove Maize growth" }));
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/tool-placements/5/")).toBe(true);
  });

  it("explains what to do first when nothing can be placed yet", async () => {
    fakeServer({ "GET /sites/9/tools/": [{ body: teachingData({ tools: [], line_items: [], placements: [] }) }, { body: teachingData({ line_items: [] }) }] });
    const { unmount } = render(<ToolsTab siteId={9} teaching modules={modules} />);
    expect(await screen.findByText(/No outside tools are registered yet/)).toBeInTheDocument();
    expect(screen.getByText("No tool sends scores to this course yet.")).toBeInTheDocument();
    unmount();
    render(<ToolsTab siteId={9} teaching modules={[]} />);
    expect(await screen.findByText(/Add a module in Content first/)).toBeInTheDocument();
  });

  it("refuses an addition the server will not take", async () => {
    fakeServer({
      "GET /sites/9/tools/": { body: teachingData({ tools: [tool({ grades: false, can_choose_content: false })] }) },
      "POST /tool-placements/": { status: 403, body: { code: "permission_denied", detail: "Only the site's teaching staff can do this." } },
      "GET /grade-categories/": noCategories,
    });
    const user = userEvent.setup();
    render(<ToolsTab siteId={9} teaching modules={modules} />);
    await user.click(await screen.findByRole("button", { name: "Add as a draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only the site's teaching staff can do this.");
    expect(screen.queryByRole("link", { name: /Choose content/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/sends scores/)).not.toBeInTheDocument();
  });
});
