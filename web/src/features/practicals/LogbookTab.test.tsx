import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { flush, pending, pendingCount } from "../../app/offlineQueue";
import { fakeServer, offline } from "../../test/fetch";
import { LogbookTab } from "./LogbookTab";
import { drain, resetOutbox } from "./photoOutbox";
import { entry, jpeg, page } from "./testData";

const returned = {
  ...entry,
  id: 41,
  status: "returned" as const,
  supervisor_name: "Marlon Bacchus",
  reviewed_at: "2026-10-05T12:00:00Z",
  review_comment: "Give the oxygen reading.",
};
const signed = { ...entry, id: 42, task: "Cleaned the pond inlet", status: "signed" as const, supervisor_name: "Marlon Bacchus", reviewed_at: "2026-10-05T12:00:00Z" };
const totals = {
  site: "AGR101",
  rows: [
    {
      person_id: 31,
      student_no: "S2026901",
      name: "Kezia Persaud",
      hours: [
        { unit_type: "pond", label: "Fish pond", signed_hours: "3.00", waiting_hours: "5.00" },
        { unit_type: "crop_plot", label: "Crop plot", signed_hours: "1.50", waiting_hours: "0.00" },
      ],
    },
  ],
};

function open(hash: string, teaching: boolean, routes: Record<string, unknown> = {}) {
  window.location.hash = hash;
  const server = fakeServer({
    "GET /logbook/": { body: page([entry, returned, signed]) },
    "GET /sites/9/logbook-totals/": { body: totals },
    ...(routes as Record<string, { body?: unknown }>),
  });
  render(<LogbookTab siteId={9} teaching={teaching} />);
  return server;
}

/** Fill in the entry form as a student does on the phone. */
async function fill(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByLabelText("Hours"), "2.5");
  await user.selectOptions(screen.getByLabelText("Where"), "pond");
  await user.type(screen.getByLabelText("Which unit"), "Pond 2, tilapia");
  await user.type(screen.getByLabelText("What you did"), "Fed fingerlings and checked oxygen");
}

beforeEach(() => resetOutbox());
afterEach(() => {
  window.location.hash = "";
});

