import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flush, pending, pendingCount } from "../../app/offlineQueue";
import { fakeServer, offline } from "../../test/fetch";
import { drain, resetOutbox } from "./photoOutbox";
import { PracticalsTab } from "./PracticalsTab";
import { jpeg, observation, students, task } from "./testData";

const created = { status: 201, body: { ...observation, is_released: false } };

function open(hash: string, routes: Record<string, unknown> = {}) {
  window.location.hash = hash;
  const server = fakeServer({
    "GET /practical-tasks/5/": { body: task },
    "GET /practical-tasks/5/students/": { body: students },
    ...(routes as Record<string, { body?: unknown }>),
  });
  render(<PracticalsTab siteId={9} teaching />);
  return server;
}

/** Mark both criteria: the critical one met, the score 4 of 5. */
async function markAll(user: ReturnType<typeof userEvent.setup>) {
  const bed = await screen.findByRole("group", { name: /Bed formed to 1.2 m/ });
  await user.click(within(bed).getByRole("button", { name: "Met" }));
  await user.click(screen.getByRole("button", { name: "4 of 5" }));
}

beforeEach(() => resetOutbox());
afterEach(() => {
  window.location.hash = "";
  Reflect.deleteProperty(navigator, "geolocation");
});

describe("the field checklist (items 3.12 and 3.15)", { timeout: 15_000 }, () => {
  it("picks a student from the class list with their next attempt", async () => {
    open("#/sites/9/practicals/5/observe");
    const user = userEvent.setup();
    const kezia = await screen.findByRole("button", { name: /Kezia Persaud/ });
    expect(kezia).toHaveTextContent("attempt 1 of 2");
    expect(screen.getByRole("button", { name: /Tevin Joseph/ })).toHaveTextContent("attempt 2 of 2");
    await user.type(screen.getByLabelText("Find a student"), "tevin");
    expect(screen.queryByRole("button", { name: /Kezia Persaud/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Tevin Joseph/ }));
    expect(window.location.hash).toBe("#/sites/9/practicals/5/observe/32");
  });

  it("will not save until every criterion has a result", async () => {
    const { calls } = open("#/sites/9/practicals/5/observe/31");
    const user = userEvent.setup();
    await user.click(within(await screen.findByRole("group", { name: /Bed formed/ })).getByRole("button", { name: "Not met" }));
    expect(screen.getByRole("button", { name: "Not met" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/critical not met/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save observation" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Still to mark: Soil tilth");
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });

  it("saves with signal: the phone's time, a key, the comment, the place when asked for, then the photo", async () => {
    const getCurrentPosition = vi.fn((ok: PositionCallback) =>
      ok({ coords: { latitude: 6.8012345, longitude: -58.1554321, accuracy: 12 } } as GeolocationPosition),
    );
    Object.defineProperty(navigator, "geolocation", { value: { getCurrentPosition }, configurable: true });
    const { calls } = open("#/sites/9/practicals/5/observe/31", {
      "POST /practical-tasks/5/observations/": created,
      "POST /observations/77/photos/": { status: 201, body: observation },
    });
    const user = userEvent.setup();
    await markAll(user);
    await user.click(screen.getAllByRole("button", { name: "Add a comment" })[1]);
    await user.type(screen.getByLabelText("Comment"), "Fine tilth");
    await user.type(screen.getByLabelText("Comments for the student"), "Good, even bed.");
    await user.upload(screen.getByLabelText("Take a photo"), jpeg());
    expect(screen.getByRole("button", { name: "Remove photo bed.jpg" })).toBeInTheDocument();
    // The place is read only when asked for, and says why.
    expect(getCurrentPosition).not.toHaveBeenCalled();
    expect(screen.getByText(/your location is never tracked/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add my location" }));
    expect(screen.getByText(/Location added: 6.801234, -58.155432/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save observation" }));

    expect(await screen.findByRole("heading", { name: "Saved: Kezia Persaud" })).toBeInTheDocument();
    expect(await screen.findByText("Photo sent")).toBeInTheDocument();
    const [record, photos] = calls.filter((c) => c.method === "POST");
    expect(record.body).toMatchObject({
      student: 31,
      location_text: "Plot 7",
      comments: "Good, even bed.",
      latitude: "6.801234",
      longitude: "-58.155432",
      results: [
        { criterion: 11, passed: true, comment: "" },
        { criterion: 12, score: 4, comment: "Fine tilth" },
      ],
    });
    expect(new Date((record.body as { observed_at: string }).observed_at).getTime()).toBeLessThanOrEqual(Date.now());
    expect(record.headers.get("Idempotency-Key")).toMatch(/[0-9a-f-]{36}/);
    expect((photos.body as FormData).getAll("photos")).toHaveLength(1);
    expect(photos.headers.get("Idempotency-Key")).toMatch(/[0-9a-f-]{36}/);
  });

  it("keeps the checklist and its photo on the phone without signal, then sends each once (photos queued)", async () => {
    const { calls } = open("#/sites/9/practicals/5/observe/31", {
      "POST /practical-tasks/5/observations/": [offline, created],
      "POST /observations/77/photos/": { status: 201, body: observation },
    });
    const user = userEvent.setup();
    await markAll(user);
    await user.upload(screen.getByLabelText("Choose photos"), [jpeg("one.jpg"), jpeg("two.jpg")]);
    await user.click(screen.getByRole("button", { name: "Save observation" }));

    expect(await screen.findByText(/Waiting to send/)).toBeInTheDocument();
    expect(await screen.findByText(/2 photos waiting to send/)).toBeInTheDocument();
    expect(await screen.findByText(/1 record and 2 photos waiting on this phone/)).toBeInTheDocument();
    expect(pendingCount()).toBe(1);
    const key = pending()[0].idempotencyKey;

    // The signal returns: the record goes from the queue under its key; the photos follow it.
    await flush();
    await drain();
    expect(await screen.findByText("2 photos sent")).toBeInTheDocument();
    const posts = calls.filter((c) => c.method === "POST");
    const records = posts.filter((c) => c.path === "/practical-tasks/5/observations/");
    // The first try was lost; the queue sent it, and the photos asked for its answer again: one key throughout.
    expect(records.map((c) => c.headers.get("Idempotency-Key"))).toEqual([key, key, key]);
    const uploads = posts.filter((c) => c.path === "/observations/77/photos/");
    expect(uploads).toHaveLength(1);
    expect((uploads[0].body as FormData).getAll("photos")).toHaveLength(2);
    expect(screen.queryByText(/waiting on this phone/)).not.toBeInTheDocument();
  });

  it("shows the server's refusal, such as no attempts left", async () => {
    open("#/sites/9/practicals/5/observe/31", {
      "POST /practical-tasks/5/observations/": {
        status: 409,
        body: { code: "no_attempts_left", detail: "This student has had all 2 attempts at this task." },
      },
    });
    const user = userEvent.setup();
    await markAll(user);
    await user.click(screen.getByRole("button", { name: "Save observation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("all 2 attempts");
    expect(pendingCount()).toBe(0);
  });

  it("opens the copy kept on the phone when there is no signal", async () => {
    open("#/sites/9/practicals/5/observe");
    expect(await screen.findByRole("button", { name: /Kezia Persaud/ })).toBeInTheDocument();
    cleanup();
    window.location.hash = "#/sites/9/practicals/5/observe";
    fakeServer({ "GET /practical-tasks/5/": offline, "GET /practical-tasks/5/students/": offline });
    render(<PracticalsTab siteId={9} teaching />);
    expect(await screen.findByText(/No signal: showing the copy kept on this phone/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Kezia Persaud/ })).toBeInTheDocument();
  });

  it("says when a task was never opened on this phone", async () => {
    window.location.hash = "#/sites/9/practicals/6/observe";
    fakeServer({ "GET /practical-tasks/6/": offline, "GET /practical-tasks/6/students/": offline });
    render(<PracticalsTab siteId={9} teaching />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Open it once with signal");
  });
});
