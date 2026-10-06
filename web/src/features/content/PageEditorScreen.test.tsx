import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FrameContext } from "../../app/frame";
import { fakeServer } from "../../test/fetch";
import { contents, item, module } from "./fixtures";
import PageEditorScreen, { CHECK_AFTER_MS } from "./PageEditorScreen";

// The editor itself is tested in RichEditor.test.tsx; here a plain text box stands in for it, so the test
// can write HTML directly and look at what the screen does with it.
vi.mock("./RichEditor", () => ({
  RichEditor: ({ initialHtml, onChange, pictures, label }: { initialHtml: string; onChange: (html: string) => void; pictures: { title: string }[]; label: string }) => (
    <>
      <textarea aria-label={label} defaultValue={initialHtml} onChange={(e) => onChange(e.target.value)} />
      <p>Pictures: {pictures.map((p) => p.title).join(", ") || "none"}</p>
    </>
  ),
}));

const photo = item(31, 1, "Maize seedlings", { kind: "file", filename: "seedlings.jpg", download_url: "/api/v1/content/31/download/" });
const pdf = item(32, 1, "Soil map", { kind: "file", filename: "map.pdf", download_url: "/api/v1/content/32/download/" });
const course = contents([module(1, "Week 1: Soils", [photo, pdf]), module(2, "Week 2: Water", [])]);
const skipped = { code: "heading_skipped", detail: "A level 3 heading follows a level 1 heading.", severity: "warning" };

afterEach(() => vi.useRealTimers());

function open(itemId: number | null, routes: Record<string, unknown>, moduleId: number | null = 2) {
  const server = fakeServer({ "GET /sites/9/contents/": { body: course }, ...(routes as Record<string, { body?: unknown }>) });
  const onNavigate = vi.fn();
  const setCrumb = vi.fn();
  render(
    <FrameContext.Provider value={{ setCrumb, decided: vi.fn() }}>
      <PageEditorScreen siteId={9} itemId={itemId} moduleId={moduleId} onNavigate={onNavigate} />
    </FrameContext.Provider>,
  );
  return { ...server, onNavigate, setCrumb };
}

describe("writing a page (items 2.12 and 2.13)", () => {
  it("offers only the course's photographs as pictures, and the chosen module", async () => {
    open(null, {});
    expect(await screen.findByRole("heading", { name: "New page", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("Pictures: Maize seedlings")).toBeInTheDocument();
    expect(screen.getByLabelText("Module")).toHaveValue("2");
  });

  it("runs the accessibility check a moment after writing stops, and shows what it found", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { calls } = open(null, { "POST /content/check-page/": { body: { body: "<h3>Soil</h3>", issues: [skipped] } } });
    const box = await screen.findByRole("textbox", { name: "Page text" });
    await userEvent.type(box, "<h3>Soil</h3>");
    expect(calls.filter((c) => c.path === "/content/check-page/")).toHaveLength(0);
    await act(() => vi.advanceTimersByTimeAsync(CHECK_AFTER_MS));
    await waitFor(() => expect(screen.getByText(/A level 3 heading follows/)).toBeInTheDocument());
    // One check for the whole burst of typing, of the text as it stood at the end.
    const checks = calls.filter((c) => c.path === "/content/check-page/");
    expect(checks).toHaveLength(1);
    expect(checks[0].body).toEqual({ body: "<h3>Soil</h3>" });
    expect(screen.getByText("Check:")).toBeInTheDocument();
  });

  it("will not save while a picture has no alternative text", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const missing = { code: "missing_alt", detail: "Image 1 has no alternative text.", severity: "error" };
    open(null, { "POST /content/check-page/": { body: { body: "", issues: [missing] } } });
    await userEvent.type(await screen.findByLabelText("Title"), "Soils");
    await userEvent.type(screen.getByRole("textbox", { name: "Page text" }), "<img>");
    await act(() => vi.advanceTimersByTimeAsync(CHECK_AFTER_MS));
    expect(await screen.findByText("Must be fixed:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save as draft" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save and publish" })).toBeDisabled();
    expect(screen.getByText("Fix what must be fixed before saving.")).toBeInTheDocument();
  });

  it("publishes a new page, shows the warnings the save returned, and moves to the page's own address", async () => {
    const saved = item(40, 2, "Soils", { body: "<h3>Soil</h3>", accessibility_issues: [skipped as never] });
    const { calls, onNavigate } = open(null, { "POST /content/": { status: 201, body: saved } });
    await userEvent.type(await screen.findByLabelText("Title"), "Soils");
    await userEvent.type(screen.getByRole("textbox", { name: "Page text" }), "<h3>Soil</h3>");
    await userEvent.click(screen.getByRole("button", { name: "Save and publish" }));
    expect(calls.find((c) => c.method === "POST" && c.path === "/content/")?.body).toEqual({
      title: "Soils",
      body: "<h3>Soil</h3>",
      is_published: true,
      module: 2,
      kind: "page",
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Saved and published. The accessibility check found 1 thing to look at.");
    expect(screen.getByText(/A level 3 heading follows/)).toBeInTheDocument();
    expect(onNavigate).toHaveBeenCalledWith("/sites/9/pages/40/edit");
  });

  it("changes a saved page, unpublishes it, and shows a refusal", async () => {
    const page = item(40, 1, "Soils", { body: "<p>Old</p>" });
    const { calls, setCrumb } = open(40, {
      "GET /content/40/": { body: page },
      "PATCH /content/40/": [
        { body: { ...page, body: "<p>New</p>", accessibility_issues: [] } },
        { body: { ...page, is_published: false, accessibility_issues: [] } },
        { status: 400, body: { body: ["A picture on the page is not a file on this course."] } },
      ],
    });
    const box = await screen.findByRole("textbox", { name: "Page text" });
    expect(screen.getByRole("heading", { name: "Edit page", level: 1 })).toBeInTheDocument();
    await waitFor(() => expect(setCrumb).toHaveBeenCalledWith("Editing Soils"));
    expect(screen.queryByLabelText("Module")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See it as students do" })).toHaveAttribute("href", "#/sites/9/pages/40");
    await userEvent.clear(box);
    await userEvent.type(box, "<p>New</p>");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ title: "Soils", body: "<p>New</p>" });
    expect(await screen.findByRole("status")).toHaveTextContent("Saved and published.");
    await userEvent.click(screen.getByRole("button", { name: "Unpublish" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved as a draft: students do not see it yet.");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("body: A picture on the page is not a file on this course.");
  });

  it("checks what is already on a page when it opens", async () => {
    const page = item(40, 1, "Soils", { body: "<h4>Deep</h4>" });
    const { calls } = open(40, { "GET /content/40/": { body: page }, "POST /content/check-page/": { body: { body: "", issues: [skipped] } } });
    expect(await screen.findByText(/A level 3 heading follows/, undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/content/check-page/")?.body).toEqual({ body: "<h4>Deep</h4>" });
  });

  it("starts in the first module when none is named", async () => {
    open(null, {}, null);
    await waitFor(() => expect(screen.getByLabelText("Module")).toHaveValue("1"));
  });

  it("says when the page cannot be opened", async () => {
    open(77, { "GET /content/77/": { status: 404, body: { code: "not_found", detail: "Not found." } } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});
