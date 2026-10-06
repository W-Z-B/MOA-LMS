import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { SiteContents } from "../../api/types";
import { FrameContext } from "../../app/frame";
import { fakeServer } from "../../test/fetch";
import { SiteScreen } from "./SiteScreen";

const contents: SiteContents = {
  site: {
    id: 9,
    code: "AGR101-2026-27-S1-MRP",
    title: "Introduction to Crop Production",
    term_code: "2026-27-S1",
    campus_code: "MRP",
    source: "local",
    kind: "academic",
    description: "",
    is_published: true,
    coursework_weight: "40.00",
    my_role: "student",
    members: 3,
  },
  modules: [],
  announcements: [],
};
function open(tab: "content" | "quizzes", routes: Record<string, unknown> = {}) {
  fakeServer({
    "GET /sites/9/contents/": { body: contents },
    ...(routes as Record<string, { body?: unknown }>),
  });
  const onTab = vi.fn();
  const setCrumb = vi.fn();
  render(
    <FrameContext.Provider value={{ setCrumb, decided: vi.fn() }}>
      <SiteScreen siteId={9} tab={tab} onTab={onTab} />
    </FrameContext.Provider>,
  );
  return { onTab, setCrumb };
}

describe("a course site in the frame (items 2.07 and 2.10)", () => {
  it("names itself in the breadcrumb, and gives each tab an address", async () => {
    const { onTab, setCrumb } = open("content");
    expect(await screen.findByRole("heading", { name: contents.site.title, level: 1 })).toBeInTheDocument();
    // The crumb is set in an effect, which may run just after the heading appears on a busy machine.
    await waitFor(() => expect(setCrumb).toHaveBeenCalledWith(contents.site.title));
    expect(screen.getByRole("tab", { name: "Content" })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(screen.getByRole("tab", { name: "Gradebook" }));
    expect(onTab).toHaveBeenCalledWith("gradebook");
  });

  it("loads the Quizzes tab when it is opened (feature 10)", async () => {
    open("quizzes", { "GET /quizzes/": { body: { count: 0, next: null, previous: null, results: [] } } });
    expect(await screen.findByText("No quizzes yet.")).toBeInTheDocument();
  });
});
