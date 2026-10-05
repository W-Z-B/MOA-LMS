import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Me } from "../../api/types";
import { fakeServer, offline } from "../../test/fetch";
import { LoginScreen } from "./LoginScreen";

const student: Me = {
  id: 3,
  username: "kezia.persaud",
  name: "Kezia Persaud",
  roles: ["student"],
  is_superuser: false,
  mfa_required: false,
  mfa_verified: true,
  person_id: 9,
  person_kind: "student",
  external_id: "S2026001",
};
const courseAdmin: Me = { ...student, roles: ["course_admin"], mfa_required: true, mfa_verified: false };

async function signIn(username: string, password: string) {
  await userEvent.type(screen.getByLabelText("Username"), username);
  await userEvent.type(screen.getByLabelText("Password"), password);
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("Sign-in", () => {
  it("signs a student straight in, with no authenticator code", async () => {
    const server = fakeServer({ "POST /auth/login/": { body: student } });
    const onSignedIn = vi.fn();
    render(<LoginScreen onSignedIn={onSignedIn} />);
    expect(screen.getByRole("heading", { name: "GSA LMS" })).toBeInTheDocument();
    await signIn("kezia.persaud", "a password");
    expect(onSignedIn).toHaveBeenCalledWith(student);
    expect(server.calls[0].body).toEqual({ username: "kezia.persaud", password: "a password" });
  });

  it("refuses a wrong password with the server's sentence", async () => {
    fakeServer({
      "POST /auth/login/": {
        status: 401,
        body: { code: "invalid_credentials", detail: "Username or password is incorrect." },
      },
    });
    const onSignedIn = vi.fn();
    render(<LoginScreen onSignedIn={onSignedIn} />);
    await signIn("kezia.persaud", "wrong");
    expect(await screen.findByRole("alert")).toHaveTextContent("Username or password is incorrect.");
    expect(onSignedIn).not.toHaveBeenCalled();
  });

  it("says plainly when the server cannot be reached", async () => {
    fakeServer({ "POST /auth/login/": offline });
    render(<LoginScreen onSignedIn={vi.fn()} />);
    await signIn("kezia.persaud", "a password");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });

  it("asks a course administrator to enrol an authenticator app, then for its code", async () => {
    const verified = { ...courseAdmin, mfa_verified: true };
    const server = fakeServer({
      "POST /auth/login/": { body: courseAdmin },
      "POST /auth/mfa/enrol/": { body: { provisioning_uri: "otpauth://totp/GSA%20LMS:admin?secret=TEST" } },
      "POST /auth/mfa/verify/": [
        { status: 400, body: { code: "invalid_code", detail: "The code is not valid." } },
        { body: verified },
      ],
    });
    const onSignedIn = vi.fn();
    render(<LoginScreen onSignedIn={onSignedIn} />);
    await signIn("course.admin", "a password");
    expect(await screen.findByText(/otpauth:\/\/totp/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Authenticator code"), "000000");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The code is not valid.");
    expect(onSignedIn).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect(onSignedIn).toHaveBeenCalledWith(verified);
    expect(server.calls.filter((c) => c.path === "/auth/mfa/verify/").map((c) => c.body)).toEqual([
      { code: "000000" },
      { code: "000000" },
    ]);
  });

  it("asks only for the code when the app is already enrolled", async () => {
    fakeServer({
      "POST /auth/login/": { body: courseAdmin },
      "POST /auth/mfa/enrol/": {
        status: 409,
        body: { code: "already_enrolled", detail: "A confirmed device exists." },
      },
    });
    render(<LoginScreen onSignedIn={vi.fn()} />);
    await signIn("course.admin", "a password");
    expect(await screen.findByLabelText("Authenticator code")).toBeInTheDocument();
    expect(screen.queryByText(/otpauth/)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
