import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Me, Notification, SearchHits, WaitingItem } from "../api/types";
import { fakeServer } from "../test/fetch";
import { useCrumb } from "./frame";
import { enqueue } from "./offlineQueue";
import { Shell } from "./Shell";

const MRP = { id: 1, code: "MRP", name: "Mon Repos Campus" };
const ESQ = { id: 2, code: "ESQ", name: "Essequibo Campus" };

const admin: Me = {
  id: 6,
  username: "course.admin",
  name: "Natasha Khan",
  roles: ["course_admin"],
  is_superuser: false,
  mfa_required: true,
  mfa_verified: true,
  person_id: 6,
  person_kind: "staff",
  external_id: "E0006",
  persona: "course_admin",
  title: "Course administrator",
};
const student: Me = {
  ...admin,
  id: 1,
  username: "kezia.persaud",
  name: "Kezia Persaud",
  roles: ["student"],
  mfa_required: false,
  person_kind: "student",
  external_id: "S2026901",
  persona: "student",
  title: "Student",
};

const waiting = (n: number): WaitingItem[] =>
  Array.from({ length: n }, (_, i) => ({
    kind: "takedown",
    kind_name: "Takedown request to review",
    title: `Item ${i}`,
    since: "2026-10-01T10:00:00Z",
    due_at: null,
    waited_days: 1,
    overdue: false,
    link: "/sites/9",
    site_title: "AGR101",
  }));
const note: Notification = {
  id: 4,
  kind: "alert",
  title: "Marked: Soil sampling report",
  body: "",
  link: "/sites/9/assignments",
  created_at: "2026-10-02T06:00:00Z",
  read_at: null,
};
const hits: SearchHits = {
  sites: [{ id: 9, title: "Introduction to Crop Production", sub: "AGR101-2026-27-S1-MRP", link: "/sites/9" }],
  content: [],
  assignments: [{ id: 3, title: "Germination trial report", sub: "Introduction to Crop Production · due 12/10/2026", link: "/sites/9/assignments" }],
  quizzes: [],
  people: [{ id: 2, title: "Tevin Joseph", sub: "S2026902 · Student", link: "/sites/9" }],
};

function server(extra: Record<string, unknown> = {}) {
  return fakeServer({
    "GET /to-do/": { body: waiting(3) },
    "GET /notifications/": [{ body: { unread: 1, results: [note] } }, { body: { unread: 0, results: [{ ...note, read_at: "2026-10-03T06:00:00Z" }] } }],
    "POST /notifications/4/read/": { status: 204 },
    "POST /notifications/read-all/": { body: { marked: 1 } },
    "POST /auth/logout/": { status: 204 },
    "GET /reference/campuses/": { body: [MRP, ESQ] },
    ...(extra as Record<string, { body?: unknown; status?: number }>),
  });
}

