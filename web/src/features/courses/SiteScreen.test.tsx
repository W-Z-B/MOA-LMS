import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Assignment, SiteContents } from "../../api/types";
import { FrameContext } from "../../app/frame";
import { flush, pendingCount } from "../../app/offlineQueue";
import { fakeServer, offline } from "../../test/fetch";
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
const assignment: Assignment = {
  id: 3,
  site: 9,
  title: "Field notebook check",
  instructions: "",
  due_at: "2026-10-08T14:00:00Z",
  max_mark: "20.00",
  weight: "1.00",
  allow_late: true,
  is_published: true,
  my_submission: null,
  submissions_count: null,
};

function open(tab: "content" | "assignments" | "quizzes", routes: Record<string, unknown> = {}) {
  fakeServer({
    "GET /sites/9/contents/": { body: contents },
    "GET /assignments/": { body: { count: 1, next: null, previous: null, results: [assignment] } },
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
    expect(setCrumb).toHaveBeenCalledWith(contents.site.title);
    expect(screen.getByRole("tab", { name: "Content" })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(screen.getByRole("tab", { name: "Gradebook" }));
    expect(onTab).toHaveBeenCalledWith("gradebook");
  });

  it("keeps a typed answer on the device without a connection, then shows it sent (item 4.02)", async () => {
    open("assignments", { "POST /assignments/3/submit/": [offline, { status: 201, body: { id: 1 } }] });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Open" }));
    await user.type(screen.getByLabelText("Your answer"), "Notebook photographed and labelled.");
    await user.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Waiting to send");
    expect(pendingCount()).toBe(1);
    await flush();
    expect(await screen.findByText("Sent")).toBeInTheDocument();
    expect(pendingCount()).toBe(0);
  });

  it("asks for a connection when a file is attached, as a file cannot wait on the device", async () => {
    open("assignments", { "POST /assignments/3/submit/": offline });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Open" }));
    await user.upload(screen.getByLabelText("Or attach a file"), new File(["x"], "notes.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No connection.");
    expect(pendingCount()).toBe(0);
    expect(within(document.body).queryByText("Waiting to send")).not.toBeInTheDocument();
  });

  it("loads the Quizzes tab when it is opened (feature 10)", async () => {
    open("quizzes", { "GET /quizzes/": { body: { count: 0, next: null, previous: null, results: [] } } });
    expect(await screen.findByText("No quizzes yet.")).toBeInTheDocument();
  });
});
