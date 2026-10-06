/** A stand-in for the server: answers fetch calls by method and path, and records what was sent. */

import { vi } from "vitest";

export interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Headers;
}

/** `raw` sends text as it is, for a proxy error page that is not JSON. */
type Answer = { status?: number; body?: unknown; raw?: string } | (() => never);

/**
 * Install a fake fetch. Keys are "METHOD /path" as the client writes them after /api/v1, for example
 * "POST /auth/login/". A function answer runs instead, so a test can throw a network error.
 */
export function fakeServer(routes: Record<string, Answer | Answer[]>) {
  const calls: Call[] = [];
  const queues = new Map(Object.entries(routes).map(([k, v]) => [k, Array.isArray(v) ? [...v] : [v]]));

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input).replace(/^\/api\/v1/, "");
    const method = (init.method ?? "GET").toUpperCase();
    const headers = new Headers(init.headers);
    const body = typeof init.body === "string" ? JSON.parse(init.body) : init.body;
    calls.push({ method, path: url, body, headers });
    const key = `${method} ${url}`;
    const queue = queues.get(key) ?? queues.get(`${method} ${url.split("?")[0]}`);
    if (!queue || queue.length === 0) return new Response(JSON.stringify({ detail: `No answer for ${key}` }), { status: 599 });
    const answer = queue.length > 1 ? queue.shift()! : queue[0];
    if (typeof answer === "function") return answer();
    const status = answer.status ?? 200;
    if (answer.raw !== undefined) return new Response(answer.raw, { status, headers: { "Content-Type": "text/html" } });
    return new Response(status === 204 ? null : JSON.stringify(answer.body ?? {}), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });

  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

/** What a dropped connection looks like to fetch. */
export const offline = () => {
  throw new TypeError("Failed to fetch");
};
