import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RegisterRow, TotalsRow } from "../../api/types-talk";
import { flush, pending, pendingCount } from "../../app/offlineQueue";
import { fakeServer, offline } from "../../test/fetch";
import { classSession } from "../forums/fixtures";
import { ClassesTab } from "./ClassesTab";
import { checkInOpen } from "./labels";

const register: RegisterRow[] = [
  { person_id: 21, student_no: "S2026901", name: "Kezia Persaud", status: "present", how: "check_in", acted_at: "2026-10-05T09:00:00Z", note: "" },
  { person_id: 22, student_no: "S2026902", name: "Tevin Joseph", status: null, how: null, acted_at: null, note: "" },
];

const totals: TotalsRow[] = [
  { person_id: 21, student_no: "S2026901", name: "Kezia Persaud", sessions: 4, present: 3, late: 0, excused: 1, absent: 0, not_recorded: 0, percent: "100.00" },
];

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

function at(address: string) {
  window.location.hash = address;
}

afterEach(() => {
  window.location.hash = "";
  vi.useRealTimers();
});

describe("classes on a course (item 4.14)", () => {
  it("lists coming and past classes with their meeting links, and the student's own attendance", async () => {
    const past = classSession({ id: 4, title: "Seed sowing practical", starts_at: "2026-09-28T13:00:00Z", ends_at: "2026-09-28T15:00:00Z", my_status: "late", meeting_url: "", recording_url: "https://video.example.org/4" });
    fakeServer({
      "GET /class-sessions/": { body: page([past, classSession()]) },
      "GET /attendance/sites/9/totals/": { body: totals },
    });
    render(<ClassesTab siteId={9} teaching={false} />);
    const coming = await screen.findByRole("list", { name: "Coming classes" });
    expect(within(coming).getByRole("link", { name: "Join online" })).toHaveAttribute("href", "https://meet.example.org/agr101");
    expect(within(coming).getByRole("link", { name: "Check in" })).toHaveAttribute("href", "#/sites/9/classes/5");
    const before = screen.getByRole("list", { name: "Past classes" });
    expect(before).toHaveTextContent("Late");
    expect(within(before).getByRole("link", { name: "Recording" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Your attendance" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Attendance totals" })).toHaveTextContent("100.00%");
    expect(screen.queryByRole("button", { name: "Add a class" })).not.toBeInTheDocument();
  });

  it("lets teaching staff add a class with a meeting link", async () => {
    const { calls } = fakeServer({
      "GET /class-sessions/": { body: page([]) },
      "GET /attendance/sites/9/totals/": { body: [] },
      "GET /attendance/sites/9/policy/": { body: { send_to_srms: false, minimum_percent: null, last_sent_at: null } },
      "GET /groups/": { body: page([{ id: 4, site: 9, name: "Lab group A", members: [] }]) },
      "POST /class-sessions/": [{ status: 400, body: { meeting_url: ["Give a secure web address, starting https://."] } }, { status: 201, body: classSession() }],
    });
    const user = userEvent.setup();
    render(<ClassesTab siteId={9} teaching />);
    expect(await screen.findByText("No classes coming up.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add a class" }));
    await user.type(screen.getByLabelText("Title"), "Irrigation (online)");
    await user.type(screen.getByLabelText("Starts"), "2026-10-12T09:00");
    await user.type(screen.getByLabelText("Ends"), "2026-10-12T10:00");
    await user.type(screen.getByLabelText("Meeting link (https)"), "https://meet.example.org/agr101");
    await user.selectOptions(await screen.findByLabelText("For"), "4");
    await user.click(screen.getByRole("button", { name: "Add class" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("meeting url: Give a secure web address");
    await user.click(screen.getByRole("button", { name: "Add class" }));
    const body = calls.filter((c) => c.method === "POST")[1].body as Record<string, unknown>;
    expect(body).toMatchObject({ site: 9, title: "Irrigation (online)", group: 4, takes_attendance: true, meeting_url: "https://meet.example.org/agr101" });
    expect(String(body.starts_at)).toMatch(/^2026-10-12T/);
  });

  it("knows when check-in is open: from 15 minutes before a class until it ends", () => {
    const s = classSession({ starts_at: "2026-10-05T13:00:00Z", ends_at: "2026-10-05T14:00:00Z" });
    expect(checkInOpen(s, Date.parse("2026-10-05T12:44:00Z"))).toBe(false);
    expect(checkInOpen(s, Date.parse("2026-10-05T12:46:00Z"))).toBe(true);
    expect(checkInOpen(s, Date.parse("2026-10-05T14:01:00Z"))).toBe(false);
    expect(checkInOpen({ ...s, takes_attendance: false }, Date.parse("2026-10-05T13:30:00Z"))).toBe(false);
  });
});

describe("the register on a phone (item 4.15)", () => {
  it("marks the rest present at one tap, keeps it without a connection, and sends it with one key", async () => {
    at("#/sites/9/classes/5");
    const { calls } = fakeServer({
      "GET /class-sessions/5/": { body: classSession() },
      "GET /class-sessions/5/register/": { body: register },
      "POST /class-sessions/5/register/": [offline, { body: { saved: 1, kept: [], register } }],
      "GET /attendance/sites/9/totals/": { body: [] },
      "GET /attendance/sites/9/policy/": { body: { send_to_srms: true, minimum_percent: "75.00", last_sent_at: null } },
    });
    const user = userEvent.setup();
    render(<ClassesTab siteId={9} teaching />);
    expect(await screen.findByRole("link", { name: "Show the check-in code in the room" })).toHaveAttribute("href", "#/sites/9/classes/5/code");
    const rows = await screen.findByRole("list", { name: "Students" });
    expect(within(rows).getAllByRole("listitem")[0]).toHaveTextContent("checked in");
    expect(within(rows).getByRole("radiogroup", { name: "Kezia Persaud" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "No changes to save" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Mark the rest present" }));
    expect(within(screen.getByRole("radiogroup", { name: "Tevin Joseph" })).getByLabelText("Present")).toBeChecked();
    await user.click(within(screen.getByRole("radiogroup", { name: "Tevin Joseph" })).getByLabelText("Late"));
    await user.click(screen.getByRole("button", { name: "Save register (1 change)" }));
    expect(await screen.findByText("Waiting to send. It is sent when the connection returns.")).toBeInTheDocument();
    expect(pendingCount()).toBe(1);
    const key = pending()[0].idempotencyKey;
    expect(pending()[0].body).toMatchObject({ records: [{ student: 22, status: "late" }] });
    await act(async () => {
      await flush();
    });
    expect(await screen.findByText("Sent")).toBeInTheDocument();
    const tries = calls.filter((c) => c.method === "POST");
    expect(tries[1].headers.get("Idempotency-Key")).toBe(key);
  });

  it("opens the register last read on this device when there is no signal", async () => {
    at("#/sites/9/classes/5");
    localStorage.setItem("gsa-lms.register.5", JSON.stringify(register));
    fakeServer({
      "GET /class-sessions/5/": { body: classSession() },
      "GET /class-sessions/5/register/": offline,
      "GET /attendance/sites/9/totals/": { body: [] },
      "GET /attendance/sites/9/policy/": { body: { send_to_srms: false, minimum_percent: null, last_sent_at: null } },
    });
    render(<ClassesTab siteId={9} teaching />);
    expect(await screen.findByText(/No connection: this is the register as last opened on this phone/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Students" })).toHaveTextContent("Tevin Joseph");
  });

  it("saves online, says whose own check-in stood, and closes the register", async () => {
    at("#/sites/9/classes/5");
    fakeServer({
      "GET /class-sessions/5/": { body: classSession() },
      "GET /class-sessions/5/register/": { body: register },
      "POST /class-sessions/5/register/": { body: { saved: 1, kept: [21], register } },
      "POST /class-sessions/5/close-register/": { body: { marked_absent: 1 } },
      "GET /attendance/sites/9/totals/": { body: [] },
      "GET /attendance/sites/9/policy/": { body: { send_to_srms: false, minimum_percent: null, last_sent_at: null } },
    });
    const user = userEvent.setup();
    render(<ClassesTab siteId={9} teaching />);
    await user.click(within(await screen.findByRole("radiogroup", { name: "Tevin Joseph" })).getByLabelText("Absent"));
    await user.click(screen.getByRole("button", { name: "Save register (1 change)" }));
    expect(await screen.findByText(/Register saved: 1 student. 1 student checked in after you took it/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close register: no record means absent" }));
    expect(await screen.findByText("Register closed: 1 student with no record marked absent.")).toBeInTheDocument();
  });
});

describe("check-in with the code in the room (item 4.15)", () => {
  it("shows the six-character code large, and asks for the next one as the minute turns", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    at("#/sites/9/classes/5/code");
    const { calls } = fakeServer({
      "GET /class-sessions/5/": { body: classSession() },
      "GET /class-sessions/5/check-in-code/": [
        { body: { code: "x-1", valid_seconds: 60, expires_at: "", short_code: "K7M2QX", refresh_seconds: 20 } },
        { body: { code: "x-2", valid_seconds: 60, expires_at: "", short_code: "P4WZ9H", refresh_seconds: 60 } },
      ],
    });
    render(<ClassesTab siteId={9} teaching />);
    expect(await screen.findByText("K7M2QX")).toBeInTheDocument();
    expect(screen.getByText("Code: K 7 M 2 Q X")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the register" })).toHaveAttribute("href", "#/sites/9/classes/5");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(21_000);
    });
    expect(await screen.findByText("P4WZ9H")).toBeInTheDocument();
    expect(calls.filter((c) => c.path === "/class-sessions/5/check-in-code/")).toHaveLength(2);
  });

  it("says why no code can be shown", async () => {
    at("#/sites/9/classes/5/code");
    fakeServer({
      "GET /class-sessions/5/": { body: classSession() },
      "GET /class-sessions/5/check-in-code/": { status: 409, body: { code: "check_in_closed", detail: "Check-in is open from 15 minutes before the class until it ends." } },
    });
    render(<ClassesTab siteId={9} teaching />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Check-in is open from 15 minutes before");
  });

  it("lets a student type the code, and shows the server's answer when it is wrong", async () => {
    at("#/sites/9/classes/5");
    const { calls } = fakeServer({
      "GET /class-sessions/5/": [{ body: classSession() }, { body: classSession({ my_status: "present" }) }],
      "POST /class-sessions/5/check-in/": [
        { status: 400, body: { code: "code_invalid", detail: "That is not the code for this class. Check the screen and try again." } },
        { status: 201, body: { session: 5, status: "present" } },
      ],
    });
    const user = userEvent.setup();
    render(<ClassesTab siteId={9} teaching={false} />);
    const box = await screen.findByLabelText("Code on the screen");
    await user.type(box, "k7m2qa");
    expect(box).toHaveValue("K7M2QA");
    await user.click(screen.getByRole("button", { name: "Check in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That is not the code for this class.");
    await user.clear(box);
    await user.type(box, "K7M2QX");
    await user.click(screen.getByRole("button", { name: "Check in" }));
    expect(await screen.findByText("Your attendance: present.")).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST")[1].body).toEqual({ code: "K7M2QX" });
  });

  it("tells a student when check-in is not open", async () => {
    at("#/sites/9/classes/5");
    fakeServer({ "GET /class-sessions/5/": { body: classSession({ starts_at: "2030-01-01T09:00:00Z", ends_at: "2030-01-01T10:00:00Z" }) } });
    render(<ClassesTab siteId={9} teaching={false} />);
    expect(await screen.findByText("Check-in opens 15 minutes before the class and closes when it ends.")).toBeInTheDocument();
  });
});

describe("totals and the SRMS (item 4.15)", () => {
  function server(answer: { status?: number; body?: unknown }) {
    return fakeServer({
      "GET /class-sessions/": { body: page([]) },
      "GET /attendance/sites/9/totals/": { body: totals },
      "GET /attendance/sites/9/policy/": { body: { send_to_srms: true, minimum_percent: "75.00", last_sent_at: "2026-10-01T12:00:00Z" } },
      "POST /attendance/sites/9/send-to-srms/": answer,
    });
  }

  it("sends the totals and says what the SRMS took", async () => {
    server({ body: { offering_code: "AGR101", accepted: ["S2026901"], locked: ["S2026903"], unknown: ["S2026999"] } });
    const user = userEvent.setup();
    render(<ClassesTab siteId={9} teaching />);
    expect(await screen.findByText(/makes attendance a condition \(at least 75.00%\)/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send to the SRMS" }));
    expect(await screen.findByRole("status")).toHaveTextContent("The SRMS took 1 student's total; 1 locked there; 1 not known to it: S2026999.");
  });

  it("shows the server's message plainly when the SRMS cannot be reached", async () => {
    server({ status: 502, body: { code: "srms_unavailable", detail: "The SRMS could not take the totals now. Try again later." } });
    const user = userEvent.setup();
    render(<ClassesTab siteId={9} teaching />);
    await user.click(await screen.findByRole("button", { name: "Send to the SRMS" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The SRMS could not take the totals now. Try again later.");
  });

  it("says when nothing was sent because the programme does not need it", async () => {
    server({ body: { offering_code: "AGR101", skipped: "attendance is not a condition of this programme" } });
    const user = userEvent.setup();
    render(<ClassesTab siteId={9} teaching />);
    await user.click(await screen.findByRole("button", { name: "Send to the SRMS" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing was sent: attendance is not a condition of this programme");
  });
});
