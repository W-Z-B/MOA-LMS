import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../../test/fetch";
import { ContentTab } from "./ContentTab";
import { asSite, contents, item, module } from "./fixtures";

vi.mock("./maths", () => ({ drawMaths: () => Promise.resolve() }));

const weekOne = module(1, "Week 1: Soils", [
  item(11, 1, "Soil texture"),
  item(12, 1, "Soil pH", { is_published: false }),
  item(13, 1, "Field guide", { kind: "link", url: "https://agriculture.gov.gy/guide", source: "Ministry of Agriculture" }),
]);
const weekTwo = module(2, "Week 2: Water", [item(21, 2, "Irrigation")], { conditions: "Shown from 12/01/2027 09:00." });

function teach(routes: Record<string, unknown> = {}) {
  const server = fakeServer({
    "GET /groups/": { body: { count: 1, next: null, previous: null, results: [{ id: 5, site: 9, name: "Group A", members: [] }] } },
    ...(routes as Record<string, { body?: unknown }>),
  });
  const onChanged = vi.fn();
  const view = render(<ContentTab data={asSite(contents([weekOne, weekTwo]))} teaching onChanged={onChanged} />);
  return { ...server, onChanged, view };
}

const sent = (calls: { method: string; path: string; body: unknown }[], method: string, path: string) =>
  calls.find((c) => c.method === method && c.path === path)?.body;

