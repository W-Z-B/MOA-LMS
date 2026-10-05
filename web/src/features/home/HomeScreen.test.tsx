import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { HomeSummary, Me } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { HomeScreen } from "./HomeScreen";

const base: Me = {
  id: 1,
  username: "kezia.persaud",
  name: "Kezia Persaud",
  roles: ["student"],
  is_superuser: false,
  mfa_required: false,
  mfa_verified: true,
  person_id: 1,
  person_kind: "student",
  external_id: "S2026901",
  persona: "student",
  title: "Student",
};
const SITE = { site_id: 9, site_code: "AGR101-2026-27-S1-MRP", site_title: "Introduction to Crop Production" };
const empty: HomeSummary = { persona: "student", as_at: "2026-10-05", waiting: 0, student: null, teaching: null, sites: null };

const studentHome: HomeSummary = {
  ...empty,
  waiting: 2,
  student: {
    due: [
      { kind: "assignment", id: 3, title: "Field notebook check", ...SITE, due_at: "2026-10-08T14:00:00Z", link: "/sites/9/assignments", can_still_submit: true },
      { kind: "quiz", id: 5, title: "Soils quiz", ...SITE, due_at: "2026-10-09T14:00:00Z", link: "/sites/9/quizzes", can_still_submit: true },
    ],
    overdue: [
      { kind: "assignment", id: 4, title: "Crop calendar", ...SITE, due_at: "2026-10-01T14:00:00Z", link: "/sites/9/assignments", can_still_submit: true },
      { kind: "assignment", id: 6, title: "Pest survey", ...SITE, due_at: "2026-09-28T14:00:00Z", link: "/sites/9/assignments", can_still_submit: false },
    ],
    feedback: [
      {
        kind: "assignment",
        id: 2,
        title: "Germination trial report",
        site_id: 9,
        site_title: SITE.site_title,
        released_at: "2026-10-03T10:00:00Z",
        result: "38 out of 50",
        link: "/sites/9/assignments",
      },
    ],
    progress: [{ site_id: 9, code: SITE.site_code, title: SITE.site_title, completed: 3, released: 4, share: 0.75, coursework_percent: "76.00" }],
  },
};

const lecturerHome: HomeSummary = {
  ...empty,
  persona: "lecturer",
  waiting: 1,
  teaching: {
    to_mark: [
      { kind: "submission", site_id: 9, site_title: SITE.site_title, title: "Germination trial report: 1 to mark", count: 1, oldest: "2026-10-02T10:00:00Z", link: "/sites/9/assignments" },
      { kind: "logbook", site_id: 9, site_title: SITE.site_title, title: "Logbook entries: 2 to sign off", count: 2, oldest: "2026-10-03T10:00:00Z", link: "/sites/9/logbook" },
    ],
    quiet_sites: [{ site_id: 9, code: SITE.site_code, title: SITE.site_title, next_item_at: null }],
    not_seen: [{ person_id: 2, name: "Tevin Joseph", student_no: "S2026902", sites: [SITE.site_title], last_seen: null }],
    not_seen_count: 3,
    not_seen_days: 14,
  },
};

const adminHome: HomeSummary = {
  ...empty,
  persona: "course_admin",
  waiting: 4,
  sites: { total: 12, published: 10, drafts: 2, without_teacher: 1, students: 340, open_takedowns: 1 },
};

function home(me: Me, summary: HomeSummary | { status: number; body: unknown }) {
  fakeServer({ "GET /home/": "status" in summary ? summary : { body: summary } });
  const onNavigate = vi.fn();
  render(<HomeScreen me={me} onNavigate={onNavigate} />);
  return onNavigate;
}