function onPhone(matches: boolean) {
  vi.stubGlobal("matchMedia", (media: string) => ({
    matches,
    media,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

function Named({ label }: { label: string }) {
  useCrumb(label);
  return <p>The site</p>;
}

function frame(me: Me, over: Partial<Parameters<typeof Shell>[0]> = {}) {
  const props = {
    me,
    path: "/",
    onNavigate: vi.fn(),
    onLogout: vi.fn(),
    campusCode: null,
    onCampusChange: vi.fn(),
    children: <p>Page</p>,
    ...over,
  };
  return { ...render(<Shell {...props} />), props };
}

describe("the frame", () => {
  it("shows the crest's Home link, how much waits in To do, and the role in words, never a code", async () => {
    server();
    const { props } = frame(admin);
    expect(screen.getByRole("link", { name: "GSA LMS Home" })).toHaveAttribute("href", "#/");
    const todo = screen.getByRole("link", { name: /^To do/ });
    expect(await within(todo).findByText("3")).toBeInTheDocument();
    expect(todo).toHaveTextContent("To do 3 waiting");
    await userEvent.setup().click(todo);
    expect(props.onNavigate).toHaveBeenCalledWith("/to-do");
    expect(screen.queryByText(/course_admin/)).not.toBeInTheDocument();
  });

  it("opens the person's menu with their title, their own pages, and Sign out", async () => {
    server();
    const { props } = frame(admin);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Signed in as Natasha Khan" }));
    const menu = screen.getByRole("dialog", { name: "Your account" });
    expect(menu).toHaveTextContent("Course administrator");
    expect(within(menu).getAllByRole("link").map((a) => a.querySelector(".menu-label")?.textContent)).toEqual([
      "My courses",
      "My data",
      "My account",
      "Notification settings",
      "Downloaded",
      "Help",
    ]);
    await user.click(within(menu).getByRole("link", { name: /My data/ }));
    expect(props.onNavigate).toHaveBeenCalledWith("/my-data");
    expect(screen.queryByRole("dialog", { name: "Your account" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Signed in as Natasha Khan" }));
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    // Signing out waits for the server; push is turned off for this device and what was kept is removed first.
    await waitFor(() => expect(props.onLogout).toHaveBeenCalled());
  });

  it("closes a menu with Esc or a click outside it", async () => {
    server();
    frame(admin);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Notifications, 1 unread/ }));
    expect(screen.getByRole("dialog", { name: "Notifications" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Notifications" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Notifications, 1 unread/ }));
    fireEvent.click(document.querySelector(".popover-backdrop")!);
    expect(screen.queryByRole("dialog", { name: "Notifications" })).not.toBeInTheDocument();
  });

  it("follows a notification to where it points, marks it read, and marks everything read at once", async () => {
    const calls = server().calls;
    const { props } = frame(admin);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Notifications, 1 unread/ }));
    await user.click(screen.getByRole("button", { name: "Mark all read" }));
    expect(calls.some((c) => c.path === "/notifications/read-all/")).toBe(true);
    await user.click(await screen.findByRole("button", { name: /Soil sampling report/ }));
    expect(props.onNavigate).toHaveBeenCalledWith("/sites/9/assignments");
  });

  it("offers the campus switch to course administrators, never to a student", async () => {
    server();
    const { props, unmount } = frame(admin, { campusCode: "ESQ" });
    const group = await screen.findByRole("group", { name: "Campus" });
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual(["All campuses", "Mon Repos", "Essequibo"]);
    expect(within(group).getByRole("button", { name: "Essequibo" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.setup().click(within(group).getByRole("button", { name: "All campuses" }));
    expect(props.onCampusChange).toHaveBeenCalledWith(null);
    unmount();
    frame(student);
    expect(screen.queryByRole("group", { name: "Campus" })).not.toBeInTheDocument();
  });

  it("leads back to Home from every page, naming the course site open", () => {
    server();
    const { rerender, props } = frame(student, { path: "/sites/9/gradebook", children: <Named label="Introduction to Crop Production" /> });
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Home",
      "My courses",
      "Introduction to Crop Production",
    ]);
    expect(within(crumbs).getByText("Introduction to Crop Production")).toHaveAttribute("aria-current", "page");
    fireEvent.click(within(crumbs).getByRole("link", { name: "My courses" }));
    expect(props.onNavigate).toHaveBeenCalledWith("/courses");
    rerender(
      <Shell {...props} path="/to-do">
        <p>To do</p>
      </Shell>,
    );
    expect(within(screen.getByRole("navigation", { name: "Breadcrumb" })).getByText("To do")).toHaveAttribute("aria-current", "page");
    rerender(
      <Shell {...props} path="/">
        <p>Home</p>
      </Shell>,
    );
    expect(screen.queryByRole("navigation", { name: "Breadcrumb" })).not.toBeInTheDocument();
  });

  it("says in the header how many writes wait on this device to be sent", () => {
    server();
    enqueue({ kind: "assignment", method: "POST", path: "/assignments/3/submit/", body: { text: "x" }, label: "Answer to Germination trial report" });
    frame(student);
    expect(screen.getByText("1 waiting to send")).toBeInTheDocument();
  });
});

describe("search", () => {
  it("opens with Ctrl K and, before anything is typed, lists the pages this person may open", () => {
    server();
    frame(student);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const dialog = screen.getByRole("dialog", { name: "Search" });
    const box = within(dialog).getByRole("combobox", { name: "Search courses, work and pages" });
    expect(box).toHaveFocus();
    const pages = within(dialog).getByRole("group", { name: "Pages" });
    expect(within(pages).getAllByRole("option").map((o) => o.querySelector(".search-title")?.textContent)).toEqual([
      "To do",
      "My courses",
      "Messages",
      "Calendar",
      "Discussion",
      "My data",
      "My account",
      "Notification settings",
      "Downloaded",
      "Help",
    ]);
  });

  it("finds courses, work and people on the server, moves with the arrow keys and opens with Enter", async () => {
    const calls = server({ "GET /search/": { body: hits } }).calls;
    const { props } = frame(admin);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Search courses, work, people and pages/ }));
    const box = screen.getByRole("combobox");
    await user.type(box, "germ");
    const work = await screen.findByRole("group", { name: "Assignments" });
    expect(within(work).getByRole("option")).toHaveTextContent("Germination trial report");
    expect(screen.getByRole("group", { name: "Courses" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "People" })).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/search/?q=germ")).toBe(true);
    expect(box).toHaveAttribute("aria-activedescendant", "search-option-0");
    await user.keyboard("{ArrowDown}{ArrowDown}{ArrowUp}{Enter}");
    expect(props.onNavigate).toHaveBeenCalledWith("/sites/9/assignments");
    expect(screen.queryByRole("dialog", { name: "Search" })).not.toBeInTheDocument();
  });

  it("says when nothing matches, keeps Tab inside, and closes with Esc back where it was opened", async () => {
    server({ "GET /search/": { body: { sites: [], content: [], assignments: [], quizzes: [], people: [] } } });
    frame(admin);
    const user = userEvent.setup();
    const opener = screen.getByRole("button", { name: /Search courses, work, people and pages/ });
    await user.click(opener);
    await user.type(screen.getByRole("combobox"), "zzzz");
    expect(screen.getByRole("status")).toHaveTextContent("Nothing matches that.");
    expect(screen.getByRole("combobox")).not.toHaveAttribute("aria-activedescendant");
    await user.tab();
    expect(screen.getByRole("combobox")).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Search" })).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("opens a page with a click, keeps going when the server cannot be reached, and closes on a click outside", async () => {
    server({ "GET /search/": { status: 500, body: { detail: "Down" } } });
    const { props } = frame(admin);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Search courses, work, people and pages/ }));
    await user.type(screen.getByRole("combobox"), "my d");
    await user.click(await screen.findByRole("option", { name: /My data/ }));
    expect(props.onNavigate).toHaveBeenCalledWith("/my-data");
    await user.click(screen.getByRole("button", { name: /Search courses, work, people and pages/ }));
    fireEvent.mouseDown(document.querySelector(".search-backdrop")!);
    expect(screen.queryByRole("dialog", { name: "Search" })).not.toBeInTheDocument();
  });
});

