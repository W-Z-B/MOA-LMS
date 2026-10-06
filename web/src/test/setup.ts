/** Loaded before every component test: DOM matchers, and a clean page and storage between tests. */

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";
import { setQueueOwner } from "../app/offlineQueue";

// Component tests act as one signed-in person, whose writes the offline queue may keep and send.
beforeEach(() => setQueueOwner(1));

afterEach(() => {
  setQueueOwner(null);
  cleanup();
  localStorage.clear();
  document.cookie.split("; ").forEach((row) => {
    const name = row.split("=")[0];
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  });
});
