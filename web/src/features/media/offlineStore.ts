/**
 * Modules kept on this device to read offline (item 4.03; ADR 0011, point 4).
 *
 * The server lists what a module needs (GET /offline/modules/{id}/): its pages, documents and the pictures on
 * its pages, and each video in the low copy with its poster frame and captions. The space it takes is shown
 * before anything is kept. What is kept goes into a cache that belongs to the signed-in person,
 * "gsa-lms-offline-<account id>"; the service worker (public/sw.js) answers from it only when the network
 * cannot be reached, and only while that person is signed in. Signing out removes it. When someone else
 * signs in on a shared phone, what an earlier person left is removed too: reading material is never shown
 * under another person's session.
 */

import { get } from "../../api/client";

export const OFFLINE_PREFIX = "gsa-lms-offline-";
const OWNER_CACHE = "gsa-lms-owner";
const OWNER_KEY = "/__owner";
const INDEX_KEY = "/__kept/index.json";
/** Files are fetched a few at a time: a weak line is not flooded, and progress is shown as they arrive. */
const AT_ONCE = 3;

export interface OfflineFile {
  url: string;
  kind: "data" | "page" | "document" | "picture" | "video" | "poster" | "captions";
  title: string;
  size: number;
}

export interface OfflineManifest {
  module: number;
  title: string;
  site: number;
  site_title: string;
  files: OfflineFile[];
  total_bytes: number;
  left_out: string[];
}

/** A module kept on this device, as the Downloaded list shows it. */
export interface KeptModule {
  module: number;
  title: string;
  site: number;
  siteTitle: string;
  bytes: number;
  files: number;
  keptAt: string;
  /** Every address kept for it, so removing it removes exactly those. */
  urls: string[];
}

let owner: number | null = null;
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((listener) => listener());

export function onKeptChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Whether this browser can keep files at all (the Cache API needs a secure page). */
export const canKeep = () => typeof caches !== "undefined";

const cacheName = (id: number) => `${OFFLINE_PREFIX}${id}`;
const api = (url: string) => `/api/v1${url}`;

/**
 * Who is signed in on this device: the service worker answers only from their cache. A new person signing
 * in removes what anyone else kept here; nobody signed in (null) leaves the caches until their owner returns.
 */
export async function setOfflineOwner(id: number | null): Promise<void> {
  owner = id;
  if (!canKeep()) return;
  const store = await caches.open(OWNER_CACHE);
  if (id === null) await store.delete(OWNER_KEY);
  else await store.put(OWNER_KEY, new Response(String(id)));
  if (id !== null) {
    const others = (await caches.keys()).filter((k) => k.startsWith(OFFLINE_PREFIX) && k !== cacheName(id));
    await Promise.all(others.map((k) => caches.delete(k)));
  }
  changed();
}

/** Remove everything the signed-in person kept, at sign-out. */
export async function clearOffline(): Promise<void> {
  if (!canKeep()) return;
  const keys = await caches.keys();
  await Promise.all(keys.filter((k) => k.startsWith(OFFLINE_PREFIX)).map((k) => caches.delete(k)));
  await (await caches.open(OWNER_CACHE)).delete(OWNER_KEY);
  owner = null;
  changed();
}

async function mine(): Promise<Cache | null> {
  return owner === null || !canKeep() ? null : caches.open(cacheName(owner));
}

/** The modules the signed-in person kept here. */
export async function keptModules(): Promise<KeptModule[]> {
  const cache = await mine();
  const index = await cache?.match(INDEX_KEY);
  if (!index) return [];
  try {
    return (await index.json()) as KeptModule[];
  } catch {
    return [];
  }
}

async function writeIndex(cache: Cache, kept: KeptModule[]) {
  await cache.put(INDEX_KEY, new Response(JSON.stringify(kept), { headers: { "Content-Type": "application/json" } }));
  changed();
}

/** What keeping a module will take, before anything is kept. */
export const describeModule = (moduleId: number) => get<OfflineManifest>(`/offline/modules/${moduleId}/`);

/** Raised when a file of the module could not be fetched; nothing of the module is left half kept. */
export class KeepFailed extends Error {}

/**
 * Keep every file of the module, reporting the bytes fetched so far. Fetched with offline=1, so keeping a
 * module records no progress; kept under the address the app reads it by.
 */
export async function keepModule(manifest: OfflineManifest, onProgress?: (bytes: number) => void): Promise<KeptModule> {
  const cache = await mine();
  if (!cache) throw new KeepFailed("Sign in to keep a module on this device.");
  let fetched = 0;
  const queue = [...manifest.files];
  const kept: string[] = [];
  let failed = false;
  async function worker() {
    for (let file = queue.shift(); file && !failed; file = queue.shift()) {
      const join = file.url.includes("?") ? "&" : "?";
      let response: Response;
      try {
        response = await fetch(api(`${file.url}${join}offline=1`), { credentials: "same-origin" });
      } catch {
        failed = true;
        throw new KeepFailed("The connection was lost. Try again when you have signal.");
      }
      if (!response.ok) {
        failed = true;
        throw new KeepFailed(`“${file.title}” could not be fetched. Try again later.`);
      }
      const body = await response.arrayBuffer();
      await cache!.put(api(file.url), new Response(body, { headers: { "Content-Type": response.headers.get("Content-Type") ?? "" } }));
      kept.push(api(file.url));
      fetched += body.byteLength;
      onProgress?.(fetched);
    }
  }
  // Every worker finishes before anything is cleared, so nothing is put back after the clearing.
  const results = await Promise.allSettled(Array.from({ length: AT_ONCE }, worker));
  const refused = results.find((r): r is PromiseRejectedResult => r.status === "rejected");
  if (refused) {
    const still = new Set((await keptModules()).flatMap((m) => m.urls));
    await Promise.all(kept.filter((url) => !still.has(url)).map((url) => cache.delete(url)));
    throw refused.reason;
  }
  const entry: KeptModule = {
    module: manifest.module,
    title: manifest.title,
    site: manifest.site,
    siteTitle: manifest.site_title,
    bytes: fetched,
    files: manifest.files.length,
    keptAt: new Date().toISOString(),
    urls: kept,
  };
  await writeIndex(cache, [...(await keptModules()).filter((m) => m.module !== manifest.module), entry]);
  return entry;
}

/** Remove one kept module; files another kept module also uses (the course's contents) stay. */
export async function removeModule(moduleId: number): Promise<void> {
  const cache = await mine();
  if (!cache) return;
  const all = await keptModules();
  const leaving = all.find((m) => m.module === moduleId);
  const rest = all.filter((m) => m.module !== moduleId);
  const still = new Set(rest.flatMap((m) => m.urls));
  await Promise.all((leaving?.urls ?? []).filter((url) => !still.has(url)).map((url) => cache.delete(url)));
  await writeIndex(cache, rest);
}

/** Space left on the device for the app, when the browser says. */
export async function spaceLeft(): Promise<number | null> {
  try {
    const { quota, usage } = await navigator.storage.estimate();
    return quota !== undefined && usage !== undefined ? quota - usage : null;
  } catch {
    return null;
  }
}
