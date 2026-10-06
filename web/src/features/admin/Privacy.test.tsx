import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Breach, CorrectionRequest, DisposalRun, NoticeVersion, RetentionRule } from "../../api/types-staff";
import { fakeServer } from "../../test/fetch";
import { administrator, auditor, courseAdmin, dpo, page } from "../../test/staff";
import { Corrections, Notices } from "./Privacy";
import { Breaches, Retention } from "./Retention";

const notice = (over: Partial<NoticeVersion> = {}): NoticeVersion => ({
  id: 1,
  version: 1,
  title: "How the GSA LMS uses your personal data",
  body: "We keep marks.",
  created_at: "2026-09-01T10:00:00Z",
  published_at: "2026-09-02T10:00:00Z",
  published_by: "Ayesha Ramdin",
  ...over,
});

describe("the privacy notice (item 1.18)", () => {
  it("writes a new version as a draft, edits it, and publishes it", async () => {
    const draft = notice({ id: 2, version: 2, published_at: null, published_by: null });
    const server = fakeServer({
      "GET /privacy/notices/": [page([notice()]), page([notice(), draft]), page([notice(), draft]), page([notice(), { ...draft, published_at: "2026-10-05T10:00:00Z" }])],
      "POST /privacy/notices/": { status: 201, body: draft },
      "PATCH /privacy/notices/2/": { body: draft },
      "POST /privacy/notices/2/publish/": { body: draft },
    });
    render(<Notices me={dpo} />);
    const list = await screen.findByRole("list", { name: "Notice versions" });
    expect(list).toHaveTextContent("Published 02/09/2026");
    expect(within(list).queryByRole("button")).not.toBeInTheDocument(); // a published version never changes
    await userEvent.click(screen.getByRole("button", { name: "Write a new version" }));
    expect(screen.getByLabelText("Title")).toHaveValue("How the GSA LMS uses your personal data"); // starts from the newest
    await userEvent.click(screen.getByRole("button", { name: "Save as a draft" }));
    expect(await screen.findByText("Version 2 is saved as a draft.")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Edit version 2" }));
    await userEvent.type(screen.getByLabelText("Text (Markdown)"), " And feedback.");
    await userEvent.click(screen.getByRole("button", { name: "Save the draft" }));
    expect(await screen.findByText("Version 2 is saved.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({ title: draft.title, body: "We keep marks. And feedback." });
    await userEvent.click(screen.getByRole("button", { name: "Publish version 2" }));
    expect(await screen.findByText("Version 2 is in force. Everyone reads it at their next sign-in.")).toBeInTheDocument();
  });

  it("lets the auditor read the versions only", async () => {
    fakeServer({ "GET /privacy/notices/": page([notice({ published_at: null, published_by: null })]) });
    render(<Notices me={auditor} />);
    expect(await screen.findByText("Draft")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

const correction = (over: Partial<CorrectionRequest> = {}): CorrectionRequest => ({
  id: 4,
  person: 9,
  person_name: "Kezia Persaud",
  person_number: "S2026901",
  subject: "mark",
  subject_name: "My marks or feedback",
  wrong: "38",
  should_be: "40",
  state: "open",
  state_name: "With a course administrator",
  due_by: "2026-11-04",
  overdue: false,
  created_at: "2026-10-05T10:00:00Z",
  decided_by_name: null,
  decision_note: "",
  is_mine: false,
  ...over,
});

describe("correction requests (item 1.18)", () => {
  it("answers one: not changed only with a reason, or corrected", async () => {
    const server = fakeServer({
      "GET /privacy/corrections/?state=open": [page([correction(), correction({ id: 5, overdue: true, is_mine: true })]), page([])],
      "GET /privacy/corrections/?state=declined": page([correction({ state: "declined", state_name: "Not changed", decision_note: "The mark stands." })]),
      "POST /privacy/corrections/4/decide/": { body: correction({ state: "corrected" }) },
    });
    render(<Corrections me={courseAdmin} />);
    const list = await screen.findByRole("list", { name: "Correction requests" });
    const [first, mine] = within(list).getAllByRole("listitem");
    expect(first).toHaveTextContent("Answer by 04/11/2026");
    expect(within(mine).queryByRole("button")).not.toBeInTheDocument(); // someone else answers a request about me
    await userEvent.click(within(first).getByRole("button", { name: "Not changed: Kezia Persaud" }));
    expect(await within(first).findByRole("alert")).toHaveTextContent("Say why the record is not changed.");
    await userEvent.click(within(first).getByRole("button", { name: "Corrected: Kezia Persaud" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Kezia Persaud: corrected. They are told.");
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ outcome: "corrected", note: "" });
    expect(await screen.findByText("No requests here.")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Show"), "declined");
    expect(await screen.findByText("Answer: The mark stands.")).toBeInTheDocument();
  });

  it("lets the DPO read them without answering", async () => {
    fakeServer({ "GET /privacy/corrections/?state=open": page([correction()]) });
    render(<Corrections me={dpo} />);
    expect(await screen.findByRole("list", { name: "Correction requests" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Corrected/ })).not.toBeInTheDocument();
  });
});

const rule = (over: Partial<RetentionRule> = {}): RetentionRule => ({
  id: 1,
  code: "submissions",
  name: "Submissions and marks",
  keep_months: 72,
  counted_from: "the end of the course",
  action: "delete",
  action_name: "Delete",
  automatic: false,
  confirmed: false,
  confirmed_by_name: null,
  note: "Proposed in the impact assessment.",
  open_run: null,
  ...over,
});

const run = (over: Partial<DisposalRun> = {}): DisposalRun => ({
  id: 3,
  rule: 1,
  rule_name: "Submissions and marks",
  state: "proposed",
  state_name: "Waiting for a second person",
  created_at: "2026-10-05T10:00:00Z",
  proposed_by: "The DPO",
  approved_by_name: null,
  proposed_by_me: false,
  items: [
    { id: 11, description: "Submission 4 of S2019001", person_number: "S2019001", due_since: "2026-01-01", keep_reason: "", disposed_at: null },
    { id: 12, description: "Submission 5 of S2019002", person_number: "S2019002", due_since: "2026-01-01", keep_reason: "Appeal open", disposed_at: null },
  ],
  ...over,
});

describe("retention and disposal (item 1.19)", () => {
  it("changes and confirms a period, finds what is due, keeps a record, and approves the run as the second person", async () => {
    const server = fakeServer({
      "GET /privacy/retention-rules/": { body: [rule(), rule({ id: 2, name: "Sign-in records", automatic: true, confirmed: true, confirmed_by_name: "The DPO", keep_months: 12, note: "" }), rule({ id: 3, name: "Records reviewed by GSA", keep_months: null, action: "review", action_name: "Reviewed by GSA" })] },
      "GET /privacy/disposal-runs/": page([run(), run({ id: 4, state: "done", state_name: "Disposed of", approved_by_name: "Ayesha Ramdin", items: [{ ...run().items[0], disposed_at: "2026-10-05T11:00:00Z" }] })]),
      "PATCH /privacy/retention-rules/1/": { body: rule({ keep_months: 84 }) },
      "POST /privacy/retention-rules/1/confirm/": { body: rule({ confirmed: true }) },
      "POST /privacy/retention-rules/1/find/": { status: 201, body: { detail: "2 records are due. Someone else approves before anything is destroyed.", run: null } },
      "POST /privacy/disposal-runs/3/keep/": { body: run() },
      "POST /privacy/disposal-runs/3/approve/": { body: run({ state: "done" }) },
      "POST /privacy/disposal-runs/3/cancel/": { body: run({ state: "cancelled" }) },
    });
    render(<Retention me={administrator} />);
    const rules = await screen.findByRole("list", { name: "Retention rules" });
    const [first, nightly, reviewed] = within(rules).getAllByRole("listitem");
    expect(first).toHaveTextContent("Kept 72 months from the end of the course · Delete");
    expect(nightly).toHaveTextContent("removed every night · confirmed by The DPO");
    expect(reviewed).toHaveTextContent("Each record's own date");
    expect(within(nightly).queryByRole("button", { name: /Find what is due/ })).not.toBeInTheDocument();
    expect(within(reviewed).queryByRole("button", { name: /Find what is due/ })).not.toBeInTheDocument();

    const months = within(first).getByLabelText("Months");
    await userEvent.clear(months);
    await userEvent.type(months, "84");
    await userEvent.click(within(first).getByRole("button", { name: "Save the period: Submissions and marks" }));
    expect(await within(first).findByRole("status")).toHaveTextContent("A changed period is confirmed again.");
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({ keep_months: 84 });
    await userEvent.click(within(first).getByRole("button", { name: "Confirm: Submissions and marks" }));
    expect(await within(first).findByText("Confirmed as agreed by GSA.")).toBeInTheDocument();
    await userEvent.click(within(first).getByRole("button", { name: "Find what is due: Submissions and marks" }));
    expect(await within(first).findByText(/2 records are due/)).toBeInTheDocument();

    const runs = await screen.findByRole("list", { name: "Disposal runs" });
    const [open, done] = within(runs).getAllByRole("listitem").filter((li) => li.parentElement === runs);
    expect(open).toHaveTextContent("kept: Appeal open");
    expect(done).toHaveTextContent("approved by Ayesha Ramdin");
    expect(done).toHaveTextContent("destroyed");
    expect(within(done).queryByRole("button")).not.toBeInTheDocument();
    await userEvent.click(within(open).getByRole("button", { name: "Keep: Submission 4 of S2019001" }));
    await userEvent.type(within(open).getByLabelText("Why it is kept"), "Legal hold");
    await userEvent.click(within(open).getByRole("button", { name: "Keep it" }));
    expect(await within(open).findByText("Kept.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.path.endsWith("/keep/"))?.body).toEqual({ item: 11, reason: "Legal hold" });
    await userEvent.click(within(open).getByRole("button", { name: "Approve the disposal" }));
    expect(await within(open).findByText(/Approved: every record not kept is destroyed/)).toBeInTheDocument();
    await userEvent.click(within(open).getByRole("button", { name: "Cancel the run" }));
    expect(await within(open).findByText("Cancelled.")).toBeInTheDocument();
  });

  it("does not offer the approval to the person who proposed the run, and lets the auditor only read", async () => {
    fakeServer({ "GET /privacy/retention-rules/": { body: [rule()] }, "GET /privacy/disposal-runs/": page([run({ proposed_by_me: true })]) });
    const { unmount } = render(<Retention me={dpo} />);
    expect(await screen.findByText("You proposed this run: a second person approves it.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve the disposal" })).not.toBeInTheDocument();
    unmount();
    render(<Retention me={auditor} />);
    expect(await screen.findByRole("list", { name: "Disposal runs" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

const breach = (over: Partial<Breach> = {}): Breach => ({
  id: 1,
  reference: "BR-2026-001",
  discovered_at: "2026-10-04T09:00:00Z",
  happened: "",
  summary: "A class list was emailed to the wrong group.",
  data_affected: "Names and student numbers of AGR101.",
  people_affected: 30,
  minors_affected: true,
  risk: "high",
  risk_name: "High",
  contained_at: null,
  commissioner_told_at: null,
  people_told_at: null,
  actions: "",
  closed_at: null,
  recorded_by: "The DPO",
  ...over,
});

describe("the breach register (item 1.19)", () => {
  it("records a breach, marks its steps as they are taken, and closes it once contained", async () => {
    const server = fakeServer({
      "GET /privacy/breaches/": [page([]), page([breach()]), page([breach({ contained_at: "2026-10-05T10:00:00Z", actions: "Recalled." })]), page([breach({ closed_at: "2026-10-05T12:00:00Z", contained_at: "2026-10-05T10:00:00Z" })])],
      "POST /privacy/breaches/": { status: 201, body: breach() },
      "PATCH /privacy/breaches/1/": { body: breach() },
      "POST /privacy/breaches/1/close/": { body: breach() },
    });
    render(<Breaches me={administrator} />);
    expect(await screen.findByText("No breach has been recorded.")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Discovered"), "2026-10-04T09:00");
    await user.type(screen.getByLabelText("What happened"), "A class list was emailed to the wrong group.");
    await user.type(screen.getByLabelText("What personal data, and whose"), "Names.");
    await user.type(screen.getByLabelText("How many people, if known"), "30");
    await user.selectOptions(screen.getByLabelText("Risk"), "high");
    await user.click(screen.getByLabelText(/Students\s+under 18/));
    await user.click(screen.getByRole("button", { name: "Record the breach" }));
    expect(await screen.findByText("BR-2026-001 is recorded. The administrators and the DPO are alerted.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "POST")?.body).toMatchObject({ people_affected: 30, risk: "high", minors_affected: true });
    const list = await screen.findByRole("list", { name: "Breaches" });
    expect(list).toHaveTextContent("30 people · students under 18");
    expect(within(list).queryByRole("button", { name: /^Close/ })).not.toBeInTheDocument(); // not before it is contained
    await user.click(within(list).getByRole("button", { name: "Contained now: BR-2026-001" }));
    expect(await screen.findByText("BR-2026-001: contained now.")).toBeInTheDocument();
    expect(Object.keys(server.calls.find((c) => c.method === "PATCH")?.body as object)).toEqual(["contained_at"]);
    expect(await screen.findByText("Done: Recalled.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close BR-2026-001" }));
    expect(await screen.findByText("BR-2026-001 is closed.")).toBeInTheDocument();
    expect(await screen.findByText("Closed")).toBeInTheDocument();
  });

  it("lets the auditor read the register only", async () => {
    fakeServer({ "GET /privacy/breaches/": page([breach({ people_affected: null, minors_affected: false })]) });
    render(<Breaches me={auditor} />);
    expect(await screen.findByText("High risk")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
