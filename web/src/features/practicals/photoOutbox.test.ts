import { describe, expect, it, beforeEach } from "vitest";
import { flush, sendPracticalWrite } from "../../app/offlineQueue";
import { fakeServer, offline } from "../../test/fetch";
import { localDate, localDateTime, windowText } from "./helpers";
import { attachPhotos, drain, resetOutbox } from "./photoOutbox";
import { logbookView, practicalsPath, practicalsView } from "./routes";
import { clearFieldCopies, keepCopy, readCopy } from "./fieldCopy";
import { jpeg, students, task } from "./testData";

beforeEach(() => resetOutbox());

const options = { photosPath: "/observations/{id}/photos/", label: "Photos" };

describe("photos kept on the phone (items 3.12, 3.14 and 3.15)", () => {
  it("keeps photos whose upload lost the signal, and sends them later under the same key", async () => {
    const { calls } = fakeServer({ "POST /observations/9/photos/": [offline, { status: 201, body: {} }] });
    await attachPhotos({ queued: false, result: { id: 9 } }, [jpeg()], options);
    const [first] = calls;
    await drain();
    expect(calls).toHaveLength(2);
    expect(calls[1].headers.get("Idempotency-Key")).toBe(first.headers.get("Idempotency-Key"));
    await drain();
    expect(calls).toHaveLength(2); // sent once
  });

  it("throws a refusal of the photos themselves, for the page to show", async () => {
    fakeServer({ "POST /observations/9/photos/": { status: 400, body: { photos: ["Send a photograph (JPG, PNG, WEBP or HEIC) or a PDF."] } } });
    await expect(attachPhotos({ queued: false, result: { id: 9 } }, [jpeg()], options)).rejects.toThrow();
    expect(await attachPhotos({ queued: false, result: { id: 9 } }, [], options)).toBeNull();
  });

  it("drops the photos of a record the server refused, and says why", async () => {
    const { calls } = fakeServer({
      "POST /practical-tasks/5/observations/": [
        offline,
        { status: 400, body: { code: "client_time_too_old", detail: "More than 7 days ago." } },
      ],
    });
    const sent = await sendPracticalWrite<{ id: number }>("/practical-tasks/5/observations/", { student: 1 }, "Observation");
    await attachPhotos(sent, [jpeg()], options);
    await flush();
    await drain();
    // The queue's send and the photos' one question, both refused; no photo upload.
    expect(calls.filter((c) => c.path.includes("photos"))).toHaveLength(0);
  });

  it("waits while the record is still queued, and while there is no signal", async () => {
    const { calls } = fakeServer({ "POST /logbook/": offline });
    const sent = await sendPracticalWrite<{ id: number }>("/logbook/", { site: 9 }, "Entry");
    await attachPhotos(sent, [jpeg()], { photosPath: "/logbook/{id}/photos/", label: "Photos" });
    await drain();
    expect(calls).toHaveLength(1); // the record is still waiting, so nothing more was asked
  });
});

describe("addresses inside the tabs (item 2.10)", () => {
  it("reads each practicals and logbook screen from the address", () => {
    expect(practicalsView("/sites/4/practicals")).toEqual({ view: "tasks" });
    expect(practicalsView("/sites/4/practicals/12")).toEqual({ view: "task", taskId: 12 });
    expect(practicalsView("/sites/4/practicals/12/observe")).toEqual({ view: "observe", taskId: 12, personId: null });
    expect(practicalsView("/sites/4/practicals/12/observe/55")).toEqual({ view: "observe", taskId: 12, personId: 55 });
    expect(practicalsView("/sites/4/practicals/competency/55")).toEqual({ view: "competency", personId: 55 });
    expect(practicalsView("/sites/4/practicals/portfolio")).toEqual({ view: "portfolio" });
    expect(practicalsView("/sites/4/practicals/nonsense")).toEqual({ view: "tasks" });
    expect(logbookView("/sites/4/logbook")).toEqual({ view: "list" });
    expect(logbookView("/sites/4/logbook/new")).toEqual({ view: "new" });
    expect(logbookView("/sites/4/logbook/7")).toEqual({ view: "edit", entryId: 7 });
    expect(practicalsPath(4, 12, "observe", 55)).toBe("/sites/4/practicals/12/observe/55");
  });

  it("writes dates for the phone's inputs and a task's window in words", () => {
    const at = new Date(2026, 9, 5, 7, 4);
    expect(localDateTime(at)).toBe("2026-10-05T07:04");
    expect(localDate(at)).toBe("2026-10-05");
    expect(windowText({ opens_at: null, closes_at: null })).toBe("no closing date");
    expect(windowText({ opens_at: "2026-10-01T12:00:00Z", closes_at: null })).toMatch(/^opens 01\/10\/2026/);
    expect(windowText({ opens_at: "2026-10-01T12:00:00Z", closes_at: "2026-10-09T12:00:00Z" })).toMatch(/^open 01\/10\/2026.* to 09\/10\/2026/);
  });
});

describe("the class list kept for the field (ADR 0011)", () => {
  it("is removed on signing out, and nothing else is", () => {
    keepCopy({ task, students, at: "2026-10-05T12:00:00Z" });
    localStorage.setItem("gsa-lms.campus", "MRP");
    expect(readCopy(5)?.students).toHaveLength(2);
    clearFieldCopies();
    expect(readCopy(5)).toBeNull();
    expect(localStorage.getItem("gsa-lms.campus")).toBe("MRP");
  });
});
