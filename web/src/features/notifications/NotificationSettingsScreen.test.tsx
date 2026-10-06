import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeServer } from "../../test/fetch";
import { NotificationSettingsScreen } from "./NotificationSettingsScreen";

const rows = [
  { kind: "mark", label: "Marks and feedback", in_app: true, email: "instant", push: false },
  { kind: "reminder", label: "Reminders before due dates", in_app: true, email: "instant", push: true },
];

describe("notification settings (item 2.33)", () => {
  it("shows each kind with its email choice and saves a change", async () => {
    const { calls } = fakeServer({
      "GET /notifications/preferences/": { body: rows },
      "PUT /notifications/preferences/": { body: [rows[0], { ...rows[1], email: "daily" }] },
    });
    render(<NotificationSettingsScreen />);
    const user = userEvent.setup();
    const reminders = await screen.findByRole("group", { name: "Reminders before due dates" });
    expect(within(reminders).getByRole("radio", { name: "An email now" })).toBeChecked();
    await user.click(within(reminders).getByRole("radio", { name: "In a daily summary email" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved: Reminders before due dates.");
    expect(within(reminders).getByRole("radio", { name: "In a daily summary email" })).toBeChecked();
    expect(calls.find((c) => c.method === "PUT")!.body).toEqual([{ kind: "reminder", email: "daily", push: true }]);
  });

  it("says when the settings cannot be read or saved", async () => {
    fakeServer({
      "GET /notifications/preferences/": { body: rows },
      "PUT /notifications/preferences/": { status: 400, body: { code: "invalid", detail: "Not a choice." } },
    });
    render(<NotificationSettingsScreen />);
    const user = userEvent.setup();
    await user.click(within(await screen.findByRole("group", { name: "Marks and feedback" })).getByRole("radio", { name: "No email" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Not a choice.");
  });
});
