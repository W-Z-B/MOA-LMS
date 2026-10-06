import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { AuditEntry } from "../../api/types-staff";
import { fakeServer } from "../../test/fetch";
import { AuditLog } from "./AuditLog";

const entry = (over: Partial<AuditEntry> = {}): AuditEntry => ({
  id: 120,
  at: "2026-10-05T14:00:00Z",
  actor: "Marlon Bacchus",
  actor_username: "marlon.bacchus",
  action: "update",
  action_name: "Changed",
  entity: "assessments.mark",
  record: "Mark",
  entity_id: 9,
  person_number: "S2026901",
  reason: "Moderation",
  source_ip: "10.0.0.4",
  changes: [{ field: "mark", before: "38", after: null }],
  ...over,
});

const check = { id: 1, checked_at: "2026-10-05T02:00:00Z", checked_by: "The nightly check", rows: 119, intact: true, last_id: 119, first_broken_id: null, detail: "" };

describe("the audit log (item 1.17)", () => {
  it("shows the entries newest first, with filters, an export of what matches, and pages", async () => {
    const server = fakeServer({
      "GET /audit/chain/": { body: { entries: 120, newest: 120, latest_check: check } },
      "GET /audit/choices/": { body: { actions: [{ code: "update", name: "Changed" }], records: [{ code: "assessments.mark", name: "Mark" }] } },
      "GET /audit/?page=1": { body: { count: 120, next: "x", previous: null, results: [entry(), entry({ id: 119, entity_id: null, person_number: null, source_ip: null, reason: "", changes: [] })] } },
      "GET /audit/?page=2": { body: { count: 120, next: null, previous: "x", results: [entry({ id: 70, changes: [{ field: "rubric", before: { a: 1 }, after: "" }] })] } },
      "GET /audit/?action=update&record=assessments.mark&who=marlon&person=S2026901&since=2026-10-01&until=2026-10-05&q=moderation&page=1": {
        body: { count: 1, next: null, previous: null, results: [entry()] },
      },
    });
    render(<AuditLog />);
    const list = await screen.findByRole("list", { name: "Audit entries" });
    expect(screen.getByText("120 entries match.")).toBeInTheDocument();
    const [first] = within(list).getAllByRole("listitem");
    expect(first).toHaveTextContent("Changed: Mark 9");
    expect(first).toHaveTextContent("Marlon Bacchus · about S2026901 · from 10.0.0.4");
    expect(first).toHaveTextContent("Reason: Moderation");
    expect(first).toHaveTextContent("mark: 38 → blank");
    expect(screen.getByRole("button", { name: "Newer entries" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Older entries" }));
    expect(await screen.findByText('rubric: {"a":1} → blank')).toBeInTheDocument();

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("What was done"), await screen.findByRole("option", { name: "Changed" }));
    await user.selectOptions(screen.getByLabelText("Kind of record"), "assessments.mark");
    await user.type(screen.getByLabelText("Who did it (name or username)"), "marlon");
    await user.type(screen.getByLabelText("About the person (employee or student number)"), "S2026901");
    await user.type(screen.getByLabelText("From"), "2026-10-01");
    await user.type(screen.getByLabelText("To"), "2026-10-05");
    await user.type(screen.getByLabelText("Words in the reason given"), "moderation");
    await user.click(screen.getByRole("button", { name: "Show the entries" }));
    expect(await screen.findByText("1 entry matches.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export to a spreadsheet (CSV)" })).toHaveAttribute(
      "href",
      "/api/v1/audit/export/?action=update&record=assessments.mark&who=marlon&person=S2026901&since=2026-10-01&until=2026-10-05&q=moderation",
    );
    expect(server.calls.at(-1)?.path).toContain("q=moderation");
  });

  it("says whether the log is intact, and checks the chain now", async () => {
    const server = fakeServer({
      "GET /audit/chain/": { body: { entries: 5, newest: 5, latest_check: null } },
      "GET /audit/choices/": { body: { actions: [], records: [] } },
      "GET /audit/?page=1": { body: { count: 0, next: null, previous: null, results: [] } },
      "POST /audit/chain/": [
        { body: { entries: 6, newest: 6, latest_check: { ...check, checked_by: "Ayesha Ramdin", rows: 6 } } },
        { body: { entries: 7, newest: 7, latest_check: { ...check, intact: false, first_broken_id: 3, detail: "" } } },
      ],
    });
    render(<AuditLog />);
    expect(await screen.findByText(/It has not been checked yet./)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Check the chain now" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Every entry matches its fingerprint: 6 entries checked.");
    expect(screen.getByText("Intact")).toBeInTheDocument();
    expect(server.calls.filter((c) => c.method === "POST")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Check the chain now" }));
    expect(await screen.findByText("Broken")).toBeInTheDocument();
    expect(screen.getByText("From entry 3.")).toBeInTheDocument();
  });
});
