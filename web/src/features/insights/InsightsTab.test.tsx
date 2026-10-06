import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { fakeServer } from "../../test/fetch";
import { alert, analytics, progress, rules, studentProgress } from "../../test/insights";
import { InsightsTab } from "./InsightsTab";

function open(at: string, routes: Parameters<typeof fakeServer>[0] = {}) {
  window.location.hash = at;
  const server = fakeServer({
    "GET /sites/9/insights/": { body: analytics },
    "GET /sites/9/progress/": { body: progress },
    "GET /sites/9/progress/101/": { body: studentProgress },
    "GET /sites/9/alerts/": { body: [alert()] },
    "GET /alert-rules/": { body: rules },
    ...routes,
  });
  render(<InsightsTab siteId={9} />);
  return server;
}

afterEach(() => {
  window.location.hash = "";
});

describe("the Insights tab (items 6.01, 6.02, 6.05)", () => {
  it("shows how the class uses the course, with the quiz statistics linked and nothing about time on a page", async () => {
    open("#/sites/9/insights");
    const items = await screen.findByRole("region", { name: "Content" });
    expect(within(items).getAllByRole("row")[1]).toHaveTextContent("Soil horizonsWeek 11 of 2 (50%)–");
    expect(within(items).getAllByRole("row")[2]).toHaveTextContent("Field handout (draft)");
    const work = screen.getByRole("region", { name: "Assignments" });
    expect(within(work).getAllByRole("row")[1]).toHaveTextContent("Soil profile report01/10/20261 of 2111 (0 released)80%80% to 80%");
    expect(screen.getByRole("link", { name: "Question statistics" })).toHaveAttribute("href", "#/sites/9/quizzes/7/statistics");
    expect(screen.getByText(/Time spent on a page is not recorded/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Course use" })).toHaveAttribute("aria-current", "page");
  });

  it("moves between its parts by address", async () => {
    open("#/sites/9/insights");
    const user = userEvent.setup();
    await screen.findByRole("region", { name: "Content" });
    await user.click(screen.getByRole("link", { name: "Progress" }));
    expect(window.location.hash).toBe("#/sites/9/insights/progress");
    expect(await screen.findByRole("region", { name: "Progress of each student" })).toBeInTheDocument();
  });

  it("lists every student's progress and opens one student's work and outcomes", async () => {
    open("#/sites/9/insights/progress");
    const table = await screen.findByRole("region", { name: "Progress of each student" });
    const [, ria, andre] = within(table).getAllByRole("row");
    expect(ria).toHaveTextContent("S2026911 Ria Ramdial1 alert3 of 42161.5%04/10/202605/10/2026");
    expect(andre).toHaveTextContent("None recordedNot yet");
    const user = userEvent.setup();
    await user.click(within(ria).getByRole("button", { name: "S2026911 Ria Ramdial" }));
    const panel = await screen.findByRole("region", { name: "Progress of Ria Ramdial" });
    expect(within(panel).getByRole("list", { name: "Work" })).toHaveTextContent("Soil profile reportAssignment · due 01/10/2026Counted · 70%");
    expect(within(panel).getByText("Missing, counted as 0")).toBeInTheDocument();
    expect(within(panel).getByRole("list", { name: "Learning outcomes" })).toHaveTextContent("LO1 Describe a soil profileMet (70%)");
    await user.click(within(panel).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("region", { name: "Progress of Ria Ramdial" })).not.toBeInTheDocument();
  });
});

describe("early alerts (item 6.05)", () => {
  it("shows each alert's evidence and the rules, and marks one as seen", async () => {
    const { calls } = open("#/sites/9/insights/alerts", {
      "POST /alerts/70/acknowledge/": { body: alert({ state: "acknowledged", state_label: "Seen" }) },
    });
    const list = await screen.findByRole("list", { name: "Early alerts" });
    expect(within(list).getByRole("list", { name: "Evidence for Ria Ramdial" })).toHaveTextContent(
      "Soil profile report: nothing handed in by the due date · 01/10/2026",
    );
    expect(screen.getByText(/2 or more pieces of work missed/)).toBeInTheDocument();
    expect(screen.getByText("(switched off)")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Mark as seen" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/alerts/70/acknowledge/")).toBe(true));
  });

  it("dismisses an alert only with a reason", async () => {
    const { calls } = open("#/sites/9/insights/alerts", { "POST /alerts/70/dismiss/": { body: alert({ state: "dismissed" }) } });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Dismiss" }));
    const reason = screen.getByRole("textbox", { name: "Why nothing needs doing" });
    const button = screen.getByRole("button", { name: "Dismiss" });
    expect(button).toBeDisabled();
    await user.type(reason, "Excused: in hospital");
    await user.click(button);
    await waitFor(() => expect(calls.find((c) => c.path === "/alerts/70/dismiss/")?.body).toEqual({ reason: "Excused: in hospital" }));
  });

  it("writes to the student in Messages and records it with the alert", async () => {
    const { calls } = open("#/sites/9/insights/alerts", {
      "POST /conversations/": { status: 201, body: { id: 300 } },
      "POST /alerts/70/act/": { body: alert({ state: "acted" }) },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Write to the student" }));
    const form = screen.getByRole("form", { name: "Write to Ria Ramdial" });
    await user.type(within(form).getByRole("textbox", { name: "Message" }), "Can we talk about the report?");
    await user.click(within(form).getByRole("button", { name: "Send and record" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/alerts/70/act/")).toBe(true));
    expect(calls.find((c) => c.path === "/conversations/")?.body).toEqual({
      site: 9,
      audience: "direct",
      subject: "Checking in about your course work",
      body: "Can we talk about the report?",
      body_format: "text",
      recipients: [101],
    });
    expect(calls.find((c) => c.path === "/alerts/70/act/")?.body).toEqual({
      note: "Wrote to the student in Messages: Checking in about your course work",
      conversation: 300,
    });
  });

  it("records what was done, says why a write failed, and shows handled alerts when asked", async () => {
    const handled = alert({ id: 71, state: "acted", state_label: "Acted on", handled_by_name: "Asha Persaud", handled_at: "2026-10-05T09:00:00Z", note: "Phoned" });
    const { calls } = open("#/sites/9/insights/alerts", {
      "POST /alerts/70/act/": [{ status: 409, body: { code: "already_handled", detail: "This alert was already acted on." } }],
      "GET /sites/9/alerts/?state=all": { body: [handled] },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Record what was done" }));
    await user.type(screen.getByRole("textbox", { name: "What was done" }), "Spoke after class");
    await user.click(screen.getByRole("button", { name: "Record" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This alert was already acted on.");
    expect(calls.find((c) => c.path === "/alerts/70/act/")?.body).toEqual({ note: "Spoke after class" });
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("checkbox", { name: "Show alerts already dealt with" }));
    expect(await screen.findByText(/acted on by Asha Persaud, 05\/10\/2026 · Phoned/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dismiss" })).not.toBeInTheDocument();
  });

  it("says when there are no alerts, and when they cannot be loaded", async () => {
    open("#/sites/9/insights/alerts", { "GET /sites/9/alerts/": { body: [] }, "GET /alert-rules/": { status: 403, body: { code: "permission_denied", detail: "No." } } });
    expect(await screen.findByText("No alerts waiting.")).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("No.");
  });
});
