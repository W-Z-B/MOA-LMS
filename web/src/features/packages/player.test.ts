import { describe, expect, it, vi } from "vitest";
import { connect, fromFrame } from "./player";
import type { Launched } from "../../api/types-packages";

const launched = { registration: "r-1", standard: "scorm2004" } as unknown as Launched;

describe("the player's bridge (items 5.12, 5.13)", () => {
  it("answers the player frame and the frames inside it, and nothing else", () => {
    const frame = document.createElement("iframe");
    document.body.appendChild(frame);
    const inner = { parent: frame.contentWindow } as unknown as Window;
    const stranger = { parent: window } as unknown as Window;
    expect(fromFrame(frame.contentWindow, frame)).toBe(true);
    expect(fromFrame(inner, frame)).toBe(true);
    expect(fromFrame(stranger, frame)).toBe(false);
    expect(fromFrame(null, frame)).toBe(false);
    expect(fromFrame(frame.contentWindow, null)).toBe(false);
  });

  it("reports a run-time error to the package and stops when asked", () => {
    const frame = document.createElement("iframe");
    document.body.appendChild(frame);
    const api = {
      loadFromJSON: vi.fn(),
      Commit: vi.fn(() => {
        throw new Error("Commit failed");
      }),
      GetValue: vi.fn(() => "completed"),
    };
    const saved = vi.fn();
    const stop = connect(() => frame, launched, api, saved);
    const reply = vi.spyOn(frame.contentWindow!, "postMessage");
    window.dispatchEvent(new MessageEvent("message", { data: { messageId: "1", method: "Commit", params: [""] }, source: frame.contentWindow }));
    expect(reply).toHaveBeenCalledWith({ messageId: "1", error: { message: "Commit failed" } }, "*");
    window.dispatchEvent(new MessageEvent("message", { data: { messageId: "2", method: "GetValue", params: ["cmi.completion_status"] }, source: frame.contentWindow }));
    expect(reply).toHaveBeenCalledWith({ messageId: "2", result: "completed" }, "*");
    window.dispatchEvent(new MessageEvent("message", { data: "not a call", source: frame.contentWindow }));
    window.dispatchEvent(new MessageEvent("message", { data: { type: "gsa-xapi" }, source: frame.contentWindow }));
    expect(reply).toHaveBeenCalledTimes(2);
    stop();
    window.dispatchEvent(new MessageEvent("message", { data: { messageId: "3", method: "GetValue" }, source: frame.contentWindow }));
    expect(reply).toHaveBeenCalledTimes(2);
    expect(saved).not.toHaveBeenCalled();
  });
});

vi.mock("scorm-again/scorm2004", () => ({
  Scorm2004API: class {
    settings: Record<string, unknown>;
    loaded: unknown = null;
    constructor(settings: Record<string, unknown>) {
      this.settings = settings;
    }
    loadFromJSON(json: unknown) {
      this.loaded = json;
    }
  },
}));

describe("the SCORM 2004 run-time", () => {
  it("commits as the learner, with the CSRF token, and starts from the LMS's data", async () => {
    const { scormRuntime } = await import("./player");
    document.cookie = "csrftoken=abc123";
    const api = (await scormRuntime({ ...launched, commit_url: "/api/v1/package-attempts/1/commit/?sco=a", cmi: { learner_id: "S1" } })) as unknown as {
      settings: Record<string, unknown>;
      loaded: unknown;
    };
    expect(api.settings).toMatchObject({ lmsCommitUrl: "/api/v1/package-attempts/1/commit/?sco=a", xhrHeaders: { "X-CSRFToken": "abc123" }, autocommit: true });
    expect(api.loaded).toEqual({ learner_id: "S1" });
  });
});
