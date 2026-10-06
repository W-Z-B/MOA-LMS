import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../../test/fetch";
import { contents, module } from "../content/fixtures";
import LibraryScreen from "./LibraryScreen";
import { libraryItem, page } from "./fixtures";

const ipm = libraryItem(1, "Integrated pest management");
const link = libraryItem(2, "CABI Compendium", {
  kind: "link",
  url: "https://www.cabi.org/",
  download_url: null,
  licence: "permission_held",
  open_licence: "",
  publisher: "",
  source: "CABI",
  is_open_resource: false,
  department_code: "",
  tags: [],
  may_change: false,
});
const site = { ...contents([], "lecturer").site, id: 9 };

function library(path = "", routes: Record<string, unknown> = {}) {
  const server = fakeServer({
    "GET /library/items/": { body: page([ipm, link]) },
    ...(routes as Record<string, { body?: unknown }>),
  });
  const onNavigate = vi.fn();
  render(<LibraryScreen path={path} onNavigate={onNavigate} />);
  return { ...server, onNavigate };
}

describe("the content library (item 5.14)", () => {
  it("lists material with its licence, publisher and shelf, and filters it", async () => {
    const { calls } = library();
    const list = await screen.findByRole("list", { name: "Library items" });
    const first = within(list).getAllByRole("listitem")[0];
    expect(first).toHaveTextContent("Integrated pest management");
    expect(first).toHaveTextContent("CC BY · FAO · FAO e-learning Academy · Department AGRON");
    expect(within(first).getByText("Open resource")).toBeInTheDocument();
    expect(within(list).getAllByRole("listitem")[1]).toHaveTextContent("Used with the owner's permission · CABI · The whole School");
    expect(within(list).getByRole("link", { name: "Open the link" })).toHaveAttribute("href", "https://www.cabi.org/");
    await userEvent.click(screen.getByLabelText("Open educational resources only"));
    await userEvent.selectOptions(screen.getByLabelText("Kind"), "file");
    await waitFor(() => expect(calls.some((c) => c.path === "/library/items/?kind=file&open=true")).toBe(true));
  });

  it("adds an open educational resource with its publisher and open licence", async () => {
    const { calls } = library("", { "POST /library/items/": { body: libraryItem(3, "Soil health") } });
    await userEvent.click(await screen.findByRole("button", { name: "Add to the library" }));
    const form = screen.getByRole("form", { name: "Add to the library" });
    await userEvent.type(within(form).getByLabelText("Title"), "Soil health");
    await userEvent.upload(within(form).getByLabelText("File"), new File(["%PDF-1.7"], "soil.pdf", { type: "application/pdf" }));
    await userEvent.type(within(form).getByLabelText(/^Department/), "AGRON");
    await userEvent.click(within(form).getByLabelText(/An open educational resource/));
    expect(within(form).queryByLabelText("Whose material is this?")).not.toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText("Publisher"), "FAO");
    await userEvent.selectOptions(within(form).getByLabelText("Which open licence"), "cc_by");
    await userEvent.type(within(form).getByLabelText("Source and credit"), "FAO, 2025");
    await userEvent.type(within(form).getByLabelText(/^Tags/), "soil, health");
    await userEvent.click(within(form).getByRole("button", { name: "Add to the library" }));
    const sent = calls.find((c) => c.method === "POST")?.body as FormData;
    expect(sent.get("is_open_resource")).toBe("true");
    expect(sent.get("licence")).toBe("open_licence");
    expect(sent.get("open_licence")).toBe("cc_by");
    expect(sent.get("publisher")).toBe("FAO");
    expect(sent.getAll("tags")).toEqual(["soil", "health"]);
    expect(await screen.findByText("Added “Soil health” to the library.")).toBeInTheDocument();
  });

  it("adds a link and a page, and says what the server refused", async () => {
    const { calls } = library("", { "POST /library/items/": [{ status: 400, body: { source: ["Say where the material comes from and how to credit its author."] } }, { body: libraryItem(4, "Rules") }] });
    await userEvent.click(await screen.findByRole("button", { name: "Add to the library" }));
    const form = screen.getByRole("form", { name: "Add to the library" });
    await userEvent.selectOptions(within(form).getByLabelText("What it is"), "link");
    await userEvent.type(within(form).getByLabelText("Title"), "Guide");
    await userEvent.type(within(form).getByLabelText("Web address"), "https://example.org/");
    await userEvent.selectOptions(within(form).getByLabelText("Whose material is this?"), "gsa_own");
    await userEvent.click(within(form).getByRole("button", { name: "Add to the library" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("source: Say where the material comes from");
    const posts = () => calls.filter((c) => c.method === "POST").map((c) => c.body as FormData);
    expect(posts()[0].get("url")).toBe("https://example.org/");
    await userEvent.selectOptions(within(form).getByLabelText("What it is"), "page");
    await userEvent.type(within(form).getByLabelText("Text"), "Wash hands");
    await userEvent.click(within(form).getByRole("button", { name: "Add to the library" }));
    await waitFor(() => expect(posts()).toHaveLength(2));
    expect(posts()[1].get("body_format")).toBe("text");
    await userEvent.click(await screen.findByRole("button", { name: "Add to the library" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  });

  it("copies an item into a module of a course the person teaches", async () => {
    const { calls } = library("", {
      "GET /sites/": { body: page([site, { ...site, id: 10, code: "X", my_role: "student" }]) },
      "GET /sites/9/contents/": { body: contents([module(1, "Week 1: Soils", [])]) },
      "POST /library/items/1/use/": { body: { item: 50, module: 1, site: 9, title: "Integrated pest management" } },
    });
    const list = await screen.findByRole("list", { name: "Library items" });
    await userEvent.click(within(list).getAllByRole("button", { name: "Use in a course" })[0]);
    const form = screen.getByRole("form", { name: "Use “Integrated pest management” in a course" });
    const course = within(form).getByLabelText("Course");
    await waitFor(() => expect(within(course).getAllByRole("option")).toHaveLength(2)); // the course taught, not the one studied
    await userEvent.selectOptions(course, "9");
    await userEvent.selectOptions(await within(form).findByLabelText("Module"), await within(form).findByRole("option", { name: "Week 1: Soils" }));
    await userEvent.click(within(form).getByRole("button", { name: "Copy into the course" }));
    expect(calls.find((c) => c.path === "/library/items/1/use/")?.body).toEqual({ module: 1 });
    expect(await screen.findByText(/Copied “Integrated pest management” into the course as a draft/)).toBeInTheDocument();
  });

  it("removes an item the person may change", async () => {
    const { calls } = library("", { "DELETE /library/items/1/": { status: 204 } });
    await userEvent.click(await screen.findByRole("button", { name: "Remove “Integrated pest management” from the library" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(true);
    expect(await screen.findByText("Removed “Integrated pest management” from the library.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove “CABI Compendium” from the library" })).not.toBeInTheDocument();
  });

  it("shares a course's item to a department's shelf", async () => {
    const { calls, onNavigate } = library("/share?item=12", {
      "GET /content/12/": { body: { title: "Field sheet" } },
      "POST /library/items/share/": { body: libraryItem(9, "Field sheet") },
    });
    expect(await screen.findByText(/A copy of “Field sheet” goes on the shelf you choose/)).toBeInTheDocument();
    await userEvent.type(screen.getAllByLabelText(/^Department/)[0], " AGRON ");
    await userEvent.click(screen.getByRole("button", { name: "Share a copy" }));
    expect(calls.find((c) => c.path === "/library/items/share/")?.body).toEqual({ item: 12, department_code: "AGRON", description: "" });
    expect(onNavigate).toHaveBeenCalledWith("/library");
  });

  it("lists department question banks with their licences and shares a course's bank", async () => {
    const { calls } = library("/banks", {
      "GET /library/banks/": {
        body: [{ id: 7, name: "Soils questions", department_code: "AGRON", questions: 12, licence: "gsa_own", open_licence: "", source: "", publisher: "", copied_from: 3 }],
      },
      "GET /question-banks/": { body: page([{ id: 3, name: "AGR101 bank", site: 9, owner_label: "AGR101", can_manage: true }]) },
      "POST /library/banks/share/": { body: { id: 8, name: "AGR101 bank", department_code: "AGRON", questions: 12 } },
    });
    const banks = await screen.findByRole("list", { name: "Department question banks" });
    expect(banks).toHaveTextContent("12 questions · GSA's own material");
    await userEvent.selectOptions(await screen.findByLabelText("Bank"), "3");
    await userEvent.type(screen.getByLabelText("Department (its HRMS unit code)"), "AGRON");
    await userEvent.selectOptions(screen.getByLabelText("Whose material is this?"), "gsa_own");
    await userEvent.click(screen.getByRole("button", { name: "Share a copy" }));
    expect(calls.find((c) => c.path === "/library/banks/share/")?.body).toEqual({ bank: 3, department_code: "AGRON", name: "", licence: "gsa_own", open_licence: "", source: "" });
    expect(await screen.findByText("Copied 12 questions to the bank “AGR101 bank” of department AGRON.")).toBeInTheDocument();
  });
});
