import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../../test/fetch";
import { NotificationSettingsScreen } from "../notifications/NotificationSettingsScreen";
import { deviceName, forgetDevice, keyBytes } from "./pushDevice";
import PushSection from "./PushSection";

const KEY = "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM";
const on = { available: true, public_key: KEY, devices: 0 };

/** A browser that can take push: a service worker registration with a push manager, and a permission. */
function browser({ permission = "granted", existing = null as null | { endpoint: string } } = {}) {
  let subscription: null | { endpoint: string; toJSON: () => unknown; unsubscribe: () => Promise<boolean> } = existing
    ? { ...existing, toJSON: () => ({ endpoint: existing.endpoint, keys: { p256dh: "p", auth: "a" } }), unsubscribe: vi.fn(async () => true) }
    : null;
  const subscribe = vi.fn(async (options: { applicationServerKey: Uint8Array }) => {
    subscription = {
      endpoint: "https://fcm.googleapis.com/fcm/send/new",
      toJSON: () => ({ endpoint: "https://fcm.googleapis.com/fcm/send/new", keys: { p256dh: "p", auth: "a" }, options }),
      unsubscribe: vi.fn(async () => true),
    };
    return subscription;
  });
  const registration = { pushManager: { getSubscription: async () => subscription, subscribe } };
  vi.stubGlobal("navigator", {
    userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36",
    serviceWorker: { getRegistration: async () => registration },
  });
  vi.stubGlobal("PushManager", function PushManager() {});
  vi.stubGlobal("Notification", { requestPermission: vi.fn(async () => permission) });
  return { subscribe, current: () => subscription };
}

describe("push notices on this device (item 4.04)", () => {
  it("turns push on after the browser asks, and off again", async () => {
    const { subscribe } = browser();
    const { calls } = fakeServer({
      "GET /notifications/push/": [{ body: on }, { body: { ...on, devices: 0 } }],
      "POST /notifications/push/subscribe/": { status: 201, body: { ...on, devices: 1 } },
      "POST /notifications/push/unsubscribe/": { body: on },
    });
    render(<PushSection />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Turn push on for this device" }));
    expect(await screen.findByText(/On for this device/)).toHaveTextContent("Your devices with push on: 1.");
    expect(subscribe.mock.calls[0][0]).toMatchObject({ userVisibleOnly: true });
    const sent = calls.find((c) => c.path === "/notifications/push/subscribe/")!.body as { endpoint: string; device: string };
    expect(sent.endpoint).toBe("https://fcm.googleapis.com/fcm/send/new");
    expect(sent.device).toBe("Chrome on Android");
    await user.click(screen.getByRole("button", { name: "Turn push off on this device" }));
    expect(await screen.findByText(/Off for this device/)).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/notifications/push/unsubscribe/")).toBe(true);
  });

  it("says what to do when notices are blocked, unsupported or not sent by this LMS", async () => {
    browser({ permission: "denied" });
    fakeServer({ "GET /notifications/push/": { body: on } });
    const { unmount } = render(<PushSection />);
    await userEvent.click(await screen.findByRole("button", { name: "Turn push on for this device" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Notices are blocked for the LMS in this browser's settings.");
    unmount();
    vi.unstubAllGlobals();
    fakeServer({ "GET /notifications/push/": { body: on } });
    const second = render(<PushSection />);
    expect(await screen.findByText(/add the LMS to the home screen first/)).toBeInTheDocument();
    second.unmount();
    fakeServer({ "GET /notifications/push/": { body: { available: false, public_key: null, devices: 0 } } });
    render(<PushSection />);
    expect(await screen.findByText("This LMS does not send push notices yet.")).toBeInTheDocument();
  });

  it("forgets this device at sign-out, here and at the LMS", async () => {
    const { current } = browser({ existing: { endpoint: "https://fcm.googleapis.com/fcm/send/old" } });
    const { calls } = fakeServer({ "POST /notifications/push/unsubscribe/": { body: on } });
    const subscription = current()!;
    await forgetDevice();
    expect(calls[0].body).toEqual({ endpoint: "https://fcm.googleapis.com/fcm/send/old" });
    expect(subscription.unsubscribe).toHaveBeenCalled();
  });

  it("reads the server's key and names the device in words", () => {
    expect(keyBytes(KEY)).toHaveLength(65);
    expect(keyBytes(KEY)[0]).toBe(4); // an uncompressed P-256 point
    expect(deviceName("Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36")).toBe("Chrome on Android");
    expect(deviceName("Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Version/17.4 Mobile/15E148 Safari/604.1")).toBe("Safari on iPhone or iPad");
    expect(deviceName("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0")).toBe("Firefox on Windows");
    expect(deviceName("curl/8")).toBe("A browser");
  });

  it("chooses, kind by kind, whether a notice is also pushed", async () => {
    const rows = [{ kind: "announcement", label: "Course announcements", in_app: true, email: "instant", push: false }];
    const { calls } = fakeServer({
      "GET /notifications/preferences/": { body: rows },
      "PUT /notifications/preferences/": { body: [{ ...rows[0], push: true }] },
      "GET /notifications/push/": { body: on },
    });
    render(<NotificationSettingsScreen />);
    const group = await screen.findByRole("group", { name: "Course announcements" });
    await userEvent.click(within(group).getByRole("checkbox", { name: "Also a push notice" }));
    expect(await screen.findByText("Saved: Course announcements.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")!.body).toEqual([{ kind: "announcement", email: "instant", push: true }]);
    expect(within(group).getByRole("checkbox", { name: "Also a push notice" })).toBeChecked();
  });
});
