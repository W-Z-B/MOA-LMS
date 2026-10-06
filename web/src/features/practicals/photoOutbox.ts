/**
 * Photographs taken in the field without signal (items 3.12, 3.14 and 3.15).
 *
 * The record itself (an observation or a logbook entry) goes through the offline queue (app/offlineQueue.ts,
 * sendPracticalWrite) with its Idempotency-Key. A photograph cannot live in localStorage, so it waits here, in
 * the browser's IndexedDB, until the record it belongs to has been sent. Then:
 *
 * 1. the record is asked for again under the same key: the server sends back the answer it gave the first
 *    time (the record's id) and creates nothing (practicals.offline);
 * 2. the photographs are sent to that record under a key of their own, made once and kept with them, so a
 *    lost answer sent again cannot add them twice.
 *
 * Where a browser has no IndexedDB the photographs wait in the page's memory instead, and the screen says
 * to keep the page open until they are sent (keepsPhotosOffline).
 */

import { useEffect, useState } from "react";
import { ApiError, api } from "../../api/client";
import { isNetworkError, pending, subscribe as onQueueChange, type QueuedWrite, type Sent } from "../../app/offlineQueue";

export interface OutboxEntry {
  id: string;
  label: string;
  /** Where the photographs go once the record's id is known: "/observations/{id}/photos/". */
  photosPath: string;
  photoKey: string;
  /** The record's id, once known. */
  targetId: number | null;
  /** The queued record they wait for, and how to ask for its answer again. */
  queueId: string | null;
  recordPath: string | null;
  recordBody: unknown;
  recordKey: string | null;
  files: { name: string; type: string; blob: Blob }[];
  createdAt: string;
}

export type PhotoOutcome = { state: "sent"; count: number } | { state: "refused"; detail: string };

const DB = "gsa-lms-practicals";
const STORE = "photo-outbox";

/** Whether photographs survive closing the page on this browser. */
export const keepsPhotosOffline = typeof indexedDB !== "undefined";

interface Store {
  all(): Promise<OutboxEntry[]>;
  put(entry: OutboxEntry): Promise<void>;
  remove(id: string): Promise<void>;
}

function memoryStore(): Store {
  const items = new Map<string, OutboxEntry>();
  return {
    all: async () => [...items.values()].sort((a, b) => a.createdAt.localeCompare(b.createdAt)),
    put: async (entry) => void items.set(entry.id, entry),
    remove: async (id) => void items.delete(id),
  };
}

