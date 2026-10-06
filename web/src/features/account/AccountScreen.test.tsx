import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeServer, offline } from "../../test/fetch";
import { AccountScreen } from "./AccountScreen";

const sessions = {
  body: [
    { id: 1, device: "Firefox on Windows", ip: "10.0.0.1", created_at: "2026-10-05T08:00:00Z", last_seen_at: "2026-10-05T09:00:00Z", current: true },
    { id: 2, device: "Chrome on Android", ip: null, created_at: "2026-10-04T08:00:00Z", last_seen_at: "2026-10-04T09:00:00Z", current: false },
  ],
};
const email = { body: { email: "asha@gsa.example", pending: null } };

describe("My account: password and sign-in email (items 1.10, 1.22)", () => {
  it("changes the password knowing the current one, and says how many other devices were signed out", async () => {
    const server = fakeServer({
      "GET /auth/sessions/": sessions,
      "GET /auth/email/": email,
      "POST /auth/password/change/": [
        { status: 400, body: { code: "wrong_password", detail: "Your current password is not right." } },
        { status: 400, body: { new_password: ["This password is too common."] } },
        { body: { ended: 1 } },
      ],
    });
    render(<AccountScreen />);
    const form = (await screen.findByRole("heading", { name: "Your password" })).closest("section")!;
    const user = userEvent.setup();
    const fill = async (current: string, next: string, again = next) => {
      for (const [label, value] of [["Current password", current], ["New password", next], ["New password again", again]]) {
        fireEvent.change(within(form).getByLabelText(label), { target: { value } });
      }
      await user.click(within(form).getByRole("button", { name: "Change password" }));
    };
    await fill("old one", "Mango-Season-2026", "Mango-Season-2027");
    expect(within(form).getByRole("alert")).toHaveTextContent("The two new passwords are not the same.");
    await fill("old one", "Mango-Season-2026");
    expect(await within(form).findByRole("alert")).toHaveTextContent("Your current password is not right.");
    await fill("old one", "Mango-Season-2026");
    expect(await within(form).findByRole("alert")).toHaveTextContent("This password is too common.");
    await fill("old one", "Mango-Season-2026");
    expect(await within(form).findByRole("status")).toHaveTextContent("You were signed out on 1 other device.");
    expect(server.calls.filter((c) => c.path === "/auth/password/change/").at(-1)?.body).toEqual({
      current_password: "old one",
      new_password: "Mango-Season-2026",
    });
    expect(within(form).getByLabelText("Current password")).toHaveValue("");
  });

  it("says a change on this device alone plainly", async () => {
    fakeServer({ "GET /auth/sessions/": sessions, "GET /auth/email/": email, "POST /auth/password/change/": { body: { ended: 0 } } });
    render(<AccountScreen />);
    const form = (await screen.findByRole("heading", { name: "Your password" })).closest("section")!;
    for (const label of ["Current password", "New password", "New password again"]) await userEvent.type(within(form).getByLabelText(label), "Mango-Season-2026");
    await userEvent.click(within(form).getByRole("button", { name: "Change password" }));
    expect(await within(form).findByRole("status")).toHaveTextContent(/^Your password is changed\.$/);
  });

  it("sends a link to a new sign-in email address with the password, and shows the change waiting", async () => {
    const server = fakeServer({
      "GET /auth/sessions/": sessions,
      "GET /auth/email/": [email, { body: { email: "asha@gsa.example", pending: { new_email: "asha.new@gsa.example", expires_at: "2026-10-07T12:00:00Z" } } }],
      "POST /auth/email/change/": [
        { status: 400, body: { code: "wrong_password", detail: "Your password is not right." } },
        { body: { detail: "A link to confirm it was sent to asha.new@gsa.example.", emailed: true, pending: null } },
      ],
    });
    render(<AccountScreen />);
    const form = await screen.findByRole("form", { name: "Change your sign-in email" });
    expect(await within(form).findByText("asha@gsa.example")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(within(form).getByLabelText("New email address"), "asha.new@gsa.example");
    await user.type(within(form).getByLabelText("Your password"), "wrong");
    await user.click(within(form).getByRole("button", { name: "Send the link" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("Your password is not right.");
    await user.click(within(form).getByRole("button", { name: "Send the link" }));
    expect(await within(form).findByRole("status")).toHaveTextContent("A link to confirm it was sent");
    expect(await within(form).findByText(/Waiting for you to follow the link sent to asha.new@gsa.example/)).toBeInTheDocument();
    expect(server.calls.find((c) => c.path === "/auth/email/change/")?.body).toEqual({ email: "asha.new@gsa.example", password: "wrong" });
  });

  it("says when the address cannot be loaded or changed", async () => {
    fakeServer({ "GET /auth/sessions/": sessions, "GET /auth/email/": offline, "POST /auth/email/change/": offline });
    render(<AccountScreen />);
    const form = await screen.findByRole("form", { name: "Change your sign-in email" });
    expect(await within(form).findByRole("alert")).toHaveTextContent("Could not load your sign-in email address.");
    await userEvent.type(within(form).getByLabelText("New email address"), "x@gsa.example");
    await userEvent.type(within(form).getByLabelText("Your password"), "p");
    await userEvent.click(within(form).getByRole("button", { name: "Send the link" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("The address was not changed.");
  });
});

describe("My account: signed-in devices", () => {
  it("signs out one other device, or every other, and says when that fails", async () => {
    fakeServer({
      "GET /auth/sessions/": sessions,
      "GET /auth/email/": email,
      "DELETE /auth/sessions/2/": { status: 204 },
      "POST /auth/sessions/end-others/": [{ body: { ended: 3 } }, offline],
    });
    render(<AccountScreen />);
    await userEvent.click(await screen.findByRole("button", { name: "Sign out of Chrome on Android" }));
    expect(await screen.findByText("Signed out of Chrome on Android.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out everywhere else" }));
    expect(await screen.findByText("Signed out of 3 other devices.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out everywhere else" }));
    expect(await screen.findByText("That did not go through. Try again.")).toBeInTheDocument();
  });

  it("says when the devices cannot be loaded", async () => {
    fakeServer({ "GET /auth/sessions/": offline, "GET /auth/email/": email });
    render(<AccountScreen />);
    expect(await screen.findByText("Could not load where you are signed in.")).toBeInTheDocument();
  });
});
