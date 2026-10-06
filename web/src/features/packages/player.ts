/**
 * The web app's half of the package player (items 5.12, 5.13; packages/play.py has the other half).
 *
 * A package runs in a sandboxed frame with an origin of its own, so it can neither reach this page nor the
 * LMS's API. A SCORM page finds its SCORM API in its own window: scorm-again's cross-frame client, which the
 * LMS puts at the top of every page of the package. That client sends each call here by postMessage, where
 * scorm-again's run-time (Scorm12API or Scorm2004API) keeps the data and commits it to the LMS as the learner,
 * with the CSRF token, exactly as CrossFrameLMS does, but answering only the frame it opened.
 *
 * H5P content sends its xAPI statements here the same way; they go to the LMS's statement store with the
 * attempt's registration, which is how its result is recorded.
 */

import { post } from "../../api/client";
import type { Launched } from "../../api/types-packages";

/** The calls a package may make: the SCORM 1.2 and 2004 API, and the cache warming of the cross-frame client. */
export const ALLOWED = new Set([
  "LMSInitialize",
  "LMSFinish",
  "LMSGetValue",
  "LMSSetValue",
  "LMSCommit",
  "LMSGetLastError",
  "LMSGetErrorString",
  "LMSGetDiagnostic",
  "Initialize",
  "Terminate",
  "GetValue",
  "SetValue",
  "Commit",
  "GetLastError",
  "GetErrorString",
  "GetDiagnostic",
  "getFlattenedCMI",
]);
/** After these, the attempt's result may have changed on the server. */
const SAVING = new Set(["LMSCommit", "LMSFinish", "Commit", "Terminate"]);

interface Message {
  messageId: string;
  method: string;
  params?: unknown[];
  isHeartbeat?: boolean;
}

type Api = Record<string, unknown> & { loadFromJSON: (json: Record<string, unknown>, element?: string) => void };

function csrfToken(): string {
  return (
    document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="))
      ?.split("=")[1] ?? ""
  );
}

/** Whether a message came from the player frame, or from a frame inside it (a package's own frames). */
export function fromFrame(source: MessageEventSource | null, frame: HTMLIFrameElement | null): boolean {
  const target = frame?.contentWindow;
  if (!source || !target) return false;
  let step = source as Window;
  for (let depth = 0; depth < 10; depth += 1) {
    if (step === target) return true;
    if (!step.parent || step.parent === step) return false;
    step = step.parent;
  }
  return false;
}

const isMessage = (data: unknown): data is Message =>
  typeof data === "object" &&
  data !== null &&
  typeof (data as Message).messageId === "string" &&
  typeof (data as Message).method === "string" &&
  ((data as Message).params === undefined || Array.isArray((data as Message).params));

/**
 * How the run-time commits: always a synchronous request with the CSRF token, also for the commit that ends a
 * session. scorm-again sends that one with navigator.sendBeacon, for a page that is closing; here the page
 * that closes is the package's frame, never this one, and a beacon cannot carry the CSRF token.
 */
export class LmsCommits {
  processHttpRequest(url: string, params: unknown): { result: string; errorCode: number } {
    const xhr = new XMLHttpRequest();
    try {
      xhr.open("POST", url, false);
      xhr.setRequestHeader("Content-Type", "application/json");
      xhr.setRequestHeader("X-CSRFToken", csrfToken());
      xhr.send(JSON.stringify(params));
      const answer = JSON.parse(xhr.responseText) as { result?: boolean };
      return xhr.status === 200 && answer.result ? { result: "true", errorCode: 0 } : { result: "false", errorCode: 391 };
    } catch {
      return { result: "false", errorCode: 391 };
    }
  }

  updateSettings(): void {}
}

/** The run-time for a SCORM launch: scorm-again's API, loaded only when a package is opened. */
export async function scormRuntime(launched: Launched): Promise<Api> {
  const settings = {
    autocommit: true,
    autocommitSeconds: 30,
    lmsCommitUrl: launched.commit_url,
    dataCommitFormat: "json",
    xhrHeaders: { "X-CSRFToken": csrfToken() },
    httpService: new LmsCommits(),
    logLevel: 5,
  };
  if (launched.standard === "scorm12") {
    const { Scorm12API } = await import("scorm-again/scorm12");
    const api = new Scorm12API(settings) as unknown as Api;
    api.loadFromJSON(launched.cmi, "");
    return api;
  }
  const { Scorm2004API } = await import("scorm-again/scorm2004");
  const api = new Scorm2004API(settings) as unknown as Api;
  api.loadFromJSON(launched.cmi, "");
  return api;
}

/**
 * Answer the frame's SCORM calls with `api`, and pass on H5P statements. Returns a function that stops.
 * `onSaved` runs after a commit or the end of a session, when the attempt may have a new result.
 */
export function connect(
  frame: () => HTMLIFrameElement | null,
  launched: Launched,
  api: Api | null,
  onSaved: () => void,
): () => void {
  const listener = (event: MessageEvent) => {
    if (!fromFrame(event.source, frame())) return;
    const source = event.source as Window;
    const data = event.data as unknown;
    if (typeof data === "object" && data !== null && (data as { type?: string }).type === "gsa-xapi") {
      const statement = (data as { statement?: Record<string, unknown> }).statement;
      if (!statement || typeof statement !== "object") return;
      const context = (statement.context as Record<string, unknown> | undefined) ?? {};
      post("/xapi/statements/", { ...statement, context: { ...context, registration: launched.registration } })
        .then(onSaved)
        .catch(() => undefined); // a statement the LMS does not keep (another activity) changes nothing
      return;
    }
    if (!api || !isMessage(data)) return;
    const reply = (answer: Record<string, unknown>) => source.postMessage({ messageId: data.messageId, ...answer }, "*");
    if (data.isHeartbeat) return reply({ isHeartbeat: true });
    if (!ALLOWED.has(data.method) || typeof api[data.method] !== "function") {
      return reply({ error: { message: `Method not allowed: ${data.method}`, code: "101" } });
    }
    try {
      const result = (api[data.method] as (...args: unknown[]) => unknown).apply(api, data.params ?? []);
      reply({ result });
      if (SAVING.has(data.method)) onSaved();
    } catch (err) {
      reply({ error: { message: err instanceof Error ? err.message : "Unknown error" } });
    }
  };
  window.addEventListener("message", listener);
  return () => window.removeEventListener("message", listener);
}
