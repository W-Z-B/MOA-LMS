import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FrameContext } from "../../app/frame";
import { fakeServer } from "../../test/fetch";
import { contents, item, module } from "./fixtures";
import { DocumentView, PageBody } from "./PageBody";
import PageScreen from "./PageScreen";

const katex = vi.hoisted(() => ({
  render: vi.fn((tex: string, element: HTMLElement, options: { displayMode: boolean; trust: boolean }) => {
    if (tex === "\\bad{") throw new Error("parse error");
    element.textContent = `${options.displayMode ? "display" : "inline"}:${tex}:trust=${options.trust}`;
  }),
}));
vi.mock("katex", () => ({ default: katex }));
vi.mock("katex/dist/katex.min.css", () => ({}));
vi.mock("./PdfViewer", () => ({ default: ({ title }: { title: string }) => <p>Viewer for {title}</p> }));

const maths = '<h2>Yield</h2><p>Yield is <span data-math="\\frac{w}{a}">\\frac{w}{a}</span> per hectare.</p><div data-math="y=mx">y=mx</div>';

function open(role: "student" | "lecturer", page = item(11, 1, "Measuring yield", { body: maths })) {
  const server = fakeServer({
    "GET /content/11/": { body: page },
    "GET /sites/9/contents/": { body: contents([module(1, "Week 1", [page])], role) },
  });
  const setCrumb = vi.fn();
  render(
    <FrameContext.Provider value={{ setCrumb, decided: vi.fn() }}>
      <PageScreen siteId={9} itemId={11} />
    </FrameContext.Provider>,
  );
  return { ...server, setCrumb };
}

describe("reading a page (items 2.12 and 2.16)", () => {
  it("shows the cleaned text with its maths drawn by KaTeX without trust, under its title", async () => {
    const { setCrumb } = open("student");
    expect(await screen.findByRole("heading", { name: "Measuring yield", level: 1 })).toBeInTheDocument();
    await waitFor(() => expect(setCrumb).toHaveBeenCalledWith("Measuring yield"));
    await waitFor(() => expect(screen.getByText("inline:\\frac{w}{a}:trust=false")).toBeInTheDocument());
    expect(screen.getByText("display:y=mx:trust=false")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Introduction to Crop Production" })).toHaveAttribute("href", "#/sites/9");
    expect(screen.queryByRole("link", { name: "Edit page" })).not.toBeInTheDocument();
  });

  it("offers teaching staff the editor and says when the page is a draft", async () => {
    open("lecturer", item(11, 1, "Measuring yield", { is_published: false }));
    expect(await screen.findByRole("link", { name: "Edit page" })).toHaveAttribute("href", "#/sites/9/pages/11/edit");
    expect(screen.getByText(/A draft: students do not see it/)).toBeInTheDocument();
  });

  it("says when the page cannot be opened", async () => {
    fakeServer({ "GET /content/11/": { status: 404, body: { code: "not_found", detail: "Not found." } }, "GET /sites/9/contents/": { body: {} } });
    render(<PageScreen siteId={9} itemId={11} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});

describe("maths and documents in the page (items 2.12 and 2.14)", () => {
  it("shows a formula KaTeX cannot read as its TeX, marked", async () => {
    render(<PageBody html='<p><span data-math="\bad{">\bad{</span></p>' />);
    await waitFor(() => expect(document.querySelector(".math-error")).toHaveTextContent("\\bad{"));
  });

  it("loads nothing for a page without maths", () => {
    katex.render.mockClear();
    render(<PageBody html="<p>Plain</p>" />);
    expect(screen.getByText("Plain")).toBeInTheDocument();
    expect(katex.render).not.toHaveBeenCalled();
  });

  it("shows a photograph in the page, named by its title", () => {
    render(<DocumentView title="Maize seedlings" filename="seedlings.JPG" url="/api/v1/content/31/download/" />);
    expect(screen.getByRole("img", { name: "Maize seedlings" })).toHaveAttribute("src", "/api/v1/content/31/download/");
    expect(screen.getByRole("link", { name: "Download seedlings.JPG" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /document/ })).not.toBeInTheDocument();
  });

  it("opens a PDF in the viewer only when asked, and hides it again", async () => {
    render(<DocumentView title="Soil map" filename="map.pdf" url="/api/v1/content/32/download/" />);
    expect(screen.queryByText("Viewer for Soil map")).not.toBeInTheDocument();
    const show = screen.getByRole("button", { name: "Show the document here" });
    expect(show).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(show);
    expect(await screen.findByText("Viewer for Soil map")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Hide the document" }));
    expect(screen.queryByText("Viewer for Soil map")).not.toBeInTheDocument();
  });

  it("only offers a download for other files", () => {
    render(<DocumentView title="Budget" filename="budget.xlsx" url="/api/v1/content/33/download/" />);
    expect(screen.getByRole("link", { name: "Download budget.xlsx" })).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
