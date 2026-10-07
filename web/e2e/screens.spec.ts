/**
 * Item 4.01: every screen checked at 360 pixels. For a student, a lecturer and an administrator, this walks
 * every page router.ts lists that the person may open, the course site's tabs, and the parts of Admin, on the
 * 360px phone: none may need sideways scrolling, and each must pass axe (WCAG 2.2 AA). A page added to
 * router.ts is checked here without anyone having to remember to.
 */

import type { Page, TestInfo } from "@playwright/test";
import { hasAnyRole, ADMIN_ROLES, type Me } from "../src/api/types";
import { pagesFor, SITE_TABS } from "../src/app/router";
import { COURSE, expect, expectAccessible, onPhone, PEOPLE, signIn, signOut, test } from "./support";

const ADMINISTRATOR = "ayesha.ramdin";

/** Go to an address in the app, as a link inside it does, and wait for the screen's heading. */
async function visit(page: Page, path: string) {
  await page.evaluate((to) => {
    window.location.hash = to;
  }, path);
  await expect(page.locator(".loading")).toHaveCount(0);
  await expect(page.locator("main h1, [role=main] h1, h1").first()).toBeVisible();
}

async function me(page: Page): Promise<Me> {
  return page.evaluate(() => fetch("/api/v1/auth/me/", { headers: { Accept: "application/json" } }).then((r) => r.json()));
}

async function courseId(page: Page): Promise<number | null> {
  const sites = await page.evaluate(() => fetch("/api/v1/sites/", { headers: { Accept: "application/json" } }).then((r) => r.json()));
  const list: { id: number; code: string }[] = Array.isArray(sites) ? sites : sites.results;
  return list.find((s) => s.code === COURSE.code)?.id ?? null;
}

/** Every page this person may open, the course's tabs if they are on it, and Admin's parts for administrators. */
async function walk(page: Page, testInfo: TestInfo, who: string) {
  const person = await me(page);
  const paths = pagesFor(person).map((p) => p.path);
  const site = await courseId(page);
  if (site !== null) paths.push(...SITE_TABS.map((tab) => (tab === "content" ? `/sites/${site}` : `/sites/${site}/${tab}`)));
  if (hasAnyRole(person, ADMIN_ROLES)) paths.push("/admin/templates", "/admin/takedowns", "/admin/storage");
  expect(paths.length).toBeGreaterThan(8);
  for (const path of paths) {
    await visit(page, path);
    await expectAccessible(page, testInfo, `${who}: #${path} at 360px`);
  }
}

test.describe("every screen at 360 pixels (item 4.01)", () => {
  test("a student's screens", async ({ page }, testInfo) => {
    test.setTimeout(240_000);
    test.skip(!onPhone(testInfo), "The walk is the phone's: 360 pixels wide, with touch.");
    await signIn(page, PEOPLE.student.username);
    expect(page.viewportSize()?.width).toBe(360);
    await walk(page, testInfo, "student");
    await signOut(page);
  });

  test("a lecturer's screens", async ({ page }, testInfo) => {
    test.setTimeout(240_000);
    test.skip(!onPhone(testInfo), "The walk is the phone's: 360 pixels wide, with touch.");
    await signIn(page, PEOPLE.lecturer.username, { code: true });
    await walk(page, testInfo, "lecturer");
    await signOut(page);
  });

  test("an administrator's screens", async ({ page }, testInfo) => {
    test.setTimeout(240_000);
    test.skip(!onPhone(testInfo), "The walk is the phone's: 360 pixels wide, with touch.");
    await signIn(page, ADMINISTRATOR, { code: true });
    await walk(page, testInfo, "administrator");
    await signOut(page);
  });
});
