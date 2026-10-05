import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { fakeServer, offline } from "../test/fetch";
import {
  enqueue,
  flush,
  isNetworkError,
  outcomeOf,
  pending,
  pendingCount,
  saveQuizAnswer,
  sendPracticalWrite,
  startAutoFlush,
  submitAssignmentText,
  subscribe,
  useSendState,
} from "./offlineQueue";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("offline queue (item 4.02)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends a typed answer at once when there is a connection, and keeps nothing", async () => {
    const server = fakeServer({ "POST /assignments/3/submit/": { status: 201, body: { id: 8 } } });
    await expect(submitAssignmentText(3, "Soil report", "My answer")).resolves.toEqual({ queued: false, result: { id: 8 } });
    expect(server.calls[0].body).toEqual({ text: "My answer" });
    expect(pendingCount()).toBe(0);
  });

  it("keeps a typed answer on the device when the connection drops, and tells listeners", async () => {
    fakeServer({ "POST /assignments/3/submit/": offline });
    const heard = vi.fn();
    const stop = subscribe(heard);
    const sent = await submitAssignmentText(3, "Soil report", "My answer");
    expect(sent.queued).toBe(true);
    expect(pending()).toEqual([expect.objectContaining({ path: "/assignments/3/submit/", label: "Answer to Soil report" })]);
    expect(heard).toHaveBeenCalledTimes(1);
    stop();
  });

  it("does not try while the device reports no connection, and queues straight away", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    const server = fakeServer({});
    const sent = await saveQuizAnswer(5, 2, { choice: 1 });
    expect(sent.queued).toBe(true);
    expect(server.fetchMock).not.toHaveBeenCalled();
    await expect(flush()).resolves.toEqual({ sent: 0, rejected: 0 });
    expect(pendingCount()).toBe(1);
  });

  it("keeps only the latest answer to the same question, under the first one's mark", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    const first = await saveQuizAnswer(5, 2, { choice: 1 });
    await saveQuizAnswer(5, 3, { choice: 0 });
    const again = await saveQuizAnswer(5, 2, { choice: 4 });
    expect(pendingCount()).toBe(2);
    expect(first.queued && again.queued && again.item.id === first.item.id).toBe(true);
    const answer = pending().find((q) => q.path === "/quiz-attempts/5/answers/2/");
    expect(answer?.method).toBe("PUT");
    expect(answer?.body).toEqual({ response: { choice: 4 }, client_saved_at: expect.any(String) });
  });

  it("sends a practicals write with an Idempotency-Key, and the same key again when it is replayed", async () => {
    const server = fakeServer({ "POST /logbook/": [offline, { status: 201, body: { id: 4 } }] });
    const sent = await sendPracticalWrite("/logbook/", { task: "Weeding" }, "Logbook entry");
    expect(sent.queued).toBe(true);
    const key = server.calls[0].headers.get("Idempotency-Key");
    expect(key).toMatch(UUID);
    await expect(flush()).resolves.toEqual({ sent: 1, rejected: 0 });
    expect(server.calls[1].headers.get("Idempotency-Key")).toBe(key);
    expect(server.calls.map((c) => c.path)).toEqual(["/logbook/", "/logbook/"]);
  });

  it("does not queue a refusal: the page shows it", async () => {
    fakeServer({ "POST /assignments/3/submit/": { status: 409, body: { code: "closed", detail: "The deadline has passed." } } });
    await expect(submitAssignmentText(3, "Soil report", "Late")).rejects.toBeInstanceOf(ApiError);
    expect(pendingCount()).toBe(0);
  });

  it("sends queued writes in order when the connection returns, and marks each sent", async () => {
    const one = enqueue({ kind: "assignment", method: "POST", path: "/assignments/3/submit/", body: { text: "a" }, label: "One" });
    const two = enqueue({ kind: "quiz-answer", method: "PUT", path: "/quiz-attempts/5/answers/1/", body: { response: 1 }, label: "Two" });
    const server = fakeServer({
      "POST /assignments/3/submit/": { status: 201, body: {} },
      "PUT /quiz-attempts/5/answers/1/": { body: { saved: true } },
    });
    await expect(flush()).resolves.toEqual({ sent: 2, rejected: 0 });
    expect(server.calls.map((c) => `${c.method} ${c.path}`)).toEqual(["POST /assignments/3/submit/", "PUT /quiz-attempts/5/answers/1/"]);
    expect(outcomeOf(one.id)).toEqual({ state: "sent" });
    expect(outcomeOf(two.id)).toEqual({ state: "sent" });
    expect(pendingCount()).toBe(0);
  });

  it("stops at the first network failure and keeps the write for later", async () => {
    enqueue({ kind: "assignment", method: "POST", path: "/assignments/3/submit/", body: { text: "a" }, label: "One" });
    fakeServer({ "POST /assignments/3/submit/": offline });
    await expect(flush()).resolves.toEqual({ sent: 0, rejected: 0 });
    expect(pendingCount()).toBe(1);
  });

  it("drops a write the server refuses, saying why, so it is not retried for ever", async () => {
    const item = enqueue({ kind: "assignment", method: "POST", path: "/assignments/3/submit/", body: { text: "a" }, label: "One" });
    fakeServer({ "POST /assignments/3/submit/": { status: 409, body: { code: "already_marked", detail: "A marked submission cannot be replaced." } } });
    await expect(flush()).resolves.toEqual({ sent: 0, rejected: 1 });
    expect(outcomeOf(item.id)).toEqual({ state: "refused", detail: "A marked submission cannot be replaced." });
    expect(pendingCount()).toBe(0);
  });

  it("shows a write as waiting, then sent, as the queue changes", async () => {
    const item = enqueue({ kind: "assignment", method: "POST", path: "/assignments/3/submit/", body: { text: "a" }, label: "One" });
    const { result } = renderHook(() => useSendState(item.id));
    expect(result.current).toEqual({ state: "waiting" });
    fakeServer({ "POST /assignments/3/submit/": { status: 201, body: {} } });
    await act(async () => {
      await flush();
    });
    expect(result.current).toEqual({ state: "sent" });
    expect(renderHook(() => useSendState(null)).result.current).toBeNull();
  });

  it("flushes on start and again whenever the connection comes back", async () => {
    const server = fakeServer({ "POST /assignments/3/submit/": { status: 201, body: {} } });
    startAutoFlush();
    enqueue({ kind: "assignment", method: "POST", path: "/assignments/3/submit/", body: { text: "a" }, label: "One" });
    window.dispatchEvent(new Event("online"));
    await vi.waitFor(() => expect(pendingCount()).toBe(0));
    expect(server.calls).toHaveLength(1);
  });

  it("recognises a dropped connection, and survives storage it cannot read", () => {
    expect(isNetworkError(new TypeError("Failed to fetch"))).toBe(true);
    expect(isNetworkError(new Error("400"))).toBe(false);
    localStorage.setItem("gsa-lms.offline-queue", "{not json");
    expect(pendingCount()).toBe(0);
  });
});
