import { expect, expectAccessible, signIn, signOut, test } from "./support";

/**
 * Required training (item 5.05, decision D13), on a desktop and a 360px phone: an administrator sees which
 * requirements are kept in the LMS and which the HRMS keeps, stops and restores one of their own, and finds
 * the HRMS's own read-only. The journey stack reads the HRMS's list (HRMS_TRAINING_REQUIREMENTS_SYNC on).
 */

/** The fictional administrator of the console journeys (seed_journeys), with the same fictional authenticator. */
const ADMINISTRATOR = "ayesha.ramdin";

test("an administrator keeps the LMS's required training and leaves the HRMS's to the HRMS", async ({ page }, testInfo) => {
  await signIn(page, ADMINISTRATOR, { code: true });
  await page.goto("/#/learning/required");
  await expect(page.getByRole("heading", { name: "Required training", level: 2 })).toBeVisible();
  const list = page.getByRole("list", { name: "Requirements" });
  const ours = list.getByRole("listitem").filter({ hasText: "Safe use of farm machinery" });
  const theirs = list.getByRole("listitem").filter({ hasText: "First aid in the field" });
  await expect(ours).toContainText("Kept in the LMS");
  await expect(theirs).toContainText("From the HRMS");
  await expect(theirs).toContainText("Kept in the HRMS: change it there.");
  await expect(theirs.getByRole("button", { name: /^(Stop requiring|Require again)/ })).toHaveCount(0);
  await expectAccessible(page, testInfo, "required training");

  // The desktop and phone runs share the data: stop it if it is in force, then put it back.
  const stop = ours.getByRole("button", { name: "Stop requiring: Safe use of farm machinery" });
  if (await stop.isVisible()) {
    await stop.click();
    await expect(page.getByRole("status")).toContainText("Safe use of farm machinery: no longer required.");
  }
  await expect(ours).toContainText("Not in force");
  await ours.getByRole("button", { name: "Require again: Safe use of farm machinery" }).click();
  await expect(page.getByRole("status")).toContainText("Safe use of farm machinery: required again.");
  await expect(ours.getByRole("button", { name: "Stop requiring: Safe use of farm machinery" })).toBeVisible();
  await signOut(page);
});
