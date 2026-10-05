import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { RichEditor } from "./RichEditor";

// KaTeX is drawn for real in the browser journeys; here a stand-in shows that formulas are handed to it.
vi.mock("./maths", () => ({
  loadKatex: () => Promise.resolve({}),
  drawFormula: (_katex: unknown, element: HTMLElement, tex: string) => {
    element.textContent = `drawn:${tex}`;
  },
}));

// ProseMirror measures the selection to scroll it into view; jsdom draws nothing, so ranges measure as empty.
beforeAll(() => {
  const none = () => Object.assign([], { item: () => null }) as unknown as DOMRectList;
  Range.prototype.getClientRects = none;
  Range.prototype.getBoundingClientRect = () => new DOMRect();
  document.elementFromPoint = () => null;
});

const pictures = [{ id: 31, title: "Maize seedlings", url: "/api/v1/content/31/download/" }];

function open(html = "<p>Seeds need water.</p>") {
  const onChange = vi.fn();
  render(<RichEditor initialHtml={html} onChange={onChange} pictures={pictures} label="Page text" />);
  return { onChange, last: () => onChange.mock.calls.at(-1)?.[0] as string };
}

describe("the page editor (item 2.12)", () => {
  it("opens with the page's text in a named text box and a labelled toolbar", async () => {
    open();
    const box = await screen.findByRole("textbox", { name: "Page text" });
    expect(box).toHaveTextContent("Seeds need water.");
    expect(screen.getByRole("toolbar", { name: "Formatting" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Heading 2" })).toHaveAttribute("aria-pressed", "false");
  });

  it("turns a paragraph into a heading, and says the heading is on", async () => {
    const { last } = open();
    await screen.findByRole("textbox", { name: "Page text" });
    await userEvent.click(screen.getByRole("button", { name: "Heading 3" }));
    expect(last().startsWith("<h3>Seeds need water.</h3>")).toBe(true);
    expect(screen.getByRole("button", { name: "Heading 3" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Text" }));
    expect(last().startsWith("<p>Seeds need water.</p>")).toBe(true);
  });

  it("adds a picture from the course's files only with alternative text", async () => {
    const { last } = open();
    await screen.findByRole("textbox", { name: "Page text" });
    await userEvent.click(screen.getByRole("button", { name: "Picture" }));
    const add = screen.getByRole("button", { name: "Add picture" });
    expect(add).toBeDisabled();
    expect(screen.getByLabelText("Picture from this course's files")).toHaveValue(pictures[0].url);
    await userEvent.type(screen.getByLabelText(/What the picture shows/), "Maize seedlings ten days after sowing");
    await userEvent.click(add);
    expect(last()).toContain('<img src="/api/v1/content/31/download/" alt="Maize seedlings ten days after sowing">');
    expect(screen.queryByRole("group", { name: "Picture" })).not.toBeInTheDocument();
  });

  it("says a picture must be a file on the course when there is none", async () => {
    render(<RichEditor initialHtml="" onChange={vi.fn()} pictures={[]} label="Page text" />);
    await screen.findByRole("textbox", { name: "Page text" });
    await userEvent.click(screen.getByRole("button", { name: "Picture" }));
    expect(screen.getByText(/This course has no photographs yet/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("group", { name: "Picture" })).not.toBeInTheDocument();
  });

  it("stores a formula as TeX in data-math, inline or on a line of its own, and previews it", async () => {
    const { last } = open("<p>Area</p>");
    await screen.findByRole("textbox", { name: "Page text" });
    await userEvent.click(screen.getByRole("button", { name: "Maths" }));
    const group = screen.getByRole("group", { name: "Maths" });
    expect(group).toHaveTextContent("Type a formula to see it here.");
    await userEvent.type(screen.getByLabelText("Formula, written in TeX"), "x^2");
    await waitFor(() => expect(group).toHaveTextContent("drawn:x^2"));
    await userEvent.click(screen.getByRole("button", { name: "Add formula" }));
    expect(last()).toContain('<span data-math="x^2">x^2</span>');

    await userEvent.click(screen.getByRole("button", { name: "Maths" }));
    await userEvent.type(screen.getByLabelText("Formula, written in TeX"), "a+b");
    await userEvent.click(screen.getByLabelText("On a line of its own"));
    await userEvent.click(screen.getByRole("button", { name: "Add formula" }));
    expect(last()).toContain('<div data-math="a+b">a+b</div>');
  });

  it("reads maths and tables back from a saved page, and edits the table", async () => {
    const { last } = open('<p>Rate <span data-math="\\frac{a}{b}">\\frac{a}{b}</span></p>');
    const box = await screen.findByRole("textbox", { name: "Page text" });
    await waitFor(() => expect(box).toHaveTextContent("drawn:\\frac{a}{b}"));
    await userEvent.click(screen.getByRole("button", { name: "Table" }));
    expect(last()).toContain("<table><tbody><tr><th");
    expect(last()).not.toContain("style=");
    const table = screen.getByRole("toolbar", { name: "Table" });
    expect(table).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add row" }));
    expect(last().match(/<tr>/g)).toHaveLength(4);
    await userEvent.click(screen.getByRole("button", { name: "Remove table" }));
    expect(last()).not.toContain("<table");
  });

  it("links the selected words, and undoes", async () => {
    const { last } = open("<p>planting guide</p>");
    await screen.findByRole("textbox", { name: "Page text" });
    await userEvent.click(screen.getByRole("button", { name: "Bold" }));
    await userEvent.click(screen.getByRole("button", { name: "Link" }));
    expect(screen.getByRole("button", { name: "Apply link" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Web address or e-mail"), "https://agriculture.gov.gy");
    await userEvent.click(screen.getByRole("button", { name: "Apply link" }));
    await userEvent.click(screen.getByRole("button", { name: "List" }));
    expect(last()).toMatch(/<ul>/);
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(last()).not.toMatch(/<ul>/);
    await userEvent.click(screen.getByRole("button", { name: "Redo" }));
    expect(last()).toMatch(/<ul>/);
  });
});
