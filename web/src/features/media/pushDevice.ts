/**
 * Push notices on this device (item 4.04): the browser's permission, its subscription with the push service,
 * and telling the LMS about it. Which kinds are pushed is chosen per kind in the notification settings.
 *
 * On a shared phone, signing out turns push off for this device first (forgetDevice), so one person's
 * notices never appear on a phone someone else is using.
 */

import { get, post } from "../../api/client";
import type { PushState } from "../../api/types-media";

/** Whether this browser can receive push notices at all. On an iPhone, only once added to the home screen. */
export const pushSupported = () =>
  typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

/** base64url -> the bytes the browser wants as applicationServerKey. */
export function keyBytes(base64url: string): Uint8Array {
  const base64 = base64url.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(base64url.length / 4) * 4, "=");
  return Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
}

async function registration(): Promise<ServiceWorkerRegistration | null> {
  if (!pushSupported()) return null;
  return (await navigator.serviceWorker.getRegistration()) ?? null;
}

/** This browser's subscription, if push is on here. */
export async function currentSubscription(): Promise<PushSubscription | null> {
  const reg = await registration();
  return reg ? reg.pushManager.getSubscription() : null;
}

/** The device in words, for the person's list: "Chrome on Android". */
export function deviceName(agent = navigator.userAgent): string {
  const browser = /Edg\//.test(agent) ? "Edge" : /Firefox\//.test(agent) ? "Firefox" : /Chrome\//.test(agent) ? "Chrome" : /Safari\//.test(agent) ? "Safari" : "A browser";
  const system = /Android/.test(agent) ? "Android" : /iPhone|iPad/.test(agent) ? "iPhone or iPad" : /Windows/.test(agent) ? "Windows" : /Mac OS/.test(agent) ? "a Mac" : /Linux/.test(agent) ? "Linux" : "";
  return system ? `${browser} on ${system}` : browser;
}

export class PushRefused extends Error {}

/** Ask the browser, subscribe, and tell the LMS. Throws PushRefused with what to do when it cannot. */
export async function turnOn(state: PushState): Promise<PushState> {
  if (!state.available || !state.public_key) throw new PushRefused("This LMS does not send push notices yet.");
  const reg = await registration();
  if (!reg) throw new PushRefused("This browser cannot receive push notices. On an iPhone, add the LMS to the home screen first.");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new PushRefused("Notices are blocked for the LMS in this browser's settings. Allow them there, then try again.");
  const subscription =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(state.public_key) as BufferSource }));
  const { endpoint, keys } = subscription.toJSON();
  return post<PushState>("/notifications/push/subscribe/", { endpoint, keys, device: deviceName() });
}

/** Stop push on this device, here and at the LMS. */
export async function turnOff(): Promise<PushState> {
  const subscription = await currentSubscription();
  if (subscription) {
    await post("/notifications/push/unsubscribe/", { endpoint: subscription.endpoint });
    await subscription.unsubscribe();
  }
  return get<PushState>("/notifications/push/");
}

/** At sign-out: this device stops receiving the person's notices. Never stands in the way of signing out. */
export async function forgetDevice(): Promise<void> {
  try {
    const subscription = await currentSubscription();
    if (!subscription) return;
    await post("/notifications/push/unsubscribe/", { endpoint: subscription.endpoint }).catch(() => undefined);
    await subscription.unsubscribe();
  } catch {
    /* signing out goes ahead */
  }
}
