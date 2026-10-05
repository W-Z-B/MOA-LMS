import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AssignmentDetail } from "../../api/types-marking";
import { flush, pendingCount } from "../../app/offlineQueue";
import { fakeServer, offline } from "../../test/fetch";
import { assignment, page, released, rubric, submission } from "../../test/marking";
import { AssignmentsTab } from "./AssignmentsTab";

// A student's view: due in a week, nothing handed in yet.
const open = assignment({ due_at: "2099-10-08T14:00:00Z", my_due_at: "2099-10-08T14:00:00Z", submissions_count: null });
const mine = submission({ id: 21, due_at: "2099-10-08T14:00:00Z", is_late: false, accommodation_applies: null });

function show(rows: AssignmentDetail[], teaching: boolean, routes: Record<string, unknown> = {}) {
  const server = fakeServer({
    "GET /assignments/": page(rows),
    "GET /grade-categories/": page([{ id: 5, site: 9, name: "Reports", weight: "60.00", drop_lowest: 0, position: 1 }]),
    "GET /rubrics/": page([rubric]),
    "GET /sites/9/my-groups/": { body: [{ id: 6, name: "Team A" }] },
    ...(routes as Record<string, { body?: unknown }>),
  });
  render(<AssignmentsTab siteId={9} teaching={teaching} />);
  return server;
}