describe("on a phone", () => {
  it("puts Home, To do, Search and Me in tabs at the bottom, and the campus switch in Me", async () => {
    onPhone(true);
    server();
    const { props } = frame(admin);
    const tabs = screen.getByRole("navigation", { name: "Main" });
    expect(within(tabs).getAllByRole("link").map((a) => a.textContent)).toEqual(["Home", expect.stringMatching(/^To do/)]);
    expect(within(tabs).getAllByRole("button").map((b) => b.textContent)).toEqual(["Search", "Me"]);
    expect(within(tabs).getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
    const user = userEvent.setup();
    await user.click(within(tabs).getByRole("button", { name: "Me" }));
    const sheet = screen.getByRole("dialog", { name: "Your account" });
    expect(await within(sheet).findByRole("group", { name: "Campus" })).toBeInTheDocument();
    await user.click(within(tabs).getByRole("button", { name: "Me" }));
    expect(screen.queryByRole("dialog", { name: "Your account" })).not.toBeInTheDocument();
    await user.click(within(tabs).getByRole("button", { name: "Search" }));
    const dialog = screen.getByRole("dialog", { name: "Search" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog", { name: "Search" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Search courses, work, people and pages" }));
    expect(screen.getByRole("dialog", { name: "Search" })).toBeInTheDocument();
    await user.click(within(tabs).getByRole("link", { name: /^To do/ }));
    expect(props.onNavigate).toHaveBeenCalledWith("/to-do");
  });

  it("closes what was open when the page changes", async () => {
    onPhone(false);
    server();
    const { rerender, props } = frame(admin);
    await userEvent.setup().click(screen.getByRole("button", { name: "Signed in as Natasha Khan" }));
    expect(screen.getByRole("dialog", { name: "Your account" })).toBeInTheDocument();
    await act(async () => rerender(<Shell {...props} path="/courses" />));
    expect(screen.queryByRole("dialog", { name: "Your account" })).not.toBeInTheDocument();
  });
});
