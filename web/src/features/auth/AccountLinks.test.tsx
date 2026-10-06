import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer, offline } from "../../test/fetch";
import { ConfirmEmailScreen } from "./ConfirmEmailScreen";
import { ForgotPasswordScreen } from "./ForgotPasswordScreen";
import { LoginScreen } from "./LoginScreen";
import { SetPasswordScreen } from "./SetPasswordScreen";

const CHOSEN = "Guava-Season-Starts-2026";

function open() {
  const onDone = vi.fn();
  const onAskAgain = vi.fn();
  render(<SetPasswordScreen uid="MTQ" token="abc-123" onDone={onDone} onAskAgain={onAskAgain} />);
  return { onDone, onAskAgain };
}

async function choose(first: string, second = first) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("New password"), first);
  await user.type(screen.getByLabelText("New password again"), second);
  await user.click(screen.getByRole("button", { name: "Save my password" }));
  return user;
}

describe("choosing a password from an emailed link (item 1.22)", () => {
  it("checks the link first, welcomes someone invited with their username and the policy, and saves their own password", async () => {
    const server = fakeServer({
      "POST /auth/password/check/": { body: { username: "S2026903", kind: "invitation" } },
      "POST /auth/password/set/": { body: { username: "S2026903", kind: "invitation" } },
    });
    const { onDone } = open();
    expect(screen.getByText("Checking your link…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Welcome: choose your password" })).toBeInTheDocument();
    expect(server.calls[0].body).toEqual({ uid: "MTQ", token: "abc-123" });
    expect(screen.getByText("S2026903")).toBeInTheDocument();
    expect(screen.getByLabelText("New password")).toHaveAccessibleDescription(/At least 12 characters/);
    expect(screen.getByLabelText("New password")).toHaveAttribute("autocomplete", "new-password");
    await choose(CHOSEN);
    expect(onDone).toHaveBeenCalledWith("S2026903");
    expect(server.calls.at(-1)?.body).toEqual({ uid: "MTQ", token: "abc-123", password: CHOSEN });
  });

  it("will not send two passwords that differ, and shows the password on request", async () => {
    const server = fakeServer({ "POST /auth/password/check/": { body: { username: "asha", kind: "reset" } } });
    open();
    expect(await screen.findByRole("heading", { name: "Choose a new password" })).toBeInTheDocument();
    const user = await choose(CHOSEN, `${CHOSEN}!`);
    expect(screen.getByRole("alert")).toHaveTextContent("The two passwords are not the same.");
    expect(server.calls).toHaveLength(1);
    await user.click(screen.getByLabelText("Show the password"));
    expect(screen.getByLabelText("New password")).toHaveAttribute("type", "text");
  });

  it("lists every rule the password breaks, in the server's words", async () => {
    fakeServer({
      "POST /auth/password/check/": { body: { username: "asha", kind: "reset" } },
      "POST /auth/password/set/": { status: 400, body: { password: ["This password is too short.", "This password is too common."] } },
    });
    open();
    await choose("password");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This password is too short.");
    expect(alert).toHaveTextContent("This password is too common.");
  });

  it("says when a link has expired, offers a new one, and says so when it stops working while open", async () => {
    fakeServer({ "POST /auth/password/check/": { status: 400, body: { code: "invalid_link", detail: "This link has expired." } } });
    const { onAskAgain } = open();
    expect(await screen.findByRole("alert")).toHaveTextContent("This link has expired.");
    await userEvent.click(screen.getByRole("button", { name: "Ask for a new link" }));
    expect(onAskAgain).toHaveBeenCalled();
  });

  it("says so when the link stops working while the page is open, or the server cannot be reached", async () => {
    fakeServer({
      "POST /auth/password/check/": { body: { username: "asha", kind: "reset" } },
      "POST /auth/password/set/": [{ status: 400, body: { code: "other", detail: "Refused." } }, offline],
    });
    open();
    await choose(CHOSEN);
    expect(await screen.findByRole("alert")).toHaveTextContent("Refused.");
    await userEvent.click(screen.getByRole("button", { name: "Save my password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });

  it("says plainly when the link cannot be checked", async () => {
    fakeServer({ "POST /auth/password/check/": offline });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });

  it("drops the form when the link stops working as it is used", async () => {
    fakeServer({
      "POST /auth/password/check/": { body: { username: "asha", kind: "reset" } },
      "POST /auth/password/set/": { status: 400, body: { code: "invalid_link", detail: "This link has been used." } },
    });
    open();
    await choose(CHOSEN);
    expect(await screen.findByRole("alert")).toHaveTextContent("This link has been used.");
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
  });
});

describe("asking for a link", () => {
  it("gives the same answer whoever is asked for, and offers the way back", async () => {
    const answer = "If that is the username or email address of an account, a link is on its way.";
    const server = fakeServer({ "POST /auth/password/forgot/": [{ status: 429, body: { code: "too_many_attempts", detail: "Too many requests." } }, { body: { detail: answer } }] });
    const onBack = vi.fn();
    render(<ForgotPasswordScreen onBack={onBack} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Username or email address"), "S2026903");
    await user.click(screen.getByRole("button", { name: "Email me a link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many requests.");
    await user.click(screen.getByRole("button", { name: "Email me a link" }));
    expect(await screen.findByRole("status")).toHaveTextContent(answer);
    expect(server.calls[0].body).toEqual({ login: "S2026903" });
    await user.click(screen.getByRole("button", { name: "Back to sign in" }));
    expect(onBack).toHaveBeenCalled();
  });

  it("says plainly when the server cannot be reached", async () => {
    fakeServer({ "POST /auth/password/forgot/": offline });
    render(<ForgotPasswordScreen onBack={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Username or email address"), "someone");
    await userEvent.click(screen.getByRole("button", { name: "Email me a link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });
});

describe("confirming a new sign-in email address (item 1.10)", () => {
  it("changes nothing until the button is pressed, then says where links will go", async () => {
    const server = fakeServer({
      "POST /auth/email/confirm/": { body: { detail: "The sign-in email address is now asha.new@gsa.example.", email: "asha.new@gsa.example" } },
    });
    const onDone = vi.fn();
    render(<ConfirmEmailScreen token="abc123" onDone={onDone} />);
    expect(server.calls).toHaveLength(0); // a mail program opening the link changes nothing
    await userEvent.click(screen.getByRole("button", { name: "Confirm the new address" }));
    expect(await screen.findByRole("status")).toHaveTextContent("The sign-in email address is now asha.new@gsa.example.");
    expect(server.calls[0].body).toEqual({ token: "abc123" });
    await userEvent.click(screen.getByRole("button", { name: "Go to the GSA LMS" }));
    expect(onDone).toHaveBeenCalled();
  });

  it("says when the link has expired, and when the server is out of reach", async () => {
    fakeServer({ "POST /auth/email/confirm/": [{ status: 400, body: { code: "expired", detail: "This link has expired." } }, offline] });
    render(<ConfirmEmailScreen token="old" onDone={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Confirm the new address" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This link has expired.");
    await userEvent.click(screen.getByRole("button", { name: "Confirm the new address" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });
});

describe("the sign-in page's ways out", () => {
  it("links to forgotten passwords and the public certificate check, and starts with a known username", async () => {
    const onForgot = vi.fn();
    render(<LoginScreen onSignedIn={vi.fn()} onForgot={onForgot} knownUsername="S2026903" notice="Your password is saved. Sign in with it now." />);
    expect(screen.getByLabelText("Username")).toHaveValue("S2026903");
    expect(screen.getByRole("status")).toHaveTextContent("Your password is saved.");
    expect(screen.getByRole("link", { name: "Check a GSA certificate" })).toHaveAttribute("href", "/api/check-certificate/");
    await userEvent.click(screen.getByRole("button", { name: "Forgot your password?" }));
    expect(onForgot).toHaveBeenCalled();
  });
});
