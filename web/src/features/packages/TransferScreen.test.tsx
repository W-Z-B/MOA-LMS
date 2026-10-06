import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../../test/fetch";
import PackageForm from "./PackageForm";
import TransferScreen from "./TransferScreen";
import { pkg, siteAs } from "./fixtures";

describe("importing and exporting a course's content (item 6.08)", () => {
  it("offers the cartridge download and reports what an import brought in and left out", async () => {
    const { calls } = fakeServer({
      "GET /sites/9/contents/": { body: siteAs("lecturer") },
      "POST /sites/9/import-content/": {
        body: {
          format: "moodle_backup",
          modules: 2,
          items: 5,
          questions: 2,
          imported: [{ kind: "page", title: "Welcome", module: "Week 1" }],
          skipped: [{ title: "Chat", reason: "Forums and their posts are not imported." }],
          warnings: ["Welcome: pictures in the page were not imported; add them again."],
        },
      },
    });
    render(<TransferScreen siteId={9} />);
    expect(await screen.findByRole("link", { name: "Back to Introduction to Crop Production" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download as a Common Cartridge (.imscc)" })).toHaveAttribute("href", "/api/v1/sites/9/export-cartridge/");
    await userEvent.upload(screen.getByLabelText("File to import"), new File(["x"], "course.mbz"));
    await userEvent.click(screen.getByRole("button", { name: "Import into this course" }));
    const sent = calls.find((c) => c.method === "POST")!.body as FormData;
    expect(sent.get("file")).toBeInstanceOf(File);
    expect(await screen.findByRole("status")).toHaveTextContent("From the Moodle backup: 2 modules, 5 items and 2 questions, all as drafts.");
    expect(screen.getByText("Chat")).toBeInTheDocument();
    expect(screen.getByText(/pictures in the page were not imported/)).toBeInTheDocument();
    expect(screen.getByText("Imported (1)")).toBeInTheDocument();
  });

  it("says why a file was refused", async () => {
    fakeServer({
      "GET /sites/9/contents/": { body: siteAs("lecturer") },
      "POST /sites/9/import-content/": { status: 400, body: { code: "import_refused", detail: "The backup holds a file with an unsafe name ('../x')." } },
    });
    render(<TransferScreen siteId={9} />);
    await userEvent.upload(await screen.findByLabelText("File to import"), new File(["x"], "course.imscc"));
    await userEvent.click(screen.getByRole("button", { name: "Import into this course" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("unsafe name");
  });
});

describe("putting a package up (items 5.12, 5.13)", () => {
  it("sends the package with its licence and how it counts, and says H5P is made outside the LMS", async () => {
    const { calls } = fakeServer({ "POST /packages/": { body: { ...pkg(), storage: { used_bytes: 1, allowance_bytes: 2, percent: 50, warning: null } } } });
    const onSaved = vi.fn();
    render(<PackageForm moduleId={1} onSaved={onSaved} onCancel={vi.fn()} />);
    const form = screen.getByRole("form", { name: "Add a SCORM or H5P package" });
    expect(form).toHaveTextContent("H5P exercises are not written in the LMS");
    await userEvent.upload(within(form).getByLabelText("Package"), new File(["PK"], "soil.zip"));
    await userEvent.selectOptions(within(form).getByLabelText("Whose material is this?"), "open_licence");
    await userEvent.selectOptions(within(form).getByLabelText("Which open licence"), "cc_by_sa");
    await userEvent.type(within(form).getByLabelText("Source and credit"), "CABI Academy");
    const weight = within(form).getByLabelText(/Weight in coursework/);
    await userEvent.clear(weight);
    await userEvent.type(weight, "2");
    expect(form).toHaveTextContent("Scores come from the learner's own browser");
    await userEvent.click(within(form).getByRole("button", { name: "Put the package up" }));
    const sent = calls[0].body as FormData;
    expect([sent.get("module"), sent.get("licence"), sent.get("open_licence"), sent.get("source"), sent.get("weight")]).toEqual(["1", "open_licence", "cc_by_sa", "CABI Academy", "2"]);
    expect(onSaved).toHaveBeenCalled();
  });

  it("shows the server's reason for refusing a package", async () => {
    fakeServer({ "POST /packages/": { status: 400, body: { file: ["The package holds a file with an unsafe name ('../evil.html')."] } } });
    render(<PackageForm moduleId={1} onSaved={vi.fn()} onCancel={vi.fn()} />);
    await userEvent.upload(screen.getByLabelText("Package"), new File(["PK"], "soil.zip"));
    await userEvent.selectOptions(screen.getByLabelText("Whose material is this?"), "gsa_own");
    await userEvent.click(screen.getByRole("button", { name: "Put the package up" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("file: The package holds a file with an unsafe name");
  });
});
