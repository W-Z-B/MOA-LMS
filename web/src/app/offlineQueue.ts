/**
 * Offline queue for writes made without a connection (item 4.02, ported from the HRMS).
 *
 * Only writes that are safe to send twice are queued, so a write whose answer was lost on the way can be sent
 * again without doing anything twice:
 * - a student's typed answer to an assignment (handing in again replaces the work until it is marked);
 * - a quiz answer (each answer is saved with PUT, and the server keeps the newest by the device's clock);
 * - practical observations and logbook entries (each carries an Idempotency-Key the server remembers);
 * - messages, and a register taken on a phone (item 4.11, 4.15: also with an Idempotency-Key).
 *
 * Items live in localStorage (per device, per browser) and are replayed in order when the connection
 * returns. A file cannot be kept here: work with a file attached needs a connection. The page shows each
 * write as "waiting to send", then "sent" (or why the server would not take it).
 */

import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";

export type WriteKind = "assignment" | "quiz-answer" | "practical" | "message" | "register";

/** Writes the server de-duplicates by their Idempotency-Key: one key is made for every try of the write. */
const KEYED: readonly WriteKind[] = ["practical", "message", "register"];

export interface QueuedWrite {
  id: string;
  kind: WriteKind;
  method: "POST" | "PUT";
  path: string;
  body: unknown;
  /** What it is, in a few words, for the list of what waits: "Answer to Soil sampling report". */
  label: string;
  /** Sent as the Idempotency-Key header, the same on every try. */
  idempotencyKey?: string;
  createdAt: string;
}

export type Outcome = { state: "sent" } | { state: "refused"; detail: string };

export interface FlushResult {
  sent: number;
  rejected: number;
}

const KEY = "gsa-lms.offline-queue";
const listeners = new Set<() => void>();
/** What happened to each write sent from the queue in this visit, for the "sent" mark beside it. */
const outcomes = new Map<string, Outcome>();

function read(): QueuedWrite[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}

function write(items: QueuedWrite[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(items));
  } catch {
    /* storage unavailable: the item is lost and the caller shows the error */
  }
  notify();
}

const notify = () => listeners.forEach((fn) => fn());

export const isNetworkError = (err: unknown) => err instanceof TypeError;

const newId = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

function request(item: Pick<QueuedWrite, "method" | "path" | "body" | "idempotencyKey">) {
  const headers: Record<string, string> = {};
  if (item.idempotencyKey) headers["Idempotency-Key"] = item.idempotencyKey;
  return api<unknown>(item.path, { method: item.method, body: JSON.stringify(item.body), headers });
}

/**
 * Keep a write to send later. A later write to the same address replaces one still waiting, so a quiz
 * answer changed twice without signal is sent once, as last given.
 */
export function enqueue(item: Omit<QueuedWrite, "id" | "createdAt"> & { id?: string }): QueuedWrite {
  const items = read();
  const same = item.method === "PUT" ? items.find((q) => q.method === "PUT" && q.path === item.path) : undefined;
  // The replaced write keeps its id, so the "waiting to send" mark beside it stays where it is.
  const queued: QueuedWrite = { ...item, id: same?.id ?? item.id ?? newId(), createdAt: new Date().toISOString() };
  write([...items.filter((q) => q !== same), queued]);
  return queued;
}

export type Sent<T> = { queued: false; result: T } | { queued: true; item: QueuedWrite };

/**
 * Send now if there is a connection; keep it for later if there is not. A refusal from the server (a
 * deadline passed, a mark already given) is not queued: it is thrown, for the page to show.
 */
export async function sendOrQueue<T>(item: Omit<QueuedWrite, "id" | "createdAt">): Promise<Sent<T>> {
  const prepared = { ...item, idempotencyKey: KEYED.includes(item.kind) ? (item.idempotencyKey ?? newId()) : undefined };
  if (typeof navigator !== "undefined" && navigator.onLine === false) return { queued: true, item: enqueue(prepared) };
  try {
    return { queued: false, result: (await request(prepared)) as T };
  } catch (err) {
    if (isNetworkError(err)) return { queued: true, item: enqueue(prepared) };
    throw err;
  }
}

/**
 * A student's typed answer to an assignment. Work with a file attached is sent only with a connection. The
 * server's clock decides whether it is late; the device's time goes with it, for teaching staff to see.
 */
export const submitAssignmentText = <T>(assignmentId: number, title: string, text: string, integrityAccepted = false) =>
  sendOrQueue<T>({
    kind: "assignment",
    method: "POST",
    path: `/assignments/${assignmentId}/submit/`,
    // The academic integrity statement, when the assignment asks for it, is accepted with the answer (3.22).
    body: { text, client_submitted_at: new Date().toISOString(), ...(integrityAccepted ? { integrity_accepted: true } : {}) },
    label: `Answer to ${title}`,
  });

/** One quiz answer, saved as it is given, with the device's time so an older answer never wins. */
export const saveQuizAnswer = <T>(attemptId: number, position: number, response: unknown, label = `Quiz answer ${position}`) =>
  sendOrQueue<T>({
    kind: "quiz-answer",
    method: "PUT",
    path: `/quiz-attempts/${attemptId}/answers/${position}/`,
    body: { response, client_saved_at: new Date().toISOString() },
    label,
  });

/** An observation, a logbook entry or another practicals write: one Idempotency-Key for every try. */
export const sendPracticalWrite = <T>(path: string, body: Record<string, unknown>, label: string) =>
  sendOrQueue<T>({ kind: "practical", method: "POST", path, body, label });

export const pending = () => read();
export const pendingCount = () => read().length;
export const outcomeOf = (id: string) => outcomes.get(id);

export function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

let flushing = false;

/** Replay queued writes in order. Stops at the first network failure; drops writes the server refuses. */
export async function flush(): Promise<FlushResult> {
  const result: FlushResult = { sent: 0, rejected: 0 };
  if (flushing || !navigator.onLine) return result;
  flushing = true;
  try {
    let items = read();
    while (items.length > 0) {
      const item = items[0];
      try {
        await request(item);
        outcomes.set(item.id, { state: "sent" });
        result.sent += 1;
      } catch (err) {
        if (isNetworkError(err)) break; // still offline; keep it
        // A validation or permission refusal: say so beside the write, and do not retry it for ever.
        outcomes.set(item.id, { state: "refused", detail: err instanceof ApiError ? err.detail : "Not accepted." });
        result.rejected += 1;
      }
      items = read().filter((q) => q.id !== item.id);
      write(items);
    }
  } finally {
    flushing = false;
  }
  return result;
}

export function startAutoFlush() {
  window.addEventListener("online", () => void flush());
  void flush();
}

/** What waits to be sent, kept current as writes are queued and sent. */
export function usePending(): QueuedWrite[] {
  const [items, setItems] = useState<QueuedWrite[]>(read);
  useEffect(() => subscribe(() => setItems(read())), []);
  return items;
}

/** "waiting", "sent" or "refused" for one queued write, as it changes; null for none. */
export function useSendState(id: string | null): { state: "waiting" } | Outcome | null {
  const items = usePending();
  if (id === null) return null;
  if (items.some((q) => q.id === id)) return { state: "waiting" };
  return outcomes.get(id) ?? null;
}
