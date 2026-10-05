import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Me } from "../api/types";
import { PAGES, pageOf, pagesFor, siteAddress, useHashRoute } from "./router";

const person = (roles: string[], is_superuser = false): Me => ({
  id: 1,
  username: "asha.persaud",
  name: "Asha Persaud",
  roles,
  is_superuser,
  mfa_required: false,
  mfa_verified: true,
  person_id: 1,
  person_kind: "staff",
  external_id: "E0001",
});

describe("pages by role", () => {
  it("gives everyone Home, To do, their courses, their data, their account and their notification settings", () => {
    const own = ["Home", "To do", "My courses", "My data", "My account", "Notification settings"];
    expect(pagesFor(person(["student"])).map((p) => p.label)).toEqual(own);
    expect(pagesFor(person(["lecturer"])).map((p) => p.label)).toEqual(own);
    expect(pagesFor(person([])).map((p) => p.label)).toEqual(own);
  });

  it("gives Admin to administrators and course administrators only, and says what every page is for", () => {
    expect(pagesFor(person(["course_admin"]))).toEqual(PAGES);
    expect(pagesFor(person(["administrator"]))).toEqual(PAGES);
    expect(pagesFor(person([], true))).toEqual(PAGES);
    expect(pagesFor(person(["auditor"])).map((p) => p.label)).not.toContain("Admin");
    expect(PAGES.every((p) => p.desc.length > 0)).toBe(true);
  });

  it("finds the page an address belongs to, for the breadcrumb: a course site is under My courses", () => {
    expect(pageOf("/sites/12")?.label).toBe("My courses");
    expect(pageOf("/sites/12/gradebook")?.label).toBe("My courses");
    expect(pageOf("/courses")?.label).toBe("My courses");
    expect(pageOf("/my-data")?.label).toBe("My data");
    expect(pageOf("/to-do?x=1")?.label).toBe("To do");
    expect(pageOf("/sitesx")).toBeUndefined();
    expect(pageOf("/")).toBeUndefined();
  });

  it("reads a course site and its tab from the address, opening Content for a tab it does not know", () => {
    expect(siteAddress("/sites/4")).toEqual({ id: 4, tab: "content" });
    expect(siteAddress("/sites/4/gradebook")).toEqual({ id: 4, tab: "gradebook" });
    expect(siteAddress("/sites/4/quizzes")).toEqual({ id: 4, tab: "content" });
    expect(siteAddress("/courses")).toBeNull();
  });
});

describe("hash routing", () => {
  afterEach(() => {
    window.location.hash = "";
  });

  it("starts on Home and follows the address", async () => {
    const { result } = renderHook(() => useHashRoute());
    expect(result.current[0]).toBe("/");
    await act(async () => {
      result.current[1]("/sites/4/assignments");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(window.location.hash).toBe("#/sites/4/assignments");
    expect(result.current[0]).toBe("/sites/4/assignments");
  });
});
