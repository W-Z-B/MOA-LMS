import { describe, expect, it } from "vitest";
import type { Me } from "../api/types";
import { dmy, initials, longDate, plural, when } from "./format";
import { roleTitle, shortCampus, usesCampusSwitch } from "./people";

describe("how dates and names are written", () => {
  it("writes dates the same on every device", () => {
    expect(dmy("2026-03-02")).toBe("02/03/2026");
    expect(dmy(null)).toBe("");
    expect(longDate("2026-10-02")).toBe("Friday 2 October 2026");
    expect(initials("Indira Devi Narine")).toBe("IN");
    expect(initials("Kezia")).toBe("K");
    expect(initials("")).toBe("");
    expect(plural(1, "course", "courses")).toBe("1 course");
    expect(plural(3, "course", "courses")).toBe("3 courses");
  });

  it("says a moment this week by its day, and one further off by its date", () => {
    const now = new Date("2026-10-05T12:00:00");
    expect(when("2026-10-07T14:30:00", now)).toBe("Wednesday 14:30");
    expect(when("2026-10-20T14:30:00", now)).toMatch(/^20\/10\/2026/);
  });
});

describe("who the person is", () => {
  const me = (over: Partial<Me>): Me => ({
    id: 1,
    username: "x",
    name: "X",
    roles: [],
    is_superuser: false,
    mfa_required: false,
    mfa_verified: true,
    person_id: null,
    person_kind: null,
    external_id: null,
    ...over,
  });

  it("names roles as people say them, from the server, never as codes", () => {
    expect(roleTitle(me({ title: "Lecturer, AGR101", roles: ["lecturer"] }))).toBe("Lecturer, AGR101");
    expect(roleTitle(me({ is_superuser: true }))).toBe("System administrator");
    expect(roleTitle(me({}))).toBe("No role yet");
    expect(roleTitle(me({ roles: ["auditor"] }))).toBe("");
  });

  it("offers the campus switch to those who look after every campus", () => {
    expect(usesCampusSwitch(me({ persona: "admin" }))).toBe(true);
    expect(usesCampusSwitch(me({ persona: "course_admin" }))).toBe(true);
    expect(usesCampusSwitch(me({ persona: "office" }))).toBe(true);
    expect(usesCampusSwitch(me({ persona: "lecturer" }))).toBe(false);
    expect(usesCampusSwitch(me({ persona: "student" }))).toBe(false);
    expect(shortCampus("Mon Repos Campus")).toBe("Mon Repos");
  });
});
