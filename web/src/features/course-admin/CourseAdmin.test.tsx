import { render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FrameContext } from "../../app/frame";
import { fakeServer } from "../../test/fetch";
import { contents } from "../content/fixtures";
import AdminScreen from "./AdminScreen";
import { asHtml } from "./sections";
import StorageAllowancesScreen from "./StorageAllowancesScreen";
import TakedownsScreen from "./TakedownsScreen";
import TemplatesScreen from "./TemplatesScreen";

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });
const sent = (calls: { method: string; path: string; body: unknown }[], method: string, path: string) =>
  calls.filter((c) => c.method === method && c.path === path).at(-1)?.body;

function framed(node: ReactNode) {
  const decided = vi.fn();
  const setCrumb = vi.fn();
  render(<FrameContext.Provider value={{ setCrumb, decided }}>{node}</FrameContext.Provider>);
  return { decided, setCrumb };
}

describe("Admin (course administrators and administrators)", () => {
  it("lists only the parts that have screens, with the takedown requests waiting", async () => {
    fakeServer({ "GET /takedowns/": { body: { ...page([]), count: 2 } } });
    const onNavigate = vi.fn();
    render(<AdminScreen onNavigate={onNavigate} />);
    const nav = screen.getByRole("navigation", { name: "Admin" });
    expect(within(nav).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(["#/admin/templates", "#/admin/takedowns", "#/admin/storage"]);
    expect(await within(nav).findByText("Takedown requests (2 waiting)")).toBeInTheDocument();
    await userEvent.click(within(nav).getByRole("link", { name: /Course templates/ }));
    expect(onNavigate).toHaveBeenCalledWith("/admin/templates");
  });
});

describe("takedown requests (item 2.19)", () => {
  const open = { id: 1, item: 11, item_title: "Scanned textbook", site: 9, reason: "Copied without permission.", status: "open", created_at: "2026-10-01T13:00:00Z", reviewed_at: null, review_note: "" };
  const decidedRow = { ...open, id: 2, item_title: "Old notes", status: "restored", reviewed_at: "2026-10-02T13:00:00Z", review_note: "Our own." };

  it("withdraws a reported item with a note, and tells the frame a decision was made", async () => {
    const { calls } = fakeServer({ "GET /takedowns/": [{ body: page([open]) }, { body: page([]) }], "POST /takedowns/1/review/": { body: {} } });
    const { decided, setCrumb } = framed(<TakedownsScreen />);
    expect(setCrumb).toHaveBeenCalledWith("Takedown requests");
    const row = (await screen.findByRole("link", { name: "Scanned textbook" })).closest("li")!;
    expect(within(row).getByRole("link", { name: "Scanned textbook" })).toHaveAttribute("href", "#/sites/9");
    expect(within(row).getByText("Copied without permission.")).toBeInTheDocument();
    await userEvent.type(within(row).getByLabelText(/Note on the decision/), "No licence held.");
    await userEvent.click(within(row).getByRole("button", { name: "Withdraw the item" }));
    expect(sent(calls, "POST", "/takedowns/1/review/")).toEqual({ decision: "withdraw", note: "No licence held." });
    expect(await screen.findByRole("status")).toHaveTextContent("“Scanned textbook” is withdrawn.");
    expect(decided).toHaveBeenCalled();
    expect(await screen.findByText("Nothing is waiting for review.")).toBeInTheDocument();
  });

  it("restores an item, shows decided requests, and shows a refusal", async () => {
    const { calls } = fakeServer({
      "GET /takedowns/": [{ body: page([open]) }, { body: page([open, decidedRow]) }],
      "POST /takedowns/1/review/": { status: 409, body: { code: "already_decided", detail: "This request has been decided." } },
    });
    framed(<TakedownsScreen />);
    await userEvent.click(await screen.findByRole("button", { name: "Restore the item" }));
    expect(sent(calls, "POST", "/takedowns/1/review/")).toEqual({ decision: "restore", note: "" });
    expect(await screen.findByRole("alert")).toHaveTextContent("This request has been decided.");
    await userEvent.click(screen.getByRole("button", { name: "Decided" }));
    expect(await screen.findByRole("link", { name: "Old notes" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Scanned textbook" })).not.toBeInTheDocument();
    expect(screen.getByText(/Item restored/)).toBeInTheDocument();
    expect(screen.getByText("Note: Our own.")).toBeInTheDocument();
    expect(calls.at(-1)?.path).toBe("/takedowns/");
  });
});

describe("storage allowances (item 2.20)", () => {
  const site = { ...contents([]).site, storage_allowance_mb: null };
  const other = { ...site, id: 10, title: "Soils and Plant Nutrition", code: "AGR102-2026-27-S1-MRP" };

  it("shows each course's use, finds a course, and sets or clears its allowance", async () => {
    const { calls } = fakeServer({
      "GET /sites/": { body: page([site, other]) },
      "GET /sites/9/storage/": { body: { used_bytes: 1024 ** 3, allowance_bytes: 2 * 1024 ** 3, percent: 50, warning: null } },
      "GET /sites/10/storage/": { body: { used_bytes: 0, allowance_bytes: 2 * 1024 ** 3, percent: 0, warning: "Nearly full." } },
      "PATCH /sites/9/": [{ body: { ...site, storage_allowance_mb: 4096 } }, { status: 403, body: { code: "permission_denied", detail: "Only a course administrator can change a site's storage allowance." } }],
    });
    framed(<StorageAllowancesScreen />);
    expect(await screen.findByText(/1 GB used of 2 GB \(50%\)/)).toBeInTheDocument();
    expect(await screen.findByText("Nearly full.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Find a course"), "AGR101");
    expect(screen.queryByRole("heading", { name: "Soils and Plant Nutrition" })).not.toBeInTheDocument();
    const row = screen.getByRole("heading", { name: "Introduction to Crop Production" }).closest("li")!;
    await userEvent.type(within(row).getByLabelText(/Allowance in MB/), "4096");
    await userEvent.click(within(row).getByRole("button", { name: "Save allowance" }));
    expect(sent(calls, "PATCH", "/sites/9/")).toEqual({ storage_allowance_mb: 4096 });
    expect(await within(row).findByRole("status")).toHaveTextContent("Saved.");
    await userEvent.clear(within(row).getByLabelText(/Allowance in MB/));
    await userEvent.click(within(row).getByRole("button", { name: "Save allowance" }));
    expect(sent(calls, "PATCH", "/sites/9/")).toEqual({ storage_allowance_mb: null });
    expect(await within(row).findByRole("alert")).toHaveTextContent("Only a course administrator");
    await userEvent.clear(screen.getByLabelText("Find a course"));
    await userEvent.type(screen.getByLabelText("Find a course"), "nothing like it");
    expect(screen.getByText("No course matches.")).toBeInTheDocument();
  });

  it("lists twenty at a time", async () => {
    const many = Array.from({ length: 25 }, (_, i) => ({ ...site, id: 100 + i, title: `Course ${i}`, code: `C${i}` }));
    fakeServer({ "GET /sites/": { body: page(many) }, "GET /sites/100/storage/": { body: {} } });
    framed(<StorageAllowancesScreen />);
    expect(await screen.findByText("Showing 20 of 25. Type part of a title or code to find a course.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Save allowance" })).toHaveLength(20);
  });
});

describe("course templates (item 2.17)", () => {
  const standard = {
    id: 1,
    name: "GSA standard",
    description: "Every course",
    is_default: true,
    structure: { modules: [{ title: "Course overview", items: [{ kind: "page", title: "Welcome", body: "<p>Hello</p>" }] }, { title: "Week 1" }] },
  };

  it("makes a template with modules and pages, plain text becoming paragraphs", async () => {
    const { calls } = fakeServer({ "GET /site-templates/": [{ body: page([]) }, { body: page([standard]) }], "POST /site-templates/": { status: 201, body: standard } });
    framed(<TemplatesScreen />);
    expect(await screen.findByText("No templates yet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New template" }));
    await userEvent.type(screen.getByLabelText("Name"), "Short course");
    await userEvent.click(screen.getByLabelText(/The standard/));
    await userEvent.type(screen.getByLabelText("Module title"), "Introduction");
    await userEvent.click(screen.getByRole("button", { name: "Add a page" }));
    await userEvent.type(screen.getByLabelText("Page 1 title"), "Welcome");
    await userEvent.type(screen.getByLabelText("Page 1 starting text"), "Say hello.{enter}{enter}Then begin.");
    await userEvent.click(screen.getByRole("button", { name: "Add a module" }));
    await userEvent.type(screen.getAllByLabelText("Module title")[1], "Assessment");
    await userEvent.click(screen.getByRole("button", { name: "Save template" }));
    expect(sent(calls, "POST", "/site-templates/")).toEqual({
      name: "Short course",
      description: "",
      is_default: true,
      structure: {
        modules: [
          { title: "Introduction", items: [{ kind: "page", title: "Welcome", body: "<p>Say hello.</p><p>Then begin.</p>" }] },
          { title: "Assessment", items: [] },
        ],
      },
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Saved the template “Short course”.");
    expect(await screen.findByText("GSA standard")).toBeInTheDocument();
  });

  it("edits a template, removes a page and a module, shows a refusal, and removes the template after asking", async () => {
    const { calls } = fakeServer({
      "GET /site-templates/": { body: page([standard]) },
      "PATCH /site-templates/1/": { status: 400, body: { structure: ["A template holds pages only, each with a title."] } },
      "DELETE /site-templates/1/": { status: 204 },
    });
    framed(<TemplatesScreen />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit the template “GSA standard”" }));
    expect(screen.getByLabelText("Page 1 starting text")).toHaveValue("<p>Hello</p>");
    await userEvent.click(screen.getByRole("button", { name: "Remove page 1 of module 1" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove module 2" }));
    await userEvent.click(screen.getByRole("button", { name: "Save template" }));
    expect(sent(calls, "PATCH", "/site-templates/1/")).toEqual({
      name: "GSA standard",
      description: "Every course",
      is_default: true,
      structure: { modules: [{ title: "Course overview", items: [] }] },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("A template holds pages only");
    await userEvent.click(screen.getByRole("button", { name: "Remove template" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove it for good" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    expect(await screen.findByRole("status")).toHaveTextContent("Removed the template “GSA standard”.");
  });

  it("cancels editing", async () => {
    fakeServer({ "GET /site-templates/": { body: page([standard]) } });
    framed(<TemplatesScreen />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit the template “GSA standard”" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "New template" })).toBeInTheDocument();
  });

  it("keeps text with tags as written for the server to clean", () => {
    expect(asHtml("<h2>Aims</h2>")).toBe("<h2>Aims</h2>");
    expect(asHtml("Fish & chips\nto go")).toBe("<p>Fish &amp; chips<br>to go</p>");
    expect(asHtml("")).toBe("");
  });
});
