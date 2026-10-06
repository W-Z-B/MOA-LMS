import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CalendarEvent } from "../../api/types-talk";
import { fakeServer } from "../../test/fetch";
import { CalendarScreen } from "./CalendarScreen";

/** A moment some days from now, at 14:00 in the device's time. */
function soon(days: number, hour = 14): string {
  const at = new Date();
  at.setDate(at.getDate() + days);
  at.setHours(hour, 0, 0, 0);
  return at.toISOString();
}

const event = (over: Partial<CalendarEvent>): CalendarEvent => ({
  kind: "assignment_due",
  id: 3,
  site: 9,
  site_code: "AGR101-2026-27-S1-MRP",
  title: "Due: Field notebook check",
  starts_at: soon(3),
  ends_at: null,
  location: "",
  meeting_url: "",
  link: "/sites/9/assignments/3",
  ...over,
});

const events = [
  event({}),
  event({ kind: "class_session", id: 5, title: "Soil science lecture", starts_at: soon(1, 9), ends_at: soon(1, 10), location: "Room 4", meeting_url: "https://meet.example.org/x", link: "/sites/9/classes/5" }),
  event({ kind: "quiz_closes", id: 8, site: 10, site_code: "AGR205", title: "Quiz closes: Soils", starts_at: soon(1, 12), link: "/sites/10/quizzes/8" }),
];

function phone(on: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: on, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("the calendar (item 2.32)", () => {
  it("opens as an agenda on a phone, day by day, and opens each item where it is", async () => {
    phone(true);
    const { calls } = fakeServer({ "GET /calendar/": { body: events }, "GET /calendar/feed/": { body: { url: null, created_at: null, last_used_at: null } } });
    const go = vi.fn();
    const user = userEvent.setup();
    render(<CalendarScreen onNavigate={go} />);
    expect(screen.getByRole("button", { name: "Agenda" })).toHaveAttribute("aria-pressed", "true");
    const due = await screen.findByRole("link", { name: "Due: Field notebook check" });
    const day = due.closest("section")!;
    expect(within(day).getByRole("heading")).toHaveTextContent(/^\w+day \d+ \w+ \d{4}$/);
    expect(screen.getByRole("link", { name: "Join online" })).toHaveAttribute("href", "https://meet.example.org/x");
    expect(screen.getByText(/Class · AGR101-2026-27-S1-MRP · Room 4/)).toBeInTheDocument();
    await user.click(due);
    expect(go).toHaveBeenCalledWith("/sites/9/assignments/3");
    expect(calls.find((c) => c.path.startsWith("/calendar/?"))?.path).toMatch(/^\/calendar\/\?from=.+&to=.+/);

    // Filtered by course.
    await user.selectOptions(screen.getByLabelText("Course"), "AGR205");
    expect(screen.queryByRole("link", { name: "Due: Field notebook check" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Quiz closes: Soils" })).toBeInTheDocument();

    // Later moves on four weeks.
    await user.click(screen.getByRole("button", { name: "Later" }));
    expect(calls.filter((c) => c.path.startsWith("/calendar/?")).length).toBe(2);
  });

  it("shows a month on a wider screen, and a day's items when the day is chosen", async () => {
    phone(false);
    fakeServer({ "GET /calendar/": { body: events }, "GET /calendar/feed/": { body: { url: null, created_at: null, last_used_at: null } } });
    const user = userEvent.setup();
    render(<CalendarScreen onNavigate={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Month" })).toHaveAttribute("aria-pressed", "true");
    const grid = await screen.findByRole("grid");
    expect(within(grid).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]);
    const due = new Date(events[0].starts_at);
    const cell = within(grid)
      .getAllByRole("button")
      .find((b) => b.getAttribute("aria-label")?.includes(` ${due.getDate()} `) && b.closest(".month-cell:not(.other)"));
    if (due.getMonth() === new Date().getMonth()) {
      expect(cell).toHaveAccessibleName(/1 on the calendar|2 on the calendar|3 on the calendar/);
      await user.click(cell!);
      expect(screen.getByRole("link", { name: "Due: Field notebook check" })).toBeInTheDocument();
    }
    await user.click(screen.getByRole("button", { name: "Next month" }));
    await user.click(screen.getByRole("button", { name: "Today" }));
    await user.click(screen.getByRole("button", { name: "Agenda" }));
    expect(await screen.findByRole("link", { name: "Due: Field notebook check" })).toBeInTheDocument();
  });

  it("says when the calendar cannot be read", async () => {
    phone(true);
    fakeServer({ "GET /calendar/": { status: 400, body: { code: "bad_period", detail: "Choose an end after the start, at most 400 days later." } }, "GET /calendar/feed/": { body: { url: null } } });
    render(<CalendarScreen onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose an end after the start");
  });
});

describe("the private calendar feed (item 2.32)", () => {
  const url = "https://lms.example/api/v1/calendar/feed/abc.ics";

  it("makes the address, copies it, makes a new one, and turns it off", async () => {
    phone(true);
    const { calls } = fakeServer({
      "GET /calendar/": { body: [] },
      "GET /calendar/feed/": { body: { url: null, created_at: null, last_used_at: null } },
      "POST /calendar/feed/": [
        { status: 201, body: { url, created_at: "2026-10-05T10:00:00Z", last_used_at: null } },
        { status: 201, body: { url: url.replace("abc", "def"), created_at: "2026-10-05T11:00:00Z", last_used_at: null } },
      ],
      "DELETE /calendar/feed/": { status: 204 },
    });
    const user = userEvent.setup();
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<CalendarScreen onNavigate={vi.fn()} />);
    expect(await screen.findByText("Nothing on your calendar for these four weeks.")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Make my private address" }));
    expect(await screen.findByLabelText("Your private address")).toHaveValue(url);
    expect(screen.getByText(/not read by a calendar yet/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Copy address" }));
    expect(writeText).toHaveBeenCalledWith(url);
    expect(await screen.findByText(/Copied/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Make a new address" }));
    await user.click(screen.getByRole("button", { name: "Make it: the old address stops working" }));
    expect(await screen.findByText(/The old one has stopped working/)).toBeInTheDocument();
    expect(screen.getByLabelText("Your private address")).toHaveValue(url.replace("abc", "def"));

    await user.click(screen.getByRole("button", { name: "Turn off" }));
    expect(await screen.findByText(/Your calendar feed is off/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "DELETE")).toBe(true);
    expect(screen.getByRole("button", { name: "Make my private address" })).toBeInTheDocument();
  });

  it("selects the address for copying by hand where there is no clipboard", async () => {
    phone(true);
    fakeServer({ "GET /calendar/": { body: [] }, "GET /calendar/feed/": { body: { url, created_at: "2026-10-05T10:00:00Z", last_used_at: "2026-10-05T12:00:00Z" } } });
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    render(<CalendarScreen onNavigate={vi.fn()} />);
    const field = (await screen.findByLabelText("Your private address")) as HTMLInputElement;
    expect(screen.getByText(/last read by a calendar/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Copy address" }));
    expect(await screen.findByText(/The address is selected/)).toBeInTheDocument();
    expect(document.activeElement).toBe(field);
    expect(field.selectionEnd! - field.selectionStart!).toBe(url.length);
  });
});
