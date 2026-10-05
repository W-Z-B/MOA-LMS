import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { markingAddress, pageOf } from "../../app/router";
import { AccommodationsScreen } from "../accommodations/AccommodationsScreen";
import { NotificationSettingsScreen } from "../notifications/NotificationSettingsScreen";
import { RubricsScreen } from "../rubrics/RubricsScreen";
import { MarkingScreen } from "./MarkingScreen";
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
  });

  it("opens the screen each address names, and nothing for any other", () => {
    const go = vi.fn();
    const marking = markingScreen("/sites/4/assignments/12/marking/55", go) as ReactElement<{ submissionId: number }>;
    expect(marking.type).toBe(MarkingScreen);
    expect(marking.props.submissionId).toBe(55);
    expect((markingScreen("/sites/4/rubrics", go) as ReactElement).type).toBe(RubricsScreen);
    expect((markingScreen("/rubrics", go) as ReactElement<{ siteId: number | null }>).props.siteId).toBeNull();
    expect((markingScreen("/accommodations", go) as ReactElement).type).toBe(AccommodationsScreen);
    expect((markingScreen("/notification-settings", go) as ReactElement).type).toBe(NotificationSettingsScreen);
    expect(markingScreen("/courses", go)).toBeNull();
  });
});
