import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Me } from "../../api/types";
import type { HelpRequest } from "../../api/types-help";
import { FrameContext } from "../../app/frame";
import { helpLink, helpTopic } from "../../app/help";
import { flush, pending, pendingCount } from "../../app/offlineQueue";
import { helpAddress } from "../../app/router";
import { SearchPalette } from "../../app/SearchPalette";
import { fakeServer, offline } from "../../test/fetch";
import HelpScreen from "./HelpScreen";
import { HELP_ROLES, ownRole, roleById, searchAll, searchHelp, taskForTopic } from "./topics";

const student: Me = {
  id: 1,
  username: "kezia.persaud",
  name: "Kezia Persaud",
  roles: ["student"],
  is_superuser: false,
  mfa_required: false,
  mfa_verified: false,
  person_id: 1,
  person_kind: "student",
  external_id: "S2026901",
  persona: "student",
  title: "Student",
};
const lecturer: Me = { ...student, id: 2, name: "Asha Persaud", roles: ["lecturer"], person_kind: "staff", persona: "lecturer", title: "Lecturer" };
const courseAdmin: Me = { ...student, id: 6, name: "Natasha Khan", roles: ["course_admin"], person_kind: "staff", persona: "course_admin" };

function framed(node: ReactNode) {
  const decided = vi.fn();
  const setCrumb = vi.fn();
  render(<FrameContext.Provider value={{ setCrumb, decided }}>{node}</FrameContext.Provider>);
  return { decided, setCrumb };
}

const request = (over: Partial<HelpRequest> = {}): HelpRequest => ({
  id: 12,
  subject: "Cannot find my quiz",
  message: "The quiz is not on the Quizzes tab.",
  page: "/sites/4/quizzes",
  status: "open",
  asked_by_name: "Kezia Persaud",
  created_at: "2026-10-05T13:00:00Z",
  client_sent_at: null,
  answer: "",
  answered_by_name: null,
  answered_at: null,
  mine: false,
  ...over,
});

describe("help addresses and topics (item 7.17)", () => {
  it("reads every help address", () => {
    expect(helpAddress("/help")).toEqual({ view: "index" });
    expect(helpAddress("/help/student")).toEqual({ view: "role", role: "student", task: null });
    expect(helpAddress("/help/student/hand-in")).toEqual({ view: "role", role: "student", task: "hand-in" });
    expect(helpAddress("/help?topic=quizzes&from=%2Fsites%2F4%2Fquizzes")).toEqual({ view: "topic", topic: "quizzes", from: "/sites/4/quizzes" });
    expect(helpAddress("/help/ask?from=%2Fsites%2F4")).toEqual({ view: "ask", from: "/sites/4" });
    expect(helpAddress("/help/requests")).toEqual({ view: "requests", id: null });
    expect(helpAddress("/help/requests/12")).toEqual({ view: "requests", id: 12 });
    expect(helpAddress("/helpdesk")).toBeNull();
    expect(helpAddress("/sites/4")).toBeNull();
  });

  it("gives each page the topic of its help", () => {
    expect(helpTopic("/sites/4/assignments/12/marking/55")).toBe("marking");
    expect(helpTopic("/sites/4/quizzes/12")).toBe("quizzes");
    expect(helpTopic("/sites/4/discussion")).toBe("forums");
    expect(helpTopic("/sites/4/pages/9/edit")).toBe("pages");
    expect(helpTopic("/sites/4")).toBe("content");
    expect(helpTopic("/admin/takedowns")).toBe("course-admin");
    expect(helpTopic("/admin/audit")).toBe("admin");
    expect(helpTopic("/staff-development/requests/3")).toBe("learning");
    expect(helpTopic("/")).toBe("home");
    expect(helpLink("/sites/4/logbook?x=1")).toBe("/help?topic=logbook&from=%2Fsites%2F4%2Flogbook%3Fx%3D1");
  });

  it("has a page for each role, every task with steps and an address of its own, and a task for every topic", () => {
    expect(HELP_ROLES.map((r) => r.id)).toEqual(["student", "lecturer", "head-of-department", "course-administrator", "administrator", "auditor"]);
    for (const role of HELP_ROLES) {
      const ids = role.sections.flatMap((s) => s.tasks.map((t) => t.id));
      expect(new Set(ids).size).toBe(ids.length);
      expect(role.sections.flatMap((s) => s.tasks).every((t) => t.steps.length > 0)).toBe(true);
    }
    const topics = ["marking", "rubrics", "setup", "pages", "assignments", "gradebook", "quizzes", "announcements", "classes", "groups", "practicals", "logbook", "forums", "content", "courses", "todo", "messages", "calendar", "account", "my-data", "notification-settings", "home", "help"];
    for (const topic of topics) expect(taskForTopic(lecturer, topic), topic).not.toBeNull();
    for (const topic of ["accommodations", "course-admin", "admin", "learning"]) expect(taskForTopic(courseAdmin, topic), topic).not.toBeNull();
    expect(ownRole(student).id).toBe("student");
    expect(ownRole({ ...lecturer, persona: "office" }).id).toBe("auditor");
    expect(ownRole({ ...student, persona: undefined, person_kind: "staff" }).id).toBe("lecturer");
    // A student's topic is never answered from the staff's help.
    expect(taskForTopic(student, "marking")).toBeNull();
    expect(roleById("nobody")).toBeUndefined();
  });

  it("searches the reader's own help, and teaching staff the heads of department's too", () => {
    expect(searchHelp(student, "hand in").map((h) => h.to)).toContain("/help/student/hand-in");
    expect(searchHelp(student, "moderation")).toEqual([]);
    expect(searchHelp(lecturer, "stand-in").map((h) => h.to)).toContain("/help/head-of-department/stand-in");
    expect(searchHelp(student, "   ")).toEqual([]);
    expect(searchAll("breach").length).toBeGreaterThan(0);
  });
});

