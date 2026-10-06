/**
 * The term calendar (item 7.12): an administrator opens Terms from the Admin page, adds a term with its close
 * date and grace, sees when its courses become read-only and are archived, and changes the grace. On a
 * desktop and on a 360px phone, with the accessibility check on each screen.
 */

import { expect, expectAccessible, signIn, signOut, test } from "./support";

/** The fictional administrator of the console journeys (seed_journeys). */
const ADMINISTRATOR = "ayesha.ramdin";

test("an administrator keeps the term calendar", async ({ page }, testInfo) => {
  // One term code for each project, so the desktop and phone runs never meet; no course uses it.
  const code = `E2E-${testInfo.project.name.toUpperCase()}`.slice(0, 16);
  await signIn(page, ADMINISTRATOR, { code: true });
  await page.goto("/#/admin");
  const links = page.getByRole("navigation", { name: "Course administration" });
  await links.getByRole("link", { name: /^Terms/ }).click();
  await expect(page.getByRole("heading", { name: "Terms", level: 1 })).toBeVisible();
  await expect(page).toHaveURL(/#\/admin\/terms$/);
  await expectAccessible(page, testInfo, "terms");

  const existing = page.getByRole("button", { name: `Change the term ${code}` });
  if (!(await existing.isVisible())) {
    await page.getByRole("button", { name: "Add a term" }).click();
    await page.getByLabel("Term code").fill(code);
    await page.getByLabel("Name").fill("Journey term");
    await page.getByLabel("Teaching starts").fill("2031-01-06");
    await page.getByLabel("Teaching ends").fill("2031-04-11");
    await page.getByLabel("Last day for work").fill("2031-04-25");
    await expectAccessible(page, testInfo, "new term");
    await page.getByRole("button", { name: "Save the term" }).click();
    await expect(page.getByRole("status")).toHaveText(`Saved the term ${code}.`);
  }
  const card = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: new RegExp(code) }) });
  await expect(card).toContainText("last day for work 25/04/2031");
  await expect(card).toContainText("Not started");

  await card.getByRole("button", { name: `Change the term ${code}` }).click();
  await page.getByLabel(/Days of grace/).fill("5");
  await page.getByRole("button", { name: "Save the term" }).click();
  await expect(page.getByRole("status")).toHaveText(`Saved the term ${code}.`);
  await expect(card).toContainText("then 5 days of grace");

  await card.getByRole("button", { name: `Show the courses of ${code}` }).click();
  await expect(card.getByText("No course uses this term code.")).toBeVisible();
  await expectAccessible(page, testInfo, "terms with courses shown");
  await signOut(page);
});
