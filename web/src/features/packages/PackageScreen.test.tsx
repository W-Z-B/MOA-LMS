import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../../test/fetch";
import type { Launched } from "../../api/types-packages";
import PackageScreen from "./PackageScreen";
import { attempt, page, pkg, siteAs } from "./fixtures";

const runtime = vi.hoisted(() => ({ calls: [] as string[], loaded: [] as unknown[] }));

vi.mock("scorm-again/scorm12", () => ({
  Scorm12API: class {
    settings: unknown;
    constructor(settings: unknown) {
      this.settings = settings;
    }
    loadFromJSON(json: unknown) {
      runtime.loaded.push(json);
    }
    LMSInitialize() {
      runtime.calls.push("LMSInitialize");
      return "true";
    }
    LMSCommit() {
      runtime.calls.push("LMSCommit");
      return "true";
    }
    LMSGetValue(name: string) {
      return name === "cmi.core.student_id" ? "S2026901" : "";
    }
  },
}));

function launched(more: Partial<Launched> = {}): Launched {
  return {
    attempt: attempt(1),
    sco: { id: "i1", title: "Taking a sample", href: "index.html", parameters: "" },
    standard: "scorm12",
    play_url: "/api/play/token/index.html",
    commit_url: "/api/v1/package-attempts/1/commit/?sco=i1",
    cmi: { core: { student_id: "S2026901", entry: "ab-initio" } },
    activity: "https://lms.example/xapi/activities/packages/3",
    registration: "5b9e4a3c-1111-4222-8333-444455556661",
    ...more,
  };
}

function open(role: "lecturer" | "student", routes: Record<string, unknown> = {}, found = pkg()) {
  const server = fakeServer({
    "GET /packages/": { body: page([found]) },
    "GET /sites/9/contents/": { body: siteAs(role) },
    "GET /packages/3/attempts/": { body: [attempt(1, { learner: "Kezia Persaud", student_no: "S2026901", completion: "completed", success: "passed", score: "0.8500", score_percent: "85.0", last_commit_at: "2026-10-02T10:00:00Z" })] },
    ...(routes as Record<string, { body?: unknown }>),
  });
  render(<PackageScreen siteId={9} itemId={12} />);
  return server;
}

/** Send a message as the package's frame would. */
function fromPackage(data: unknown) {
  const frame = screen.getByTitle("Soil testing: the package") as HTMLIFrameElement;
  const reply = vi.spyOn(frame.contentWindow!, "postMessage");
  window.dispatchEvent(new MessageEvent("message", { data, source: frame.contentWindow }));
  return reply;
}

