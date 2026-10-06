import { defineConfig, devices } from "@playwright/test";

/**
 * Browser journeys against the hosted image (deploy/railway/Dockerfile) behind TLS, with the fictional
 * journey data loaded (seed_journeys). Run the whole thing with scripts/e2e.sh; it starts compose.e2e.yml and
 * runs these tests in the Playwright container, so a developer machine needs only Docker.
 */
export default defineConfig({
  testDir: "e2e",
  // The journeys share one database, so they run in order.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://lms-e2e",
    ignoreHTTPSErrors: true, // the test stack signs its certificate with Caddy's own authority
    locale: "en-GB",
    timezoneId: "America/Guyana",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    // Phone first: every journey also runs on a phone with touch, at 360px, the narrowest common width.
    { name: "phone", use: { ...devices["Pixel 7"], viewport: { width: 360, height: 780 } } },
  ],
});