/* v8 ignore start -- IndexedDB exists only in a real browser; the Playwright journeys exercise it. */
function indexedStore(): Store {
  let opened: Promise<IDBDatabase> | null = null;
  const open = () =>
    (opened ??= new Promise((resolve, reject) => {
      const request = indexedDB.open(DB, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: "id" });
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    }));
  const run = async <T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => IDBRequest<T>) => {
    const db = await open();
    return new Promise<T>((resolve, reject) => {
      const request = work(db.transaction(STORE, mode).objectStore(STORE));
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  };
  return {
    all: async () =>
      ((await run("readonly", (s) => s.getAll())) as OutboxEntry[]).sort((a, b) => a.createdAt.localeCompare(b.createdAt)),
    put: async (entry) => void (await run("readwrite", (s) => s.put(entry))),
    remove: async (id) => void (await run("readwrite", (s) => s.delete(id))),
  };
}
/* v8 ignore stop */

let store: Store = keepsPhotosOffline ? indexedStore() : memoryStore();

/** For tests: start again with an empty store in memory. */
export function resetOutbox() {
  store = memoryStore();
  outcomes.clear();
  waiting = [];
}

const listeners = new Set<() => void>();
const outcomes = new Map<string, PhotoOutcome>();
/** The ids of the entries still waiting, kept for the hooks (the store itself is asynchronous). */
let waiting: { id: string; count: number }[] = [];

async function refresh() {
  try {
    waiting = (await store.all()).map((e) => ({ id: e.id, count: e.files.length }));
  } catch {
    waiting = [];
  }
  listeners.forEach((fn) => fn());
}

const newKey = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}-4000-8000-${Math.random().toString(16).slice(2, 14)}`;

function upload(entry: OutboxEntry, id: number) {
  const form = new FormData();
  entry.files.forEach((f) => form.append("photos", new File([f.blob], f.name, { type: f.type })));
  return api<unknown>(entry.photosPath.replace("{id}", String(id)), {
    method: "POST",
    body: form,
    headers: { "Idempotency-Key": entry.photoKey },
  });
}

const refusal = (err: unknown) => (err instanceof ApiError ? err.detail : "Not accepted.");

/**
 * Send the photographs taken with a record, or keep them until they can be. `sent` is what
 * sendPracticalWrite answered for the record. Returns the id to follow with usePhotoState, or null when
 * there were none. A refusal of the photographs themselves (a file too large) is thrown, for the page to show.
 */
export async function attachPhotos(
  sent: Sent<{ id: number }>,
  files: File[],
  { photosPath, label }: { photosPath: string; label: string },
): Promise<string | null> {
  if (files.length === 0) return null;
  const queued: QueuedWrite | null = sent.queued ? sent.item : null;
  const entry: OutboxEntry = {
    id: newKey(),
    label,
    photosPath,
    photoKey: newKey(),
    targetId: sent.queued ? null : sent.result.id,
    queueId: queued?.id ?? null,
    recordPath: queued?.path ?? null,
    recordBody: queued?.body ?? null,
    recordKey: queued?.idempotencyKey ?? null,
    files: files.map((f) => ({ name: f.name, type: f.type, blob: f })),
    createdAt: new Date().toISOString(),
  };
  if (!sent.queued && (typeof navigator === "undefined" || navigator.onLine !== false)) {
    try {
      await upload(entry, sent.result.id);
      outcomes.set(entry.id, { state: "sent", count: files.length });
      listeners.forEach((fn) => fn());
      return entry.id;
    } catch (err) {
      if (!isNetworkError(err)) throw err;
    }
  }
  await store.put(entry);
  await refresh();
  return entry.id;
}

let draining: Promise<void> | null = null;
let again = false;

/** Send what can be sent: photographs whose record has gone. Stops at the first network failure. */
export function drain(): Promise<void> {
  if (draining) {
    again = true;
    return draining;
  }
  draining = (async () => {
    do {
      again = false;
      await drainOnce();
    } while (again);
  })().finally(() => {
    draining = null;
  });
  return draining;
}

async function drainOnce() {
  if (typeof navigator !== "undefined" && navigator.onLine === false) return;
  const queued = new Set(pending().map((q) => q.id));
  for (const entry of await store.all()) {
    if (entry.targetId === null) {
      if (entry.queueId && queued.has(entry.queueId)) continue; // the record has not gone yet
      try {
        // The same request under the same key: the server answers as it did the first time.
        const answer = await api<{ id: number }>(entry.recordPath ?? "", {
          method: "POST",
          body: JSON.stringify(entry.recordBody),
          headers: entry.recordKey ? { "Idempotency-Key": entry.recordKey } : {},
        });
        entry.targetId = answer.id;
        await store.put(entry);
      } catch (err) {
        if (isNetworkError(err) || (err instanceof ApiError && err.code === "in_progress")) return;
        // The record itself was refused (the queue says why beside it): its photographs cannot go either.
        outcomes.set(entry.id, { state: "refused", detail: refusal(err) });
        await store.remove(entry.id);
        continue;
      }
    }
    try {
      await upload(entry, entry.targetId);
      outcomes.set(entry.id, { state: "sent", count: entry.files.length });
    } catch (err) {
      if (isNetworkError(err)) return;
      outcomes.set(entry.id, { state: "refused", detail: refusal(err) });
    }
    await store.remove(entry.id);
    await refresh();
  }
  await refresh();
}

let started = false;

/** Send waiting photographs now, after each write the offline queue sends, and whenever signal returns. */
export function startPhotoOutbox() {
  if (started) return;
  started = true;
  onQueueChange(() => void drain());
  window.addEventListener("online", () => void drain());
  void refresh().then(drain);
}

/** "waiting" (with how many), "sent" or "refused" for photographs kept by attachPhotos; null for none. */
export function usePhotoState(id: string | null): ({ state: "waiting"; count: number } | PhotoOutcome) | null {
  const [, setTick] = useState(0);
  useEffect(() => {
    const fn = () => setTick((t) => t + 1);
    listeners.add(fn);
    return () => void listeners.delete(fn);
  }, []);
  if (id === null) return null;
  const queued = waiting.find((w) => w.id === id);
  if (queued) return { state: "waiting", count: queued.count };
  return outcomes.get(id) ?? null;
}

/** How many photographs wait on this device, for a line on the practicals screens. */
export function useWaitingPhotos(): number {
  const [, setTick] = useState(0);
  useEffect(() => {
    const fn = () => setTick((t) => t + 1);
    listeners.add(fn);
    return () => void listeners.delete(fn);
  }, []);
  return waiting.reduce((n, w) => n + w.count, 0);
}
