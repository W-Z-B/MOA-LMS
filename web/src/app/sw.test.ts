/**
 * The service worker (public/sw.js), run here with a stand-in for its global scope: reading a kept module with
 * no connection only for the person signed in (item 4.03, ADR 0011), part of a kept video for a player that
 * seeks, and push notices (item 4.04).
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { fakeCaches } from "../test/caches";

type Listener = (event: Record<string, unknown>) => void;

function worker() {
  const stores = fakeCaches();
  const listeners: Record<string, Listener> = {};
  const self = {
    location: { origin: "https://lms.test" },
    addEventListener: (type: string, listener: Listener) => (listeners[type] = listener),
    registration: { showNotification: vi.fn(async () => undefined) },
    clients: { matchAll: vi.fn(async () => []), openWindow: vi.fn(async () => null), claim: async () => undefined },
    skipWaiting: async () => undefined,
  };
  const network = vi.fn(async (): Promise<Response> => {
    throw new TypeError("Failed to fetch");
  });
  const source = readFileSync(resolve(__dirname, "../../public/sw.js"), "utf8");
  new Function("self", "caches", "fetch", source)(self, stores, network);

  /** What the worker answers for a request, or the error it gives. */
  async function ask(url: string, headers: Record<string, string> = {}): Promise<Response> {
    let answer: Promise<Response> | undefined;
    listeners.fetch({
      request: { url: `https://lms.test${url}`, method: "GET", mode: "cors", headers: new Headers(headers) },
      respondWith: (r: Promise<Response>) => (answer = r),
    });
    return answer!;
  }
  return { stores, listeners, self, network, ask };
}

describe("the service worker", () => {
  it("answers from the signed-in person's kept module only when the network cannot be reached", async () => {
    const { stores, ask, network } = worker();
    await (await stores.open("gsa-lms-offline-7")).put("/api/v1/content/11/", new Response('{"id":11}'));
    await expect(ask("/api/v1/content/11/")).rejects.toThrow("Failed to fetch"); // nobody signed in
    await (await stores.open("gsa-lms-owner")).put("/__owner", new Response("7"));
    expect(await (await ask("/api/v1/content/11/?offline=1")).json()).toEqual({ id: 11 });
    await expect(ask("/api/v1/content/99/")).rejects.toThrow(); // not kept
    await (await stores.open("gsa-lms-owner")).put("/__owner", new Response("8")); // someone else
    await expect(ask("/api/v1/content/11/")).rejects.toThrow();
    network.mockResolvedValueOnce(new Response('{"fresh":true}'));
    expect(await (await ask("/api/v1/content/11/")).json()).toEqual({ fresh: true }); // the network first
  });

  it("gives a player that seeks the part of a kept video it asks for", async () => {
    const { stores, ask } = worker();
    await (await stores.open("gsa-lms-owner")).put("/__owner", new Response("7"));
    const film = new Uint8Array(100).map((_, i) => i);
    await (await stores.open("gsa-lms-offline-7")).put(
      "/api/v1/videos/12/play/low/",
      new Response(film, { headers: { "Content-Type": "video/mp4" } }),
    );
    const part = await ask("/api/v1/videos/12/play/low/", { Range: "bytes=10-19" });
    expect(part.status).toBe(206);
    expect(part.headers.get("Content-Range")).toBe("bytes 10-19/100");
    expect([...new Uint8Array(await part.arrayBuffer())]).toEqual([10, 11, 12, 13, 14, 15, 16, 17, 18, 19]);
    expect((await ask("/api/v1/videos/12/play/low/", { Range: "bytes=-5" })).headers.get("Content-Range")).toBe("bytes 95-99/100");
    expect((await ask("/api/v1/videos/12/play/low/", { Range: "bytes=200-" })).status).toBe(416);
    expect((await ask("/api/v1/videos/12/play/low/")).status).toBe(200);
  });

  it("shows a push notice with its title, and opens its page when tapped", async () => {
    const { listeners, self } = worker();
    let shown: Promise<unknown> | undefined;
    listeners.push({ data: { json: () => ({ title: "Marked: Soil report", link: "/sites/4", tag: "gsa-lms-9" }) }, waitUntil: (p: Promise<unknown>) => (shown = p) });
    await shown;
    expect(self.registration.showNotification).toHaveBeenCalledWith("Marked: Soil report", expect.objectContaining({ tag: "gsa-lms-9", data: { link: "/sites/4" } }));
    let opened: Promise<unknown> | undefined;
    listeners.notificationclick({ notification: { close: () => undefined, data: { link: "/sites/4" } }, waitUntil: (p: Promise<unknown>) => (opened = p) });
    await opened;
    expect(self.clients.openWindow).toHaveBeenCalledWith("/#/sites/4");
    // A notice that is not ours to read, or a link that leaves the app, still opens only the app.
    listeners.push({ data: { json: () => ({ title: "x", link: "https://elsewhere.example" }) }, waitUntil: (p: Promise<unknown>) => (shown = p) });
    await shown;
    expect(self.registration.showNotification).toHaveBeenLastCalledWith("x", expect.objectContaining({ data: { link: "/" } }));
  });
});
