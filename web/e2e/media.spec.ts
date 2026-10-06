/**
 * Items 4.03 to 4.07: a lecturer puts a video up once and corrects its captions; a student plays a lecture in
 * the quality they choose, keeps a module to read offline, reads it with no connection, and removes it from
 * Downloaded; data-light mode; push notices in the notification settings. On a desktop and on a 360px phone,
 * every screen checked with axe.
 *
 * seed_journeys gives AGR101 the module "Week 4: Preparing the ground" with a page and a prepared video (the
 * journey image has no converter, so a video put up here waits to be prepared or fails in words).
 */

import { COURSE, expect, expectAccessible, onPhone, PEOPLE, search, signIn, signOut, test } from "./support";

const WEEK = "Week 4: Preparing the ground";
const VIDEO = "Making a seed bed";

/** The smallest file the server takes as a video: an MP4 box header. It is never played. */
const MP4 = Buffer.concat([Buffer.from([0, 0, 0, 0x18]), Buffer.from("ftypisom"), Buffer.alloc(12)]);

async function openCourse(page: import("@playwright/test").Page, testInfo: import("@playwright/test").TestInfo) {
  const results = await search(page, testInfo, "Crop Production");
  await results.getByRole("option", { name: new RegExp(COURSE.title) }).first().click();
  await expect(page.getByRole("heading", { name: COURSE.title, level: 1 })).toBeVisible();
}

