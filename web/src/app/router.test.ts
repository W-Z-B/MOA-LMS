import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { NAV, useHashRoute } from "./router";

afterEach(() => {
  window.location.hash = "";
});

describe("hash routing", () => {
  it("starts at My courses and follows the address", async () => {
    const { result } = renderHook(() => useHashRoute());
    expect(result.current[0]).toBe("/");
    act(() => result.current[1]("/sites/4"));
    await act(async () => {
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(window.location.hash).toBe("#/sites/4");
    expect(result.current[0]).toBe("/sites/4");
  });

  it("offers Admin only to administrators and course administrators", () => {
    expect(NAV.find((item) => item.path === "/admin")?.roles).toEqual(["administrator", "course_admin"]);
    expect(NAV.find((item) => item.path === "/")?.roles).toBeUndefined();
  });
});
