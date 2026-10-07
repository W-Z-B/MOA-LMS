import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SiteContents, SiteRole } from "../../api/types";
import { FrameContext } from "../../app/frame";
import { insightsSection, siteAddress } from "../../app/router";
import { fakeServer } from "../../test/fetch";
import { analytics, studentProgress } from "../../test/insights";
import { SiteScreen } from "../courses/SiteScreen";

const contents = (role: SiteRole): SiteContents => ({
  site: {
    id: 9,
    code: "AGR205-2026-27-S1-MRP",
    title: "Soil Science and Fertility",
    term_code: "2026-27-S1",
    campus_code: "MRP",
    source: "srms",
    kind: "academic",
    description: "",
    is_published: true,
    coursework_weight: "40.00",
    my_role: role,
    members: 3,
  },
  modules: [],
  announcements: [],
});

function open(role: SiteRole, tab: "insights" | "progress") {
  fakeServer({
    "GET /sites/9/contents/": { body: contents(role) },
    "GET /sites/9/insights/": { body: analytics },
    "GET /sites/9/my-progress/": { body: studentProgress },
  });
  render(
    <FrameContext.Provider value={{ setCrumb: vi.fn(), decided: vi.fn() }}>
      <SiteScreen siteId={9} tab={tab} onTab={vi.fn()} />
    </FrameContext.Provider>,
  );
}

describe("the course site's insight tabs (items 6.01, 6.02)", () => {
  it("gives teaching staff Insights and no My progress", async () => {
    open("lecturer", "insights");
    expect(await screen.findByRole("tab", { name: "Insights" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "My progress" })).not.toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "Content" })).toBeInTheDocument();
  });

  it("gives a student My progress and never Insights, even at its address", async () => {
    open("student", "insights");
    expect(await screen.findByRole("tab", { name: "My progress" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Insights" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Content" })).not.toBeInTheDocument();
  });

  it("opens a student's progress at its address", async () => {
    open("student", "progress");
    expect(await screen.findByText("Coursework so far")).toBeInTheDocument();
  });

  it("reads the tab and the part of Insights from the address", () => {
    expect(siteAddress("/sites/4/insights/alerts")).toEqual({ id: 4, tab: "insights" });
    expect(siteAddress("/sites/4/progress")).toEqual({ id: 4, tab: "progress" });
    expect(insightsSection("/sites/4/insights/alerts")).toBe("alerts");
    expect(insightsSection("/sites/4/insights/outcomes?x=1")).toBe("outcomes");
    expect(insightsSection("/sites/4/insights")).toBe("overview");
    expect(insightsSection("/sites/4/insights/nonsense")).toBe("overview");
  });
});