describe("a package for a student (items 5.12, 5.13)", () => {
  it("opens the package in a sandboxed frame and answers its SCORM calls", async () => {
    const { calls } = open("student", { "POST /packages/3/launch/": { body: launched() } });
    expect(await screen.findByRole("heading", { name: "Soil testing", level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/counts in coursework \(weight 2.00\) · 2 attempts allowed/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ sco: "", new_attempt: false });
    const frame = await screen.findByTitle("Soil testing: the package");
    expect(frame).toHaveAttribute("src", "/api/play/token/index.html");
    expect(frame.getAttribute("sandbox")).not.toContain("allow-same-origin");
    expect(frame).toHaveAttribute("referrerpolicy", "no-referrer");
    await waitFor(() => expect(runtime.loaded).toContainEqual({ core: { student_id: "S2026901", entry: "ab-initio" } }));
    const reply = fromPackage({ messageId: "m1", method: "LMSInitialize", params: [""] });
    expect(reply).toHaveBeenCalledWith({ messageId: "m1", result: "true" }, "*");
    const refused = fromPackage({ messageId: "m2", method: "constructor" });
    expect(refused).toHaveBeenCalledWith({ messageId: "m2", error: { message: "Method not allowed: constructor", code: "101" } }, "*");
    const heartbeat = fromPackage({ messageId: "m3", method: "LMSGetValue", isHeartbeat: true });
    expect(heartbeat).toHaveBeenCalledWith({ messageId: "m3", isHeartbeat: true }, "*");
    // A message from anywhere else is not answered.
    const elsewhere = vi.fn();
    window.dispatchEvent(new MessageEvent("message", { data: { messageId: "x", method: "LMSCommit" }, source: { postMessage: elsewhere } as unknown as Window }));
    expect(elsewhere).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Close the package" }));
    expect(screen.getByRole("status")).toHaveTextContent("What you did has been saved.");
  });

  it("continues an open attempt, offers a new one once finished, and says what counts", async () => {
    const finished = pkg({
      my_attempts: [attempt(1, { completion: "completed", success: "failed", score: "0.4000", score_percent: "40.0" })],
      attempts_left: 1,
      my_result: { fraction: "0.4000", state: "graded" },
    });
    const { calls } = open("student", { "POST /packages/3/launch/": { body: launched({ attempt: attempt(2) }) } }, finished);
    expect(await screen.findByText("Completed · Not passed · 40.0%")).toBeInTheDocument();
    expect(screen.getByText("40.0% counts in your coursework (your best attempt).")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start a new attempt" }));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ sco: "", new_attempt: true });
    expect(await screen.findByRole("status")).toHaveTextContent("Attempt 2.");
  });

  it("says why a package cannot be opened", async () => {
    open("student", { "POST /packages/3/launch/": { status: 409, body: { code: "no_attempts_left", detail: "You have used all 2 attempts at this package." } } });
    await userEvent.click(await screen.findByRole("button", { name: "Start" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You have used all 2 attempts");
  });

  it("passes an H5P exercise's statements to the LMS with the attempt's registration", async () => {
    const h5p = pkg({ standard: "h5p", version_label: "H5P H5P.GSATest 1.0", scos: [{ id: "h5p", title: "Crop quiz", href: "", parameters: "" }] });
    const { calls } = open(
      "student",
      {
        "POST /packages/3/launch/": { body: launched({ standard: "h5p", play_url: "/api/play/token/", commit_url: "", cmi: {} }) },
        "POST /xapi/statements/": { body: ["id-1"] },
      },
      h5p,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Start" }));
    await screen.findByTitle("Soil testing: the package");
    fromPackage({ type: "gsa-xapi", statement: { verb: { id: "http://adlnet.gov/expapi/verbs/answered" }, object: { id: "x" }, context: { extensions: {} } } });
    await waitFor(() => expect(calls.find((c) => c.path === "/xapi/statements/")).toBeDefined());
    expect(calls.find((c) => c.path === "/xapi/statements/")?.body).toEqual({
      verb: { id: "http://adlnet.gov/expapi/verbs/answered" },
      object: { id: "x" },
      context: { extensions: {}, registration: "5b9e4a3c-1111-4222-8333-444455556661" },
    });
  });
});

describe("a package for teaching staff", () => {
  it("previews it, sets how it counts, and shows every learner's attempts and statements", async () => {
    const { calls } = open("lecturer", {
      "POST /packages/3/launch/": { body: launched({ attempt: attempt(1, { is_preview: true }) }) },
      "PATCH /packages/3/": { body: pkg({ weight: "3.00" }) },
      "GET /xapi/statements/": {
        body: { statements: [{ id: "s1", verb: { id: "http://adlnet.gov/expapi/verbs/passed", display: { "en-GB": "passed" } }, object: { id: "x" }, actor: { account: { name: "S2026901" } }, result: { score: { scaled: 0.85 } }, timestamp: "2026-10-02T10:00:00Z", stored: "2026-10-02T10:00:00Z" }], more: "" },
      },
    });
    const table = await screen.findByRole("table", { name: "Every learner's attempts" });
    expect(within(table).getByText("Completed · Passed · 85.0%")).toBeInTheDocument();
    expect(within(table).getByText(/Kezia Persaud/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download the package" })).toHaveAttribute("href", "/api/v1/content/12/download/");
    const weight = screen.getByLabelText("Weight in coursework");
    await userEvent.clear(weight);
    await userEvent.type(weight, "3");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ weight: "3", max_attempts: 2 });
    expect(await screen.findByText("Saved how the package counts.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show what the package reported" }));
    const reported = await screen.findByRole("list", { name: "Statements the package reported" });
    expect(reported).toHaveTextContent("S2026901 passed 85%");
    expect(calls.find((c) => c.path.startsWith("/xapi/statements/"))?.path).toContain(encodeURIComponent("https://lms.example/xapi/activities/packages/3"));
    await userEvent.click(screen.getByRole("button", { name: "Try it (preview)" }));
    expect(await screen.findByText("Preview attempt 1: it never counts.")).toBeInTheDocument();
  });

  it("chooses a part of a package with several", async () => {
    const parts = pkg({
      scos: [
        { id: "a", title: "Part one", href: "one.html", parameters: "" },
        { id: "b", title: "Part two", href: "two.html", parameters: "" },
      ],
    });
    const { calls } = open("lecturer", { "POST /packages/3/launch/": { body: launched() } }, parts);
    await userEvent.selectOptions(await screen.findByLabelText("Part"), "b");
    await userEvent.click(screen.getByRole("button", { name: "Try it (preview)" }));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ sco: "b", new_attempt: false });
  });

  it("says when the package cannot be found", async () => {
    fakeServer({ "GET /packages/": { body: page([]) }, "GET /sites/9/contents/": { body: siteAs("student") } });
    render(<PackageScreen siteId={9} itemId={12} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not open this package.");
  });
});
