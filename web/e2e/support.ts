/** Helpers shared by the journeys: signing in as the fictional journey cast, and the accessibility check. */

import AxeBuilder from "@axe-core/playwright";
import { test as base, expect, type Page, type TestInfo } from "@playwright/test";

/**
 * Every journey runs with a guard: a Content-Security-Policy violation in the browser fails the test,
 * so a policy set in deploy/ can never quietly break a screen.
 */
export const test = base.extend<{ cspGuard: void }>({
  cspGuard: [
    async ({ page }, use) => {
      const violations: string[] = [];
      page.on("console", (message) => {
        if (message.type() === "error" && /Content Security Policy/i.test(message.text())) violations.push(message.text());
      });
      await use();
      expect(violations, "Content-Security-Policy violations").toEqual([]);
    },
    { auto: true },
  ],
});
export { expect };

/** Accounts from seed_journeys (fictional people). Their shared password comes from the environment. */
export const PEOPLE = {
  student: { username: "kezia.persaud", name: "Kezia Persaud", studentNo: "S2026901" },
  lecturer: { username: "marlon.bacchus", name: "Marlon Bacchus" },
} as const;

/** The course site seed_journeys teaches. */
export const COURSE = { code: "AGR101-2026-27-S1-MRP", title: "Introduction to Crop Production" } as const;

export function password(): string {
  const value = process.env.E2E_PASSWORD;
  if (!value) throw new Error("Set E2E_PASSWORD to the DEMO_USER_PASSWORD of the test stack.");
  return value;
}

export async function signIn(page: Page, username: string) {
  await page.goto("/");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "My courses", level: 1 })).toBeVisible();
}

export async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
}

/**
 * WCAG 2.2 AA rules, as the gold standard requires. Serious and critical findings fail the test; every
 * finding is attached to the report so the minor ones can be worked through too. The page must also
 * fit the screen: nothing may need sideways scrolling (WCAG 1.4.10 Reflow), at desktop or phone width.
 */
export async function expectAccessible(page: Page, testInfo: TestInfo, screen: string) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, `${screen} is wider than the screen by ${overflow}px`).toBeLessThanOrEqual(0);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  await testInfo.attach(`axe ${screen}`, { body: JSON.stringify(results.violations, null, 2), contentType: "application/json" });
  const blocking = results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect(blocking, `Accessibility problems on ${screen}`).toEqual([]);
}
