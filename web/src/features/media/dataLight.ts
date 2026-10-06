/**
 * Data-light mode (item 4.05): pictures and video are loaded only when asked for, and large items say how
 * big they are. A setting of this device (under Me, on the Downloaded page), since it is about the line the
 * device is on. Until the person chooses, it is on for a phone and off for a computer; where the browser
 * gives connection hints they decide: "save data" or a slow line turns it on, Wi-Fi or a cable turns it off.
 */

import { useEffect, useState } from "react";
import { PHONE } from "../../app/frame";

const KEY = "gsa-lms.data-light";
const EVENT = "gsa:data-light";

interface ConnectionHints {
  saveData?: boolean;
  effectiveType?: string;
  type?: string;
}

/** What the device suggests before the person has chosen. */
export function suggested(): boolean {
  const hints = (navigator as Navigator & { connection?: ConnectionHints }).connection;
  if (hints?.saveData) return true;
  if (hints?.effectiveType && /(^|-)(2g|3g)$/.test(hints.effectiveType)) return true;
  if (hints?.type === "wifi" || hints?.type === "ethernet") return false;
  if (hints?.type === "cellular") return true;
  return typeof window.matchMedia === "function" && window.matchMedia(PHONE).matches;
}

/** The person's own choice on this device, or null when they have not chosen. */
export function chosen(): boolean | null {
  try {
    const value = localStorage.getItem(KEY);
    return value === "on" ? true : value === "off" ? false : null;
  } catch {
    return null;
  }
}

export const isDataLight = () => chosen() ?? suggested();

/** On, off, or null to go back to what the device suggests. */
export function setDataLight(value: boolean | null) {
  try {
    if (value === null) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, value ? "on" : "off");
  } catch {
    /* a convenience of this device only */
  }
  window.dispatchEvent(new Event(EVENT));
}

export function useDataLight(): boolean {
  const [light, setLight] = useState(isDataLight);
  useEffect(() => {
    const update = () => setLight(isDataLight());
    window.addEventListener(EVENT, update);
    return () => window.removeEventListener(EVENT, update);
  }, []);
  return light;
}

/** Items this big say their size beside them in data-light mode. */
export const LARGE_BYTES = 500 * 1024;
