import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PdfViewer from "./PdfViewer";

// PDF.js draws on a canvas in a worker, which jsdom has neither of; a stand-in records what it is asked.
const pdfjs = vi.hoisted(() => {
  const rendered: number[] = [];
  const page = (n: number) => ({
    getViewport: ({ scale }: { scale: number }) => ({ width: 600 * scale, height: 800 * scale }),
    render: () => {
      rendered.push(n);
      return { promise: Promise.resolve(), cancel: vi.fn() };
    },
  });
  return {
    rendered,
    getDocument: vi.fn((_options: { data: Uint8Array; useWasm: boolean }) => ({
      promise: Promise.resolve({ numPages: 3, getPage: (n: number) => Promise.resolve(page(n)) }),
      destroy: vi.fn(() => Promise.resolve()),
    })),
    GlobalWorkerOptions: { workerSrc: "" },
  };
});
vi.mock("pdfjs-dist", () => pdfjs);
vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({ default: "/assets/pdf.worker.mjs" }));

beforeEach(() => {
  pdfjs.rendered.length = 0;
});

describe("a PDF shown in the page (item 2.14)", () => {
  it("fetches the file with the session, shows it a page at a time without WebAssembly, and pages through it", async () => {
    const fetchMock = vi.fn(async () => new Response(new Uint8Array([37, 80, 68, 70]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<PdfViewer url="/api/v1/content/32/download/" title="Soil map" />);
    expect(await screen.findByText("Page 1 of 3")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/content/32/download/", { credentials: "same-origin" });
    expect(pdfjs.getDocument.mock.calls[0][0].useWasm).toBe(false);
    expect(pdfjs.GlobalWorkerOptions.workerSrc).toBe("/assets/pdf.worker.mjs");
    expect(screen.getByRole("img", { name: "Soil map, page 1 of 3" })).toBeInTheDocument();
    await waitFor(() => expect(pdfjs.rendered).toEqual([1]));
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("Page 3 of 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    await waitFor(() => expect(pdfjs.rendered).toEqual([1, 2, 3]));
  });

  it("offers the download instead when the document cannot be shown", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    render(<PdfViewer url="/api/v1/content/32/download/" title="Soil map" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The document could not be shown. Download it instead.");
  });
});