test("a lecturer puts a video up once and corrects its captions in the browser", async ({ page }, testInfo) => {
  const phone = onPhone(testInfo);
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openCourse(page, testInfo);
  const week = page.getByRole("region", { name: WEEK });
  await week.getByRole("button", { name: "Put a video up" }).click();
  const title = `Watering the bed (${testInfo.project.name})`;
  await week.getByLabel("Title").fill(title);
  await week.getByLabel(/^Video/).setInputFiles({ name: "watering.mp4", mimeType: "video/mp4", buffer: MP4 });
  await week.getByLabel("Whose material is this?").selectOption({ label: "GSA's own material" });
  await week.getByRole("button", { name: "Put the video up" }).click();
  await expect(page.getByRole("status").filter({ hasText: `Added “${title}”.` })).toBeVisible();
  // Prepared by the job worker: it says so until it is ready, or why it could not be.
  await expect(week.getByRole("listitem").filter({ hasText: title }).getByText(/Being prepared|could not be prepared/)).toBeVisible();

  const video = week.getByRole("listitem").filter({ hasText: VIDEO });
  await expect(video.getByRole("radio", { name: /^Low \(240p\), \d+ KB$/ })).toBeVisible();
  await expectAccessible(page, testInfo, "content tab with video, teaching");
  await video.getByRole("link", { name: "Captions" }).click();
  await expect(page.getByRole("heading", { name: `Captions: ${VIDEO}`, level: 1 })).toBeVisible();
  const caption = page.getByRole("textbox", { name: "Caption 1" });
  await expect(caption).toHaveValue(/^Loosen the soil/);
  const corrected = phone ? "Loosen the soil a spade deep." : "Loosen the soil to a spade's depth, then rake it level.";
  await caption.fill(corrected);
  await page.getByRole("button", { name: "Save captions" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved the English captions." })).toBeVisible();
  await expectAccessible(page, testInfo, "captions");
  await signOut(page);
});

test("a student plays the lecture in the quality they choose, and keeps the module to read offline", async ({ page, context }, testInfo) => {
  const phone = onPhone(testInfo);
  await signIn(page, PEOPLE.student.username);
  await openCourse(page, testInfo);
  const week = page.getByRole("region", { name: WEEK });
  const video = week.getByRole("listitem").filter({ hasText: VIDEO });
  // Phones start in data-light mode (item 4.05): the low copy, and nothing fetched before Play.
  const player = video.locator("video");
  await expect(player).toHaveAttribute("src", phone ? /\/play\/low\/$/ : /\/play\/standard\/$/);
  await expect(player).toHaveAttribute("preload", phone ? "none" : "metadata");
  await video.getByRole("radio", { name: /^Sound only/ }).check();
  await expect(video.locator("audio")).toHaveAttribute("src", /\/play\/audio\/$/);
  await video.getByRole("radio", { name: /^Low \(240p\)/ }).check();
  await expectAccessible(page, testInfo, "content tab with video, student");

  // The space it will take first; then it is kept for this person only.
  await week.getByRole("button", { name: `Keep “${WEEK}” to read offline` }).click();
  const confirm = week.getByRole("group", { name: `Keep “${WEEK}” to read offline` });
  await expect(confirm).toContainText(/This keeps \d+ KB on this device: 1 page and 1 video at low quality\./);
  await expectAccessible(page, testInfo, "keep a module offline");
  await confirm.getByRole("button", { name: "Keep it" }).click();
  await expect(week.getByText("Kept offline")).toBeVisible();

  // With no connection at all, the course and the kept page still open: the service worker answers from the
  // person's own cache. Browsers refuse service workers on a page whose certificate they do not trust, as the
  // journey stack's own is, so this part runs only where the worker could register (sw.test.ts covers it).
  const worker = await page.evaluate(() => navigator.serviceWorker.getRegistration().then((r) => Boolean(r?.active)));
  if (worker) {
    await context.setOffline(true);
    try {
      await page.reload();
      await expect(page.getByRole("heading", { name: COURSE.title, level: 1 })).toBeVisible();
      await page.getByRole("region", { name: WEEK }).getByRole("link", { name: "Before you watch" }).click();
      await expect(page.getByRole("heading", { name: "Before you watch", level: 1 })).toBeVisible();
      await expect(page.getByText("Watch the short video")).toBeVisible();
    } finally {
      await context.setOffline(false);
    }
  } else {
    testInfo.annotations.push({ type: "note", description: "No service worker here (untrusted certificate): offline reading not exercised." });
  }

  // Downloaded, under Me: what is kept, its size, and Remove.
  await page.getByRole("button", { name: /^Signed in as / }).click();
  await page.getByRole("link", { name: /Downloaded/ }).click();
  await expect(page.getByRole("heading", { name: "Downloaded", level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: WEEK })).toBeVisible();
  await expect(page.getByRole("radio", { name: /As the device suggests \((on|off) here\)/ })).toBeChecked();
  await expectAccessible(page, testInfo, "downloaded");
  await page.getByRole("button", { name: `Remove “${WEEK}”` }).click();
  await expect(page.getByRole("status").filter({ hasText: `Removed “${WEEK}” from this device.` })).toBeVisible();
  await expect(page.getByText(/Nothing yet/)).toBeVisible();
  await signOut(page);
});

test("data-light mode holds pictures back, and modules kept offline go at sign-out", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.student.username);
  await page.goto("/#/downloads");
  await page.getByRole("radio", { name: "Always on" }).check();
  await expect(page.getByText("It is on on this device now.", { exact: false })).toBeVisible();
  await openCourse(page, testInfo);
  const week = page.getByRole("region", { name: WEEK });
  await expect(week.getByRole("listitem").filter({ hasText: VIDEO }).locator("video")).not.toHaveAttribute("poster", /./);
  await week.getByRole("button", { name: `Keep “${WEEK}” to read offline` }).click();
  await week.getByRole("button", { name: "Keep it" }).click();
  await expect(week.getByText("Kept offline")).toBeVisible();
  await signOut(page);
  // Nothing of the person's is left on the device once they have signed out.
  const left = await page.evaluate(async () => (await caches.keys()).filter((name) => name.startsWith("gsa-lms-offline-")));
  expect(left).toEqual([]);
  await signIn(page, PEOPLE.student.username);
  await page.goto("/#/downloads");
  await expect(page.getByText(/Nothing yet/)).toBeVisible();
  await page.getByRole("radio", { name: /As the device suggests/ }).check();
  await signOut(page);
});

test("push notices are chosen per kind in the notification settings", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.student.username);
  await page.goto("/#/notification-settings");
  await expect(page.getByRole("heading", { name: "Push notices on this device" })).toBeVisible();
  // The journey stack has no VAPID keys, so push is not sent there: the screen says so plainly.
  await expect(page.getByText("This LMS does not send push notices yet.")).toBeVisible();
  const announcements = page.getByRole("group", { name: "Course announcements" });
  const push = announcements.getByRole("checkbox", { name: "Also a push notice" });
  const was = await push.isChecked();
  await push.click();
  await expect(push).toBeChecked({ checked: !was });
  await expect(page.getByRole("status").filter({ hasText: "Saved: Course announcements." })).toBeVisible();
  await expectAccessible(page, testInfo, "notification settings with push");
  await signOut(page);
});
