import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Me } from "../api/types";
import { PAGES, pageOf, pagesFor, siteAddress, useHashRoute } from "./router";

const person = (roles: string[], is_superuser = false, person_kind: Me["person_kind"] = "staff"): Me => ({
  id: 1,
  username: "asha.persaud",
  name: "Asha Persaud",
  roles,
  is_superuser,
  mfa_required: false,
  mfa_verified: true,
  person_id: 1,
  person_kind,
  external_id: "E0001",
});

describe("pages by role", () => {
  it("gives everyone Home, To do, their courses, their data and their account, and staff their development", () => {
    const own = ["Home", "To do", "My courses", "Messages", "Calendar", "Discussion", "My data", "My account"];
    expect(pagesFor(person(["student"], false, "student")).map((p) => p.label)).toEqual(own);
    expect(pagesFor(person([], false, null)).map((p) => p.label)).toEqual(own);
    expect(pagesFor(person(["lecturer"])).map((p) => p.label)).toEqual([...own, "Staff development"]);
    expect(pagesFor(person([])).map((p) => p.label)).toEqual([...own, "Staff development"]);
  });

  it("gives Admin to those the console has a section for, and says what every page is for", () => {
    expect(pagesFor(person(["course_admin"]))).toEqual(PAGES);
    expect(pagesFor(person(["administrator"], false, null))).toEqual(PAGES);
    expect(pagesFor(person([], true))).toEqual(PAGES);
    expect(pagesFor(person(["auditor"], false, null)).map((p) => p.label)).toContain("Admin");
    expect(pagesFor(person(["dpo"], false, null)).map((p) => p.label)).toEqual(["Home", "To do", "My courses", "Messages", "Calendar", "Discussion", "My data", "My account", "Admin"]);
    expect(pagesFor(person(["lecturer"])).map((p) => p.label)).not.toContain("Admin");
    expect(PAGES.every((p) => p.desc.length > 0)).toBe(true);
  });

  it("finds the page an address belongs to, for the breadcrumb: a course site is under My courses", () => {
    expect(pageOf("/sites/12")?.label).toBe("My courses");
    expect(pageOf("/sites/12/gradebook")?.label).toBe("My courses");
    expect(pageOf("/courses")?.label).toBe("My courses");
    expect(pageOf("/my-data")?.label).toBe("My data");
    expect(pageOf("/to-do?x=1")?.label).toBe("To do");
    expect(pageOf("/staff-development/requests/4")?.label).toBe("Staff development");
    expect(pageOf("/certificates")?.label).toBe("Staff development");
    expect(pageOf("/admin/audit")?.label).toBe("Admin");
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
