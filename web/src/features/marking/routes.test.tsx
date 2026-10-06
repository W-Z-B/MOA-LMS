import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { markingAddress, pageOf } from "../../app/router";
import { fakeServer } from "../../test/fetch";
import { assignment, page } from "../../test/marking";
import { markingScreen } from "./routes";

describe("the addresses of marking, rubrics, accommodations and notification settings (item 2.10)", () => {
  it("reads a submission's marking address and a course's rubrics", () => {
    expect(markingAddress("/sites/4/assignments/12/marking/55")).toEqual({ kind: "marking", siteId: 4, assignmentId: 12, submissionId: 55 });
    expect(markingAddress("/sites/4/assignments/12/marking")).toEqual({ kind: "marking", siteId: 4, assignmentId: 12, submissionId: null });
    expect(markingAddress("/sites/4/rubrics")).toEqual({ kind: "site-rubrics", siteId: 4 });
    expect(markingAddress("/sites/4/assignments")).toBeNull();
    // Under My courses in the breadcrumb, as the course site is.
    expect(pageOf("/sites/4/assignments/12/marking/55")?.label).toBe("My courses");
    expect(pageOf("/notification-settings")?.label).toBe("Notification settings");
    expect(markingScreen("/courses", vi.fn())).toBeNull();
  });

  it("opens each screen its address names, its code fetched on first use", async () => {
    fakeServer({
      "GET /assignments/3/": { body: assignment() },
      "GET /assignments/3/submissions/": { body: [] },
      "GET /rubrics/?site=9": page([]),
      "GET /rubrics/?library=1": page([]),
      "GET /accommodations/": page([]),
      "GET /notifications/preferences/": { body: [] },
    });
    const views: [string, string][] = [
      ["/sites/9/assignments/3/marking", "Soil profile report"],
      ["/sites/9/rubrics", "Rubrics and marking guides"],
      ["/rubrics", "GSA rubric library"],
      ["/accommodations", "Accommodations"],
      ["/notification-settings", "Notification settings"],
    ];
    for (const [path, heading] of views) {
      const { unmount } = render(<>{markingScreen(path, vi.fn())}</>);
      expect(await screen.findByRole("heading", { name: heading, level: 1 })).toBeInTheDocument();
      unmount();
    }
  });
});