describe("Home for a student (item 2.08)", () => {
  it("shows what is due this week, what is overdue, new feedback and progress in each course", async () => {
    const go = home(base, studentHome);
    expect(await screen.findByText("Monday 5 October 2026 · Student")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Home", level: 1 })).toBeInTheDocument();
    const figures = screen.getByRole("region", { name: "Figures" });
    expect(within(figures).getByText("Due this week").nextSibling).toHaveTextContent("2");
    expect(within(figures).getByText("Overdue").nextSibling).toHaveTextContent("2");

    const due = screen.getByRole("region", { name: "Due this week" });
    expect(within(due).getAllByRole("listitem")).toHaveLength(2);
    expect(within(due).getByText("Field notebook check")).toBeInTheDocument();
    await userEvent.click(within(due).getByRole("button", { name: "Open quiz: Soils quiz" }));
    expect(go).toHaveBeenCalledWith("/sites/9/quizzes");

    const overdue = screen.getByRole("region", { name: "Overdue" });
    expect(within(overdue).getByRole("button", { name: "Hand in: Crop calendar" })).toBeInTheDocument();
    // Work that is no longer accepted is shown, but offers nothing to do.
    expect(within(overdue).getByText(/no longer accepted/)).toBeInTheDocument();
    expect(within(overdue).queryByRole("button", { name: /Pest survey/ })).not.toBeInTheDocument();

    const feedback = screen.getByRole("region", { name: "New feedback" });
    expect(feedback).toHaveTextContent("38 out of 50");
    const progress = screen.getByRole("region", { name: "Your progress" });
    expect(progress).toHaveTextContent("3 of 4 items completed · coursework so far 76.00%");
    expect(within(progress).getByRole("img", { name: "75% of Introduction to Crop Production completed" })).toBeInTheDocument();
    await userEvent.click(within(progress).getByRole("link", { name: SITE.site_title }));
    expect(go).toHaveBeenCalledWith("/sites/9");

    const shortcuts = screen.getByRole("navigation", { name: "Shortcuts" });
    expect(within(shortcuts).getAllByRole("link").map((a) => a.querySelector(".shortcut-title")?.textContent)).toEqual([
      "My courses",
      "To do",
      "My data",
    ]);
    expect(shortcuts).toHaveTextContent("2 waiting for you");
  });

  it("says plainly when nothing is due and nothing was released", async () => {
    home(base, { ...empty, student: { due: [], overdue: [], feedback: [], progress: [] } });
    expect(await screen.findByText("Nothing is due in the next seven days.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Overdue" })).not.toBeInTheDocument();
    expect(screen.getByText(/No marks or feedback were released/)).toBeInTheDocument();
    expect(screen.getByText("You are not enrolled on a course yet.")).toBeInTheDocument();
  });
});

describe("Home for teaching staff (item 2.09)", () => {
  it("shows work waiting to be marked, sites with nothing new, and students not seen lately", async () => {
    const lecturer = { ...base, name: "Marlon Bacchus", roles: ["lecturer"], persona: "lecturer" as const, title: "Lecturer, AGR101" };
    const go = home(lecturer, lecturerHome);
    const marking = await screen.findByRole("region", { name: "Waiting to be marked" });
    expect(within(marking).getAllByRole("listitem")).toHaveLength(2);
    expect(marking).toHaveTextContent("Waiting since 02/10/2026");
    await userEvent.click(within(marking).getByRole("button", { name: "Open: Logbook entries: 2 to sign off" }));
    expect(go).toHaveBeenCalledWith("/sites/9/logbook");
    const figures = screen.getByRole("region", { name: "Figures" });
    expect(within(figures).getByText("Waiting to be marked").nextSibling).toHaveTextContent("3");

    const quiet = screen.getByRole("region", { name: "Nothing new this week" });
    expect(quiet).toHaveTextContent("Nothing set to open");
    await userEvent.click(within(quiet).getByRole("button", { name: `Add content: ${SITE.site_title}` }));
    expect(go).toHaveBeenCalledWith("/sites/9");

    const absent = screen.getByRole("region", { name: "Not seen in 14 days" });
    expect(absent).toHaveTextContent("Never signed in");
    expect(absent).toHaveTextContent("Tevin Joseph");
    expect(absent).toHaveTextContent("2 more students not seen");
    expect(screen.getByText(/Lecturer, AGR101/)).toBeInTheDocument();
  });
});

describe("Home for course administrators and administrators (item 2.07)", () => {
  it("shows the sites as a whole and leads to To do and Admin", async () => {
    const admin = { ...base, name: "Natasha Khan", roles: ["course_admin"], persona: "course_admin" as const, title: "Course administrator" };
    const go = home(admin, adminHome);
    const figures = await screen.findByRole("region", { name: "Figures" });
    expect(within(figures).getByText("Course sites").nextSibling).toHaveTextContent("12");
    expect(figures).toHaveTextContent("10 published · 2 not yet");
    expect(figures).toHaveTextContent("Sites nobody teaches yet");
    expect(screen.getByRole("region", { name: "Waiting for you" })).toHaveTextContent("4 things wait for you under To do.");
    const shortcuts = screen.getByRole("navigation", { name: "Shortcuts" });
    await userEvent.click(within(shortcuts).getByRole("link", { name: /Admin/ }));
    expect(go).toHaveBeenCalledWith("/admin");
    await userEvent.click(screen.getByRole("link", { name: "All of To do" }));
    expect(go).toHaveBeenCalledWith("/to-do");
  });

  it("shows nothing but shortcuts to an office role with no sites to count", async () => {
    const auditor = { ...base, roles: ["auditor"], persona: "office" as const, title: "Auditor" };
    home(auditor, { ...empty, persona: "office" });
    const shortcuts = await screen.findByRole("navigation", { name: "Shortcuts" });
    expect(within(shortcuts).queryByRole("link", { name: /Admin/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Figures" })).not.toBeInTheDocument();
  });
});

it("says when Home cannot be loaded", async () => {
  home(base, { status: 503, body: { code: "unavailable", detail: "The server is busy." } });
  expect(await screen.findByRole("alert")).toHaveTextContent("The server is busy.");
});