describe("a student's logbook (item 3.14)", { timeout: 15_000 }, () => {
  it("shows each entry's state, the hours by kind of place, and the supervisor's comment", async () => {
    open("#/sites/9/logbook", false);
    const user = userEvent.setup();
    expect(await screen.findByText("Waiting for sign-off")).toBeInTheDocument();
    expect(screen.getByText("Returned for correction")).toBeInTheDocument();
    expect(screen.getByText("Signed off")).toBeInTheDocument();
    expect(screen.getByText(/Returned by Marlon Bacchus .*: Give the oxygen reading./)).toBeInTheDocument();
    expect(await screen.findByText("3.00 h signed")).toBeInTheDocument();
    expect(screen.getByText("4.50 h signed")).toBeInTheDocument();
    expect(screen.getAllByText(/5.00 h waiting/)).toHaveLength(2);
    // A signed entry is locked; a returned one can be corrected.
    const signedCard = screen.getByRole("article", { name: /Cleaned the pond inlet/ });
    expect(within(signedCard).queryByRole("button")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Correct and send again" }));
    expect(window.location.hash).toBe("#/sites/9/logbook/41");
  });

  it("adds an entry with signal, with its photo", async () => {
    const { calls } = open("#/sites/9/logbook/new", false, {
      "POST /logbook/": { status: 201, body: { ...entry, id: 43 } },
      "POST /logbook/43/photos/": { status: 201, body: entry },
    });
    const user = userEvent.setup();
    await fill(user);
    await user.upload(screen.getByLabelText("Take a photo"), jpeg("pond.jpg"));
    await user.click(screen.getByRole("button", { name: "Save entry" }));
    expect(await screen.findByText("Sent to your supervisor for sign-off.")).toBeInTheDocument();
    expect(await screen.findByText("Photo sent")).toBeInTheDocument();
    const record = calls.find((c) => c.method === "POST" && c.path === "/logbook/")!;
    expect(record.body).toMatchObject({ site: 9, unit_type: "pond", unit_text: "Pond 2, tilapia", hours: "2.5", task: "Fed fingerlings and checked oxygen" });
    expect((record.body as { client_recorded_at: string }).client_recorded_at).toMatch(/Z$/);
    expect(record.headers.get("Idempotency-Key")).toBeTruthy();
  });

  it("keeps an entry and its photo on the phone without signal, and sends the entry once when it returns", async () => {
    const { calls } = open("#/sites/9/logbook/new", false, {
      "POST /logbook/": [offline, { status: 201, body: { ...entry, id: 44 } }],
      "POST /logbook/44/photos/": { status: 201, body: entry },
    });
    const user = userEvent.setup();
    await fill(user);
    await user.upload(screen.getByLabelText("Take a photo"), jpeg("pond.jpg"));
    await user.click(screen.getByRole("button", { name: "Save entry" }));
    expect(await screen.findByText(/Waiting to send/)).toBeInTheDocument();
    expect(await screen.findByText(/1 photo waiting to send/)).toBeInTheDocument();
    expect(pendingCount()).toBe(1);
    const key = pending()[0].idempotencyKey;

    await user.click(screen.getByRole("button", { name: "Back to my logbook" }));
    expect(await screen.findByRole("heading", { name: "Waiting on this phone" })).toBeInTheDocument();
    await flush();
    await drain();
    expect(pendingCount()).toBe(0);
    const records = calls.filter((c) => c.method === "POST" && c.path === "/logbook/");
    expect(new Set(records.map((c) => c.headers.get("Idempotency-Key")))).toEqual(new Set([key]));
    expect(calls.filter((c) => c.path === "/logbook/44/photos/")).toHaveLength(1);
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Waiting on this phone" })).not.toBeInTheDocument());
  });

  it("corrects a returned entry, which needs signal", async () => {
    const { calls } = open("#/sites/9/logbook/41", false, {
      "GET /logbook/41/": { body: returned },
      "PATCH /logbook/41/": [offline, { body: { ...returned, status: "pending" } }],
    });
    const user = userEvent.setup();
    expect(await screen.findByText("Returned by Marlon Bacchus: Give the oxygen reading.")).toBeInTheDocument();
    expect(screen.getByLabelText("What you did")).toHaveValue("Fed fingerlings and checked oxygen");
    await user.type(screen.getByLabelText("Notes"), "Oxygen 6.1 mg/l.");
    await user.click(screen.getByRole("button", { name: "Send the correction" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A correction needs signal");
    await user.click(screen.getByRole("button", { name: "Send the correction" }));
    expect(await screen.findByRole("heading", { name: "Correction sent" })).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "PATCH").at(-1)?.body).toMatchObject({ notes: "Oxygen 6.1 mg/l." });
  });

  it("shows a refusal from the server", async () => {
    open("#/sites/9/logbook/new", false, {
      "POST /logbook/": { status: 400, body: { work_date: ["The work date cannot be in the future."] } },
    });
    const user = userEvent.setup();
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Save entry" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("work date: The work date cannot be in the future.");
    expect(pendingCount()).toBe(0);
  });
});

describe("signing off logbooks (item 3.14)", { timeout: 15_000 }, () => {
  it("signs an entry off, and returns one only with a comment", async () => {
    const { calls } = open("#/sites/9/logbook", true, {
      "GET /logbook/": { body: page([entry, { ...entry, id: 45, student_name: "Tevin Joseph", student_no: "S2026902", work_date: "2026-10-03" }]) },
      "POST /logbook/40/review/": { body: { ...entry, status: "signed" } },
      "POST /logbook/45/review/": { body: { ...entry, status: "returned" } },
    });
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: "Waiting for sign-off" })).toBeInTheDocument();
    // Oldest first.
    const cards = screen.getAllByRole("article");
    expect(cards[0]).toHaveAccessibleName(/03\/10\/2026/);
    await user.click(screen.getByRole("button", { name: "Sign off Kezia Persaud's entry for 04/10/2026" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Signed off: Kezia Persaud, 04/10/2026.");
    expect(calls.find((c) => c.path === "/logbook/40/review/")?.body).toMatchObject({ decision: "sign", comment: "" });

    await user.click(screen.getByRole("button", { name: "Return Tevin Joseph's entry for 03/10/2026" }));
    await user.type(screen.getByLabelText("What needs correcting"), "Give the oxygen reading.");
    await user.click(screen.getByRole("button", { name: "Return to Tevin Joseph" }));
    expect(calls.find((c) => c.path === "/logbook/45/review/")?.body).toMatchObject({ decision: "return", comment: "Give the oxygen reading." });
    expect(screen.getByRole("region", { name: "Hours of Kezia Persaud" })).toHaveTextContent("Fish pond");
  });
});