describe("the Content tab for teaching staff (items 2.15 and 2.16)", () => {
  it("lists modules and items with drafts marked and the conditions in the server's words", () => {
    teach();
    expect(screen.getByRole("heading", { name: "Week 1: Soils", level: 2 })).toBeInTheDocument();
    const items = screen.getByRole("list", { name: "Items in Week 1: Soils" });
    expect(within(items).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["Soil texture", "Soil pH", "Field guide"]);
    expect(within(items).getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("Shown from 12/01/2027 09:00.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Soil texture" })).toHaveAttribute("href", "#/sites/9/pages/11");
    expect(screen.getByText("Source: Ministry of Agriculture")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Course setup/ })).toHaveAttribute("href", "#/sites/9/setup");
  });

  it("moves an item down with the keyboard, sending the whole new order, and says where it went", async () => {
    const { calls, onChanged, view } = teach({ "POST /modules/1/reorder-items/": { body: { order: [12, 11, 13] } } });
    await userEvent.click(screen.getByRole("button", { name: "Change “Soil texture”" }));
    expect(screen.getByRole("button", { name: "Move “Soil texture” up" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Move “Soil texture” down" }));
    expect(sent(calls, "POST", "/modules/1/reorder-items/")).toEqual({ order: [12, 11, 13] });
    expect(await screen.findByRole("status")).toHaveTextContent("Moved “Soil texture” to place 2 of 3 in Week 1: Soils.");
    expect(onChanged).toHaveBeenCalled();
    // The list comes back in its new order and focus returns to the button that was used.
    const moved = module(1, "Week 1: Soils", [weekOne.items[1], weekOne.items[0], weekOne.items[2]]);
    view.rerender(<ContentTab data={asSite(contents([moved, weekTwo]))} teaching onChanged={onChanged} />);
    expect(screen.getByRole("button", { name: "Move “Soil texture” down" })).toHaveFocus();
  });

  it("moves an item up, and sends focus to the other button when it reaches the top", async () => {
    const { calls, onChanged, view } = teach({ "POST /modules/1/reorder-items/": { body: {} } });
    await userEvent.click(screen.getByRole("button", { name: "Change “Soil pH”" }));
    await userEvent.click(screen.getByRole("button", { name: "Move “Soil pH” up" }));
    expect(sent(calls, "POST", "/modules/1/reorder-items/")).toEqual({ order: [12, 11, 13] });
    const moved = module(1, "Week 1: Soils", [weekOne.items[1], weekOne.items[0], weekOne.items[2]]);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    view.rerender(<ContentTab data={asSite(contents([moved, weekTwo]))} teaching onChanged={onChanged} />);
    expect(screen.getByRole("button", { name: "Move “Soil pH” down" })).toHaveFocus();
  });

  it("reorders modules", async () => {
    const { calls } = teach({ "POST /sites/9/reorder-modules/": { body: {} } });
    expect(screen.getByRole("button", { name: "Move the module “Week 1: Soils” up" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Move the module “Week 2: Water” up" }));
    expect(sent(calls, "POST", "/sites/9/reorder-modules/")).toEqual({ order: [2, 1] });
    expect(await screen.findByRole("status")).toHaveTextContent("place 1 of 2");
  });

  it("drags an item within a module and onto another module", async () => {
    const { calls } = teach({ "POST /modules/1/reorder-items/": { body: {} }, "POST /content/11/move/": { body: {} } });
    const rows = within(screen.getByRole("list", { name: "Items in Week 1: Soils" })).getAllByRole("listitem");
    fireEvent.dragStart(rows[0]);
    fireEvent.dragOver(rows[2]);
    fireEvent.drop(rows[2]);
    await waitFor(() => expect(sent(calls, "POST", "/modules/1/reorder-items/")).toEqual({ order: [12, 11, 13] }));

    const other = within(screen.getByRole("list", { name: "Items in Week 2: Water" })).getAllByRole("listitem");
    fireEvent.dragStart(rows[0]);
    fireEvent.drop(other[0]);
    await waitFor(() => expect(sent(calls, "POST", "/content/11/move/")).toEqual({ module: 2, position: 1 }));
  });

  it("moves an item to another module, duplicates it and publishes a draft", async () => {
    const { calls } = teach({
      "POST /content/11/move/": { body: {} },
      "POST /content/11/duplicate/": { status: 201, body: {} },
      "PATCH /content/12/": { body: {} },
    });
    await userEvent.click(screen.getByRole("button", { name: "Change “Soil texture”" }));
    const tools = screen.getByRole("group", { name: "Change “Soil texture”" });
    expect(within(tools).getByRole("button", { name: "Move" })).toBeDisabled();
    await userEvent.selectOptions(within(tools).getByLabelText("Move to module"), "Week 2: Water");
    await userEvent.click(within(tools).getByRole("button", { name: "Move" }));
    expect(sent(calls, "POST", "/content/11/move/")).toEqual({ module: 2 });
    await userEvent.click(within(tools).getByRole("button", { name: "Duplicate" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Copied “Soil texture” as a draft below it.");
    expect(within(tools).getByRole("link", { name: "Edit page" })).toHaveAttribute("href", "#/sites/9/pages/11/edit");

    await userEvent.click(screen.getByRole("button", { name: "Change “Soil pH”" }));
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    expect(sent(calls, "PATCH", "/content/12/")).toEqual({ is_published: true });
  });

  it("shows why a change was refused", async () => {
    teach({ "PATCH /content/12/": { status: 400, body: { is_published: ["This item was withdrawn after a takedown request."] } } });
    await userEvent.click(screen.getByRole("button", { name: "Change “Soil pH”" }));
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("withdrawn after a takedown request");
  });

  it("sets release conditions and shows the server's sentence for them", async () => {
    const { calls } = teach({
      "PATCH /content/21/": { body: { conditions: "Once “Soil texture” is complete; to Group A only." } },
    });
    await userEvent.click(screen.getByRole("button", { name: "Change “Irrigation”" }));
    const tools = screen.getByRole("group", { name: "Change “Irrigation”" });
    await userEvent.click(within(tools).getByRole("button", { name: "When students see it" }));
    const form = screen.getByRole("form", { name: "When students see “Irrigation”" });
    await userEvent.selectOptions(within(form).getByLabelText("Only once this item is complete"), "Soil texture");
    await userEvent.click(within(form).getByLabelText("Group A"));
    await userEvent.type(within(form).getByLabelText(/Shown from/), "2027-01-12T09:00");
    await userEvent.click(within(form).getByRole("button", { name: "Save conditions" }));
    const body = sent(calls, "PATCH", "/content/21/") as Record<string, unknown>;
    expect(body.requires_item).toBe(11);
    expect(body.groups).toEqual([5]);
    expect(new Date(body.available_from as string).getTime()).toBe(new Date("2027-01-12T09:00").getTime());
    expect(await within(form).findByRole("status")).toHaveTextContent("Saved. Once “Soil texture” is complete; to Group A only.");
    await userEvent.click(within(form).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("form", { name: "When students see “Irrigation”" })).not.toBeInTheDocument();
  });

  it("sets a module's conditions without offering its own items, and clears them", async () => {
    const { calls } = teach({ "PATCH /modules/1/": { body: { conditions: null } }, "PATCH /modules/1/x": { body: {} } });
    const head = screen.getByRole("heading", { name: "Week 1: Soils" }).parentElement!;
    await userEvent.click(within(head).getByRole("button", { name: "When students see it" }));
    const form = screen.getByRole("form", { name: "When students see “Week 1: Soils”" });
    const after = within(form).getByLabelText("Only once this item is complete");
    expect(within(after).queryByRole("option", { name: "Soil texture" })).not.toBeInTheDocument();
    expect(within(after).getByRole("option", { name: "Irrigation" })).toBeInTheDocument();
    await userEvent.click(within(form).getByRole("button", { name: "Save conditions" }));
    expect(sent(calls, "PATCH", "/modules/1/")).toEqual({ available_from: null, requires_item: null, groups: [] });
    expect(await within(form).findByRole("status")).toHaveTextContent("No conditions: every student sees it once it is published.");
  });

  it("adds a module, a link with whose material it is, and offers a new page in the editor", async () => {
    const { calls, onChanged } = teach({
      "POST /modules/": { status: 201, body: {} },
      "POST /content/": { status: 201, body: item(30, 2, "Rain gauge", { kind: "link" }) },
    });
    await userEvent.type(screen.getByLabelText("New module"), "Week 3: Pests");
    await userEvent.click(screen.getByRole("button", { name: "Add module" }));
    expect(sent(calls, "POST", "/modules/")).toEqual({ site: 9, title: "Week 3: Pests" });

    const second = screen.getByRole("heading", { name: "Week 2: Water" }).closest("section")!;
    expect(within(second).getByRole("link", { name: "Add a page" })).toHaveAttribute("href", "#/sites/9/pages/new?module=2");
    await userEvent.click(within(second).getByRole("button", { name: "Add a link" }));
    await userEvent.type(within(second).getByLabelText("Title"), "Rain gauge");
    await userEvent.type(within(second).getByLabelText("Web address"), "https://example.org/rain");
    await userEvent.selectOptions(within(second).getByLabelText("Whose material is this?"), "Under an open licence");
    await userEvent.selectOptions(within(second).getByLabelText("Which open licence"), "CC BY");
    await userEvent.type(within(second).getByLabelText("Source and credit"), "Hydromet Service");
    await userEvent.click(within(second).getByRole("button", { name: "Add link" }));
    expect(sent(calls, "POST", "/content/")).toEqual({
      title: "Rain gauge",
      licence: "open_licence",
      open_licence: "cc_by",
      source: "Hydromet Service",
      module: 2,
      kind: "link",
      url: "https://example.org/rain",
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Added “Rain gauge”.");
    expect(onChanged).toHaveBeenCalledTimes(2);
  });

  it("uploads a file and warns when the course's storage is nearly full", async () => {
    const { calls } = teach({
      "POST /content/": {
        status: 201,
        body: item(31, 1, "Soil map", { kind: "file", storage: { used_bytes: 1, allowance_bytes: 1, percent: 85, warning: "This course has used 85% of its storage." } }),
      },
    });
    const first = screen.getByRole("heading", { name: "Week 1: Soils" }).closest("section")!;
    await userEvent.click(within(first).getByRole("button", { name: "Upload a file" }));
    await userEvent.type(within(first).getByLabelText("Title"), "Soil map");
    await userEvent.upload(within(first).getByLabelText(/^File/), new File(["%PDF"], "map.pdf", { type: "application/pdf" }));
    await userEvent.selectOptions(within(first).getByLabelText("Whose material is this?"), "GSA's own material");
    expect(within(first).queryByLabelText("Source and credit")).not.toBeInTheDocument();
    // jsdom does not count a file set by a test towards a required field, so the form is sent directly.
    fireEvent.submit(within(first).getByRole("button", { name: "Upload file" }).closest("form")!);
    await waitFor(() => expect(sent(calls, "POST", "/content/")).toBeDefined());
    const form = sent(calls, "POST", "/content/") as FormData;
    expect(form.get("kind")).toBe("file");
    expect(form.get("licence")).toBe("gsa_own");
    expect((form.get("file") as File).name).toBe("map.pdf");
    expect(await screen.findByRole("status")).toHaveTextContent("This course has used 85% of its storage.");
  });

  it("edits a link's details, licence and source", async () => {
    const { calls } = teach({ "PATCH /content/13/": { body: item(13, 1, "Field guide 2", { kind: "link" }) } });
    await userEvent.click(screen.getByRole("button", { name: "Change “Field guide”" }));
    await userEvent.click(screen.getByRole("button", { name: "Edit details" }));
    const title = screen.getByDisplayValue("Field guide");
    await userEvent.clear(title);
    await userEvent.type(title, "Field guide 2");
    await userEvent.selectOptions(screen.getByLabelText("Whose material is this?"), "Used with the owner's permission");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(sent(calls, "PATCH", "/content/13/")).toEqual({
      title: "Field guide 2",
      licence: "permission_held",
      open_licence: "",
      source: "Ministry of Agriculture",
      url: "https://agriculture.gov.gy/guide",
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Saved “Field guide 2”.");
  });

  it("edits a file's details without sending the file again, and cancels", async () => {
    const file = item(14, 1, "Soil map", { kind: "file", filename: "map.pdf", download_url: "/api/v1/content/14/download/", licence: "gsa_own" });
    const { calls } = (() => {
      const server = fakeServer({ "GET /groups/": { body: { results: [] } }, "PATCH /content/14/": { body: file } });
      render(<ContentTab data={asSite(contents([module(1, "Week 1: Soils", [file])]))} teaching onChanged={vi.fn()} />);
      return server;
    })();
    expect(screen.getByRole("link", { name: "Download map.pdf" })).toHaveAttribute("href", "/api/v1/content/14/download/");
    await userEvent.click(screen.getByRole("button", { name: "Change “Soil map”" }));
    expect(screen.queryByLabelText("Move to module")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Edit details" }));
    expect(screen.getByLabelText("Replace the file (now map.pdf)")).not.toBeRequired();
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(sent(calls, "PATCH", "/content/14/")).toEqual({ title: "Soil map", licence: "gsa_own", open_licence: "", source: "" });
    await userEvent.click(screen.getByRole("button", { name: "Edit details" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });
});

describe("the Content tab for students (item 2.16)", () => {
  const read = module(1, "Week 1: Soils", [item(11, 1, "Soil texture", { completed: true }), item(12, 1, "Soil pH")]);

  it("shows progress through each module and marks an item complete", async () => {
    const { calls } = fakeServer({ "POST /content/12/complete/": { body: {} } });
    const onChanged = vi.fn();
    render(<ContentTab data={asSite(contents([read], "student"))} teaching={false} onChanged={onChanged} />);
    expect(screen.getByText("1 of 2 complete")).toBeInTheDocument();
    expect(screen.getByText("Complete")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Change/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Course setup/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole("listitem")[0]).not.toHaveAttribute("draggable", "true");
    await userEvent.click(screen.getByRole("button", { name: "Mark “Soil pH” complete" }));
    expect(calls.some((c) => c.method === "POST" && c.path === "/content/12/complete/")).toBe(true);
    expect(onChanged).toHaveBeenCalled();
  });

  it("records no progress for an auditor reading the course", () => {
    fakeServer({});
    const auditing = contents([read], "student");
    render(<ContentTab data={asSite({ ...auditing, site: { ...auditing.site, my_role: "auditor" } })} teaching={false} onChanged={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Soil pH" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /complete/ })).not.toBeInTheDocument();
    expect(screen.queryByText("1 of 2 complete")).not.toBeInTheDocument();
  });

  it("says when there is no content", () => {
    fakeServer({});
    render(<ContentTab data={asSite(contents([], "student"))} teaching={false} onChanged={vi.fn()} />);
    expect(screen.getByText("No content yet.")).toBeInTheDocument();
  });
});

// --- packaged content (items 5.12 to 5.14, 6.08) ---
describe("packages and the library in the Content tab", () => {
  const withPackage = module(1, "Week 1: Soils", [item(14, 1, "Soil testing", { kind: "package", download_url: "/api/v1/content/14/download/" })]);

  it("links a package to its player, and teaching staff to its settings, the library and the import screen", async () => {
    fakeServer({ "GET /groups/": { body: { count: 0, next: null, previous: null, results: [] } } });
    render(<ContentTab data={asSite(contents([withPackage]))} teaching onChanged={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Soil testing" })).toHaveAttribute("href", "#/sites/9/packages/14");
    expect(screen.getByRole("link", { name: "Import or export content" })).toHaveAttribute("href", "#/sites/9/transfer");
    expect(screen.getByRole("link", { name: "From the library" })).toHaveAttribute("href", "#/library");
    await userEvent.click(screen.getByRole("button", { name: "Change “Soil testing”" }));
    expect(screen.getByRole("link", { name: "Package settings and results" })).toHaveAttribute("href", "#/sites/9/packages/14");
    expect(screen.getByRole("link", { name: "Share to the library" })).toHaveAttribute("href", "#/library/share?item=14");
    await userEvent.click(screen.getByRole("button", { name: "Add a SCORM or H5P package" }));
    expect(await screen.findByRole("form", { name: "Add a SCORM or H5P package" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  });

  it("does not let a student mark a package complete: finishing it does", () => {
    render(<ContentTab data={asSite(contents([withPackage], "student"))} teaching={false} onChanged={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Mark “Soil testing” complete" })).not.toBeInTheDocument();
  });
});
// --- end packaged content ---