describe("a student hands in (items 2.21, 2.22, 2.35, 3.22)", () => {
  it("sees what to hand in and the late rule, hands in several files with the integrity statement, and gets a receipt", async () => {
    const { calls } = show([open], false, {
      "POST /assignments/3/submit/": { status: 201, body: { ...mine, files: [{ id: 1, filename: "a.pdf", size: 2048, sha256: "x", download_url: "/x" }, { id: 2, filename: "b.pdf", size: 3000000, sha256: "y", download_url: "/y" }] } },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Open" }));
    expect(screen.getByText("A typed answer, or up to 3 files: PDF, each at most 20 MB.")).toBeInTheDocument();
    expect(screen.getByText("Late work loses 5% of the maximum mark for each day or part of a day late, at most 20%.")).toBeInTheDocument();
    // The rubric is shown with the assignment.
    expect(screen.getByText("Rubric: Soil profile report rubric")).toBeInTheDocument();

    await user.upload(screen.getByLabelText("Files (up to 3)"), [
      new File(["%PDF"], "a.pdf", { type: "application/pdf" }),
      new File(["%PDF"], "b.pdf", { type: "application/pdf" }),
    ]);
    const hand = screen.getByRole("button", { name: "Hand in" });
    expect(screen.getByRole("checkbox", { name: "I confirm that this work is my own." })).toBeRequired();
    await user.click(screen.getByRole("checkbox", { name: "I confirm that this work is my own." }));
    await user.click(hand);

    const receipt = await screen.findByRole("status", { name: "Receipt" });
    expect(receipt).toHaveTextContent("Receipt GSA-ABCDE-FGHJK");
    expect(receipt).toHaveTextContent("b.pdf (2.9 MB)");
    const sent = calls.find((c) => c.path === "/assignments/3/submit/")!.body as FormData;
    expect(sent.getAll("files")).toHaveLength(2);
    expect(sent.get("integrity_accepted")).toBe("true");
  });

  it("keeps a typed answer on the device without a connection, with the integrity statement accepted (item 4.02)", async () => {
    const { calls } = show([open], false, { "POST /assignments/3/submit/": [offline, { status: 201, body: mine }] });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Open" }));
    await user.type(screen.getByLabelText("Your answer"), "Notebook photographed and labelled.");
    await user.click(screen.getByRole("checkbox", { name: "I confirm that this work is my own." }));
    await user.click(screen.getByRole("button", { name: "Hand in" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Waiting to send");
    expect(pendingCount()).toBe(1);
    await flush();
    expect(await screen.findByText("Sent")).toBeInTheDocument();
    expect(calls.at(-1)!.body).toMatchObject({ text: "Notebook photographed and labelled.", integrity_accepted: true });
  });

  it("asks for a connection when files are attached, as files cannot wait on the device", async () => {
    show([assignment({ ...open, requires_integrity: false })], false, { "POST /assignments/3/submit/": offline });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Open" }));
    await user.upload(screen.getByLabelText("Files (up to 3)"), new File(["x"], "notes.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Hand in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No connection.");
    expect(pendingCount()).toBe(0);
  });

  it("sees the released mark with its late penalty, the rubric levels given, spoken feedback, and every hand-in", async () => {
    const marked = submission({
      mark: released,
      accommodation_applies: null,
      feedback_files: [{ id: 51, filename: "comments.m4a", kind: "m4a", is_audio: true, size: 900, download_url: "/api/v1/feedback-files/51/" }],
    });
    show([assignment({ my_submission: marked, submissions_count: null })], false, {
      "GET /submissions/21/history/": {
        body: {
          submission: 21,
          attempts: [{ number: 1, submitted_at: "2026-10-02T14:00:00Z", client_submitted_at: null, submitted_by: "S2026911", is_late: true, receipt: "GSA-ABCDE-FGHJK", content_hash: "c".repeat(64), integrity_accepted: true, text: "", files: [{ id: 31, filename: "profile.pdf", size: 1, sha256: "", download_url: "/f/31" }], is_marked_attempt: true }],
          marks: [],
          moderation: null,
        },
      },
      "GET /receipts/GSA-ABCDE-FGHJK/": {
        body: { receipt: "GSA-ABCDE-FGHJK", site: "AGR205", assignment: "Soil profile report", student_no: "S2026911", attempt: 1, submitted_at: "2026-10-02T14:00:00Z", is_late: true, content_hash: "c".repeat(64), files: [] },
      },
    });
    const user = userEvent.setup();
    expect(await screen.findByText("Marked")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open" }));
    const box = screen.getByRole("region", { name: "Your mark" });
    expect(box).toHaveTextContent("Marked: 14 out of 20");
    expect(box).toHaveTextContent("Late penalty: 1 (5% of the maximum) taken from 15.");
    expect(within(box).getByLabelText("Spoken feedback comments.m4a")).toHaveAttribute("src", "/api/v1/feedback-files/51/");
    expect(screen.getByText("Every horizon described").closest("li")).toHaveClass("chosen");
    expect(screen.getByText("Comment: Drainage?")).toBeInTheDocument();
    // Marked work cannot be handed in again.
    expect(screen.queryByRole("button", { name: /Hand in/ })).not.toBeInTheDocument();

    await user.click(screen.getByText("Every hand-in and its receipt"));
    expect(await screen.findByText(/Receipt GSA-ABCDE-FGHJK · fingerprint cccccccccccccccc · integrity statement accepted/)).toBeInTheDocument();
    await user.click(screen.getByText("Look up a receipt"));
    await user.type(screen.getByLabelText("Receipt code"), "GSA-ABCDE-FGHJK");
    await user.click(screen.getByRole("button", { name: "Look up" }));
    expect(await screen.findByText(/GSA-ABCDE-FGHJK: Soil profile report \(AGR205\), hand-in 1 by S2026911/)).toBeInTheDocument();
  });

  it("is told when the deadline has passed and late work is not taken", async () => {
    show([assignment({ allow_late: false, submissions_count: null })], false);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Open" }));
    expect(screen.getByText("The deadline has passed.")).toBeInTheDocument();
    expect(screen.getByText("Work cannot be handed in after the due date.")).toBeInTheDocument();
  });
});

describe("teaching staff set assignments (items 2.22, 2.26, 2.27, 2.35, 3.16, 3.17, 3.22)", () => {
  it("creates an assignment with file kinds, late rule, rubric, anonymous marking and category", async () => {
    const { calls } = show([], true, { "POST /assignments/": { status: 201, body: assignment() } });
    const user = userEvent.setup();
    expect(await screen.findByText("No assignments yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Rubrics and marking guides" })).toHaveAttribute("href", "#/sites/9/rubrics");
    await user.click(screen.getByRole("button", { name: "New assignment" }));
    const form = screen.getByRole("form", { name: "New assignment" });
    await user.type(within(form).getByLabelText("Title"), "Soil profile report");
    await user.type(within(form).getByLabelText("Due"), "2026-10-08T14:00");
    await user.click(within(form).getByRole("checkbox", { name: "PDF" }));
    await user.clear(within(form).getByLabelText(/Files in one hand-in/));
    await user.type(within(form).getByLabelText(/Files in one hand-in/), "3");
    await user.selectOptions(within(form).getByLabelText("Late penalty"), "per_day");
    await user.type(within(form).getByLabelText(/The most taken in all/), "20");
    await user.selectOptions(within(form).getByLabelText("Rubric or marking guide"), "4");
    await user.selectOptions(await within(form).findByLabelText("Gradebook category"), "5");
    await user.click(within(form).getByRole("checkbox", { name: /Anonymous marking/ }));
    await user.selectOptions(within(form).getByLabelText("Second marking"), "sample");
    await user.click(within(form).getByRole("checkbox", { name: /Group assignment/ }));
    await user.click(within(form).getByRole("checkbox", { name: "Team A" }));
    await user.click(within(form).getByRole("button", { name: "Create assignment" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/assignments/")).toBe(true));
    const body = calls.find((c) => c.method === "POST" && c.path === "/assignments/")!.body as Record<string, unknown>;
    expect(body).toMatchObject({
      site: 9,
      title: "Soil profile report",
      accepted_kinds: ["pdf"],
      max_files: 3,
      late_penalty: "per_day",
      late_penalty_percent: "5",
      late_penalty_cap: "20",
      rubric: 4,
      category: 5,
      anonymous: true,
      moderation: "sample",
      is_group: true,
      groups: [6],
      requires_integrity: true,
      opens_at: null,
    });
    expect(body.due_at).toMatch(/^2026-10-08T/);
  });

  it("changes an assignment, and cannot change anonymous marking once work is handed in", async () => {
    const { calls } = show([assignment({ anonymous: true })], true, { "PATCH /assignments/3/": { body: assignment() } });
    const user = userEvent.setup();
    expect(await screen.findByText("Anonymous marking")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mark" })).toHaveAttribute("href", "#/sites/9/assignments/3/marking");
    await user.click(screen.getByRole("button", { name: "Change" }));
    const form = screen.getByRole("form", { name: "Change Soil profile report" });
    expect(within(form).getByRole("checkbox", { name: /Anonymous marking/ })).toBeDisabled();
    await user.selectOptions(within(form).getByLabelText("Late penalty"), "none");
    await user.click(within(form).getByRole("button", { name: "Save changes" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toMatchObject({ late_penalty: "none", late_penalty_percent: "0", late_penalty_cap: null });
  });

  it("grants an extension to one student or a group, with the reason, and withdraws one", async () => {
    const existing = { id: 70, assignment: 3, student: 101, student_no: "S2026911", group: null, due_at: "2026-10-10T14:00:00Z", reason: "Ill", granted_by: 1 };
    const { calls } = show([assignment()], true, {
      "GET /extensions/": [page([existing]), page([existing]), page([])],
      "GET /sites/9/members/": { body: { count: 1, next: null, previous: null, results: [{ membership_id: 1, person_id: 101, external_id: "S2026911", name: "Ria Ramdial", role: "student" }] } },
      "POST /extensions/": { status: 201, body: existing },
      "DELETE /extensions/70/": { status: 204 },
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Extensions" }));
    const panel = screen.getByRole("region", { name: "Extensions for Soil profile report" });
    expect(await within(panel).findByText("Ria Ramdial")).toBeInTheDocument();
    expect(within(panel).getByText("Ill")).toBeInTheDocument();
    await user.selectOptions(within(panel).getByLabelText("For"), "group:6");
    await user.type(within(panel).getByLabelText("New due date"), "2026-10-12T14:00");
    await user.type(within(panel).getByLabelText("Reason"), "Field trip");
    await user.click(within(panel).getByRole("button", { name: "Grant the extension" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/extensions/")).toBe(true));
    expect(calls.find((c) => c.path === "/extensions/" && c.method === "POST")!.body).toMatchObject({ assignment: 3, student: null, group: 6, reason: "Field trip" });
    await user.click(within(panel).getByRole("button", { name: "Withdraw" }));
    expect(await within(panel).findByText(/No extensions/)).toBeInTheDocument();
  });

  it("says when the assignments cannot be loaded", async () => {
    fakeServer({ "GET /assignments/": { status: 403, body: { code: "forbidden", detail: "You are not a member of this course." } } });
    render(<AssignmentsTab siteId={9} teaching={false} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("You are not a member of this course.");
  });
});