describe("the help pages", () => {
  it("lists every role's help with the reader's own first, and searches it", async () => {
    framed(<HelpScreen me={student} view={{ view: "index" }} onNavigate={vi.fn()} />);
    const cards = screen.getAllByRole("heading", { level: 2 });
    expect(cards[0]).toHaveTextContent("Students (your help)");
    expect(cards).toHaveLength(6);
    await userEvent.type(screen.getByLabelText("Search the help"), "logbook");
    const found = screen.getByRole("region", { name: "Help found" });
    expect(within(found).getByRole("link", { name: "Write a logbook entry" })).toHaveAttribute("href", "#/help/student/logbook");
    await userEvent.clear(screen.getByLabelText("Search the help"));
    await userEvent.type(screen.getByLabelText("Search the help"), "zzzz");
    expect(screen.getByText(/No help matches that/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "My help requests" })).toHaveAttribute("href", "#/help/requests");
  });

  it("shows a role's tasks as numbered steps with the screen's words in bold, and opens at a task", () => {
    const { setCrumb } = framed(<HelpScreen me={lecturer} view={{ view: "role", role: "student", task: "hand-in" }} onNavigate={vi.fn()} />);
    expect(setCrumb).toHaveBeenCalledWith("Students");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Help for students");
    const heading = screen.getByRole("heading", { name: "Hand in an assignment" });
    expect(heading).toHaveFocus();
    const task = heading.closest("article")!;
    expect(task).toHaveClass("focus");
    expect(within(task).getAllByRole("listitem").length).toBeGreaterThan(3);
    expect(within(task).getAllByText("Hand in", { selector: "strong" }).length).toBeGreaterThan(0);
    const contents = screen.getByRole("navigation", { name: "On this page" });
    expect(within(contents).getByRole("link", { name: "Take a quiz" })).toHaveAttribute("href", "#/help/student/take-quiz");
  });

  it("opens the reader's own help at the topic of the page they came from, and asks for help from there", async () => {
    const onNavigate = vi.fn();
    framed(<HelpScreen me={lecturer} view={{ view: "topic", topic: "classes", from: "/sites/4/classes" }} onNavigate={onNavigate} />);
    expect(screen.getByRole("heading", { name: "Add a class and take the register" })).toHaveFocus();
    await userEvent.click(screen.getAllByRole("link", { name: "Ask for help" })[0]);
    expect(onNavigate).toHaveBeenCalledWith("/help/ask?from=%2Fsites%2F4%2Fclasses");
  });

  it("opens the reader's own page when their help has nothing on the topic, and says when a page does not exist", () => {
    framed(<HelpScreen me={student} view={{ view: "topic", topic: "marking", from: "/" }} onNavigate={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Help for students");
    framed(<HelpScreen me={student} view={{ view: "role", role: "nobody", task: null }} onNavigate={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("There is no help page at this address.");
  });
});

describe("asking for help", () => {
  it("sends the question with the page the person was on", async () => {
    const { calls } = fakeServer({ "POST /help-requests/": { status: 201, body: request({ mine: true }) } });
    const onNavigate = vi.fn();
    framed(<HelpScreen me={student} view={{ view: "ask", from: "/sites/4/quizzes" }} onNavigate={onNavigate} />);
    await userEvent.type(screen.getByLabelText("What do you need help with?"), "Cannot find my quiz");
    await userEvent.type(screen.getByLabelText("What were you trying to do, and what happened?"), "It is not there.");
    expect(screen.getByLabelText(/Send the page I was on/)).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Send to the course administrators" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Sent. The course administrators have your request");
    const sent = calls.find((c) => c.method === "POST");
    expect(sent?.body).toMatchObject({ subject: "Cannot find my quiz", message: "It is not there.", page: "/sites/4/quizzes" });
    expect(sent?.headers.get("Idempotency-Key")).toBeTruthy();
    await userEvent.click(screen.getByRole("link", { name: "Back to the page I was on" }));
    expect(onNavigate).toHaveBeenCalledWith("/sites/4/quizzes");
  });

  it("leaves the page out when asked to, and shows a refusal", async () => {
    const { calls } = fakeServer({
      "POST /help-requests/": { status: 429, body: { code: "too_many_help_requests", detail: "You have sent 5 help requests in the last hour." } },
    });
    framed(<HelpScreen me={student} view={{ view: "ask", from: "/sites/4" }} onNavigate={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("What do you need help with?"), "Password");
    await userEvent.type(screen.getByLabelText("What were you trying to do, and what happened?"), "Locked out.");
    await userEvent.click(screen.getByLabelText(/Send the page I was on/));
    await userEvent.click(screen.getByRole("button", { name: "Send to the course administrators" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You have sent 5 help requests in the last hour.");
    expect(calls[0].body).toMatchObject({ page: "" });
  });

  it("keeps the question on the phone without signal and sends it once when the signal returns", async () => {
    const { calls } = fakeServer({ "POST /help-requests/": [offline, { status: 201, body: request() }] });
    framed(<HelpScreen me={student} view={{ view: "ask", from: "/help" }} onNavigate={vi.fn()} />);
    expect(screen.queryByLabelText(/Send the page I was on/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("What do you need help with?"), { target: { value: "No signal" } });
    fireEvent.change(screen.getByLabelText("What were you trying to do, and what happened?"), { target: { value: "On the farm." } });
    await userEvent.click(screen.getByRole("button", { name: "Send to the course administrators" }));
    expect(await screen.findByText("Waiting to send. It is sent when the connection returns.")).toBeInTheDocument();
    expect(pendingCount()).toBe(1);
    const key = pending()[0].idempotencyKey;
    await flush();
    expect(await screen.findByText("Sent")).toBeInTheDocument();
    const tries = calls.filter((c) => c.method === "POST");
    expect(tries).toHaveLength(2);
    expect(tries[1].headers.get("Idempotency-Key")).toBe(key);
  });
});

describe("help requests", () => {
  it("lets a course administrator read a request, open its page and answer it", async () => {
    const { calls } = fakeServer({
      "GET /help-requests/?status=open": [{ body: [request()] }, { body: [] }],
      "GET /help-requests/?status=answered": { body: [request({ status: "answered", answer: "It opens on Monday.", answered_by_name: "Natasha Khan", answered_at: "2026-10-05T14:00:00Z" })] },
      "POST /help-requests/12/answer/": { body: request({ status: "answered" }) },
    });
    const { decided, setCrumb } = framed(<HelpScreen me={courseAdmin} view={{ view: "requests", id: 12 }} onNavigate={vi.fn()} />);
    expect(setCrumb).toHaveBeenCalledWith("Help requests");
    const card = (await screen.findByRole("heading", { name: "Cannot find my quiz" })).closest("li")!;
    expect(card).toHaveClass("focus");
    expect(within(card).getByText(/From Kezia Persaud/)).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Open the page they were on" })).toHaveAttribute("href", "#/sites/4/quizzes");
    const send = within(card).getByRole("button", { name: "Send the answer" });
    expect(send).toBeDisabled();
    await userEvent.type(within(card).getByLabelText("Your answer"), "It opens on Monday.");
    await userEvent.click(send);
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ answer: "It opens on Monday." });
    expect(await screen.findByText("No help request is waiting for an answer.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Your answer to “Cannot find my quiz” is sent.");
    expect(decided).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Answered" }));
    expect(await screen.findByText(/Answered by Natasha Khan/)).toBeInTheDocument();
  });

  it("shows a refused answer", async () => {
    fakeServer({
      "GET /help-requests/?status=open": { body: [request()] },
      "POST /help-requests/12/answer/": { status: 409, body: { code: "already_answered", detail: "Marlon Bacchus has already answered this request." } },
    });
    framed(<HelpScreen me={courseAdmin} view={{ view: "requests", id: null }} onNavigate={vi.fn()} />);
    await userEvent.type(await screen.findByLabelText("Your answer"), "Done");
    await userEvent.click(screen.getByRole("button", { name: "Send the answer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("has already answered");
  });

  it("shows other people their own requests and the answers, with nothing to answer", async () => {
    fakeServer({
      "GET /help-requests/?mine=1": {
        body: [request({ mine: true, status: "answered", answer: "Try again now.", answered_by_name: null, answered_at: null }), request({ id: 13, mine: true, page: "" })],
      },
    });
    const onNavigate = vi.fn();
    framed(<HelpScreen me={student} view={{ view: "requests", id: null }} onNavigate={onNavigate} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("My help requests");
    expect(screen.queryByRole("group", { name: "Show" })).not.toBeInTheDocument();
    expect(await screen.findByText("Try again now.")).toBeInTheDocument();
    expect(screen.getByText(/Answered by a course administrator/)).toBeInTheDocument();
    expect(screen.getAllByText(/You asked/)).toHaveLength(2);
    expect(screen.queryByLabelText("Your answer")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the page I was on" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Ask for help" }));
    expect(onNavigate).toHaveBeenCalledWith("/help/ask");
  });

  it("says when the requests cannot be read", async () => {
    fakeServer({ "GET /help-requests/?mine=1": { status: 500, body: { detail: "Server error" } } });
    framed(<HelpScreen me={student} view={{ view: "requests", id: null }} onNavigate={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Server error");
  });
});

describe("help in search", () => {
  it("finds the reader's help as well as pages", async () => {
    fakeServer({ "GET /search/": { body: { sites: [], content: [], assignments: [], quizzes: [], people: [] } } });
    const onGo = vi.fn();
    render(<SearchPalette me={student} phone={false} onGo={onGo} onClose={vi.fn()} />);
    await userEvent.type(screen.getByRole("combobox"), "hand in");
    const group = await screen.findByRole("group", { name: "Help" });
    const option = within(group).getByRole("option", { name: /Hand in an assignment/ });
    await userEvent.click(option);
    expect(onGo).toHaveBeenCalledWith("/help/student/hand-in");
    await waitFor(() => expect(within(group).getAllByRole("option").length).toBeGreaterThan(0));
  });
});
