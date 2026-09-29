/**
 * Minimal API client: same-origin fetch, JSON, CSRF header for unsafe methods, typed errors.
 * No third-party dependency; TanStack Query can wrap this later per ADR 0001.
 */

export class ApiError extends Error {
  status: number;
  code: string;
  detail: string;
  fields?: Record<string, string[]>;

  constructor(status: number, code: string, detail: string, fields?: Record<string, string[]>) {
    super(detail);
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.fields = fields;
  }
}

function csrfToken(): string | undefined {
  return document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="))
    ?.split("=")[1];
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const token = csrfToken();
    if (token) headers.set("X-CSRFToken", token);
  }
  const response = await fetch(`/api/v1${path}`, { ...init, method, headers, credentials: "same-origin" });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const fields = typeof body === "object" && !("detail" in body) ? body : undefined;
    throw new ApiError(response.status, body.code ?? "error", body.detail ?? "Request failed", fields);
  }
  return body as T;
}

const encode = (data: unknown) => (data instanceof FormData ? data : JSON.stringify(data));

export const get = <T>(path: string) => api<T>(path);
export const post = <T>(path: string, data?: unknown) =>
  api<T>(path, { method: "POST", body: data === undefined ? undefined : encode(data) });
export const patch = <T>(path: string, data: unknown) => api<T>(path, { method: "PATCH", body: encode(data) });

/** First human-readable message from an API error, preferring field errors. */
export function errorMessage(err: unknown, fallback = "Something went wrong."): string {
  if (err instanceof ApiError) {
    const field = err.fields ? Object.entries(err.fields)[0] : undefined;
    return field ? `${field[0].replace(/_/g, " ")}: ${[field[1]].flat()[0]}` : err.detail;
  }
  return fallback;
}
