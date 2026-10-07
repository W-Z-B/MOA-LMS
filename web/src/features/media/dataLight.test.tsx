import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PageBody } from "../content/PageBody";
import { chosen, isDataLight, setDataLight, suggested, useDataLight } from "./dataLight";
import { holdPictures } from "./pictures";

vi.mock("../content/maths", () => ({ drawMaths: () => Promise.resolve() }));

function device(connection: object | undefined, phone = false) {
  vi.stubGlobal("navigator", { ...navigator, connection });
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: phone, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }));
}

describe("data-light mode (item 4.05)", () => {
  afterEach(() => setDataLight(null));

  it("follows the connection hints, then the kind of device, until the person chooses", () => {
    device({ saveData: true });
    expect(suggested()).toBe(true);
    device({ effectiveType: "slow-2g" });
    expect(suggested()).toBe(true);
    device({ effectiveType: "4g", type: "wifi" }, true);
    expect(suggested()).toBe(false); // a phone on Wi-Fi
    device({ type: "cellular" });
    expect(suggested()).toBe(true);
    device(undefined, true);
    expect(suggested()).toBe(true); // a phone, no hints
    device(undefined, false);
    expect(isDataLight()).toBe(false); // a computer
    setDataLight(true);
    expect(chosen()).toBe(true);
    expect(isDataLight()).toBe(true);
    setDataLight(false);
    expect(isDataLight()).toBe(false);
  });

  it("tells every screen when it changes", () => {
    device(undefined, false);
    const { result } = renderHook(() => useDataLight());
    expect(result.current).toBe(false);
    act(() => setDataLight(true));
    expect(result.current).toBe(true);
  });

  it("holds a page's pictures behind a button with what they show and their size", async () => {
    device(undefined, false);
    setDataLight(true);
    const html = '<p>Seedlings.</p><img src="/api/v1/content/31/download/" alt="Maize seedlings"><img src="/api/v1/content/32/download/" alt="">';
    render(<PageBody html={html} sizes={{ 31: 2 * 1024 * 1024 }} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(document.querySelector("img[src]")).toBeNull(); // nothing is fetched
    const show = screen.getByRole("button", { name: "Show picture: Maize seedlings (2 MB)" });
    expect(screen.getByRole("button", { name: "Show picture: a picture" })).toBeInTheDocument();
    await userEvent.click(show);
    expect(screen.getByRole("img", { name: "Maize seedlings" })).toHaveAttribute("src", "/api/v1/content/31/download/");
    expect(screen.queryByRole("button", { name: /Maize seedlings/ })).not.toBeInTheDocument();
  });

  it("leaves a page without pictures, or with data-light off, as it is", () => {
    expect(holdPictures("<p>No pictures</p>")).toBe("<p>No pictures</p>");
    device(undefined, false);
    render(<PageBody html={'<img src="/api/v1/content/31/download/" alt="Maize">'} />);
    expect(screen.getByRole("img", { name: "Maize" })).toHaveAttribute("src", "/api/v1/content/31/download/");
  });
});
