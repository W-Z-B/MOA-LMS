import { describe, expect, it } from "vitest";
import { fakeServer, offline } from "../test/fetch";
import { ApiError, errorMessage, get, patch, post } from "./client";

describe("API client", () => {
  it("calls the versioned API with the session cookie and asks for JSON", async () => {
    const server = fakeServer({ "GET /auth/me/": { body: { id: 7 } } });
    await expect(get("/auth/me/")).resolves.toEqual({ id: 7 });
    expect(server.fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/me/",
      expect.objectContaining({ credentials: "same-origin", method: "GET" }),
    );
    expect(server.calls[0].headers.get("Accept")).toBe("application/json");
    expect(server.calls[0].headers.has("X-CSRFToken")).toBe(false);
  });

  it("sends the CSRF token with every change, never with a read", async () => {
    document.cookie = "csrftoken=abc123";
    const server = fakeServer({
      "POST /announcements/": { status: 201, body: { id: 1 } },
      "PATCH /sites/4/": { body: { id: 4 } },
    });
    await post("/announcements/", { title: "Field trip" });
    await patch("/sites/4/", { is_published: true });
    expect(server.calls.map((c) => c.headers.get("X-CSRFToken"))).toEqual(["abc123", "abc123"]);
    expect(server.calls[0].headers.get("Content-Type")).toBe("application/json");
    expect(server.calls[0].body).toEqual({ title: "Field trip" });
  });

  it("lets the browser set the content type for a file upload", async () => {
    const server = fakeServer({ "POST /assignments/3/submit/": { status: 201, body: {} } });
    const form = new FormData();
    form.set("file", new Blob(["x"]), "report.pdf");
    await post("/assignments/3/submit/", form);
    expect(server.calls[0].headers.has("Content-Type")).toBe(false);
    expect(server.calls[0].body).toBeInstanceOf(FormData);
  });

  it("answers nothing for 204 No Content", async () => {
    fakeServer({ "POST /auth/logout/": { status: 204 } });
    await expect(post("/auth/logout/")).resolves.toBeUndefined();
  });

  it("turns a refusal into an ApiError with its code and sentence", async () => {
    fakeServer({ "POST /auth/login/": { status: 423, body: { code: "locked_out", detail: "Too many failed attempts." } } });
    const err = await post("/auth/login/", {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 423, code: "locked_out", detail: "Too many failed attempts." });
    expect(errorMessage(err)).toBe("Too many failed attempts.");
  });

  it("keeps field errors so forms can show them", async () => {
    fakeServer({ "POST /submissions/5/mark/": { status: 400, body: { mark: ["The maximum is 50."] } } });
    const err = await post("/submissions/5/mark/", {}).catch((e: unknown) => e);
    expect(err).toMatchObject({ code: "error", fields: { mark: ["The maximum is 50."] } });
    expect(errorMessage(err)).toBe("mark: The maximum is 50.");
  });

  it("falls back to a plain sentence when the answer is not JSON or the network is down", async () => {
    fakeServer({ "GET /sites/": { status: 502, raw: "<html>Bad gateway</html>" } });
    const err = await get("/sites/").catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 502, code: "error", detail: "Request failed" });
    fakeServer({ "GET /sites/": offline });
    const down = await get("/sites/").catch((e: unknown) => e);
    expect(errorMessage(down, "Could not load your courses.")).toBe("Could not load your courses.");
  });
});
