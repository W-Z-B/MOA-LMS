/** Helpers shared by the journeys: signing in as the fictional journey cast, and the accessibility check. */

import { createHmac } from "node:crypto";
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
  // Teaching staff give an authenticator code; the secret is fictional and held by the test stack.
  lecturer: { username: "marlon.bacchus", name: "Marlon Bacchus" },
} as const;

/** Whether the journey runs in the phone project (360px, touch). */
export const onPhone = (testInfo: TestInfo) => testInfo.project.name === "phone";

/** Open a page the way people do: from search, Ctrl K on a desktop or the Search tab on a phone. */
export async function search(page: Page, testInfo: TestInfo, words: string) {
  if (onPhone(testInfo)) await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: "Search" }).click();
  else await page.keyboard.press("Control+K");
  const box = page.getByRole("dialog", { name: "Search" }).getByRole("combobox");
  await expect(box).toBeFocused();
  await box.fill(words);
  return page.getByRole("dialog", { name: "Search" });
}

/** The course site seed_journeys teaches. */
export const COURSE = { code: "AGR101-2026-27-S1-MRP", title: "Introduction to Crop Production" } as const;

export function password(): string {
  const value = process.env.E2E_PASSWORD;
  if (!value) throw new Error("Set E2E_PASSWORD to the DEMO_USER_PASSWORD of the test stack.");
  return value;
}

/**
 * The current six-digit code of an authenticator app holding a base32 secret (RFC 6238: HMAC-SHA1, 30-second
 * steps). A dozen lines of Node rather than another dependency.
 */
export function totp(secret: string, at = Date.now()): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of secret.replace(/=+$/, "").toUpperCase()) bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  const key = Buffer.from((bits.match(/.{8}/g) ?? []).map((byte) => parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 1000 / 30)));
  const hmac = createHmac("sha1", key).update(counter).digest();
  const offset = hmac[hmac.length - 1] & 0x0f;
  return String((hmac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

/** The fictional lecturer's authenticator secret (DEMO_TOTP_SECRET of the test stack). */
function totpSecret(): string {
  const value = process.env.E2E_TOTP_SECRET;
  if (!value) throw new Error("Set E2E_TOTP_SECRET to the DEMO_TOTP_SECRET of the test stack.");
  return value;
}

/** The privacy notice's title (privacy/notice_text.py), read and acknowledged once by each person. */
export const NOTICE_TITLE = "How the GSA LMS uses your personal data";

/**
 * After signing in, the first time: the privacy notice in force is read and acknowledged (item 1.18).
 * Returns whether it was shown.
 */
export async function passNotice(page: Page): Promise<boolean> {
  const read = page.getByRole("button", { name: "I have read this notice" });
  // Everyone opens on their own Home (item 2.07).
  const inside = page.getByRole("heading", { name: "Home", level: 1 });
  await expect(read.or(inside).first()).toBeVisible();
  const shown = await read.isVisible();
  if (shown) {
    await expect(page.getByRole("heading", { name: NOTICE_TITLE, level: 1 })).toBeVisible();
    await read.click();
  }
  await expect(inside).toBeVisible();
  return shown;
}

/** Sign in; teaching staff then give their authenticator code (ADR 0013). Returns whether the notice was shown. */
export async function signIn(page: Page, username: string, { code = false } = {}): Promise<boolean> {
  await page.goto("/");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password());
  await page.getByRole("button", { name: "Sign in" }).click();
  if (code) {
    await page.getByLabel("Authenticator code").fill(totp(totpSecret()));
    await page.getByRole("button", { name: "Verify" }).click();
  }
  return passNotice(page);
}

/** Sign out from the person's menu behind their initials (the "Me" sheet on a phone). */
export async function signOut(page: Page) {
  await page.getByRole("button", { name: /^Signed in as / }).click();
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
