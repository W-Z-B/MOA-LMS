import type { Page } from "@playwright/test";
import { COURSE, PEOPLE, expect, expectAccessible, onPhone, signIn, signOut, test } from "./support";

/**
 * Items 3.12 to 3.15 and 5.15: practical assessment in the field, on a desktop and on a 360px phone. A lecturer
 * marks a checklist with a photo and releases it, the student reads it; a student keeps a logbook entry
 * on the phone without signal and it is sent once when the signal returns; the lecturer signs entries off.
 */

/** A one-pixel PNG, as a stand-in for a photo from the phone's camera. */
const PHOTO = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
const TASK = "Prepare a vegetable bed";

/** From Home to a tab of the journeys' course. */
async function openTab(page: Page, tab: "Practicals" | "Logbook") {
  await page.getByRole("navigation", { name: "Shortcuts" }).getByRole("link", { name: /My courses/ }).click();
  await page.getByRole("button", { name: new RegExp(COURSE.title) }).click();
  await expect(page.getByRole("heading", { name: COURSE.title, level: 1 })).toBeVisible();
  await page.getByRole("tab", { name: tab }).click();
  await expect(page.getByRole("tab", { name: tab })).toHaveAttribute("aria-selected", "true");
}

async function fillEntry(page: Page, task: string) {
  await expect(page.getByRole("heading", { name: "New logbook entry" })).toBeVisible();
  await page.getByLabel("Hours").fill("2.5");
  await page.getByRole("combobox", { name: "Where", exact: true }).selectOption({ label: "Fish pond" });
  await page.getByLabel("Which unit").fill("Pond 2, tilapia");
  await page.getByLabel("What you did").fill(task);
}

test("a lecturer marks a checklist in the field with a photo and releases it, and the student reads it", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openTab(page, "Practicals");
  await expect(page.getByRole("heading", { name: new RegExp(TASK) })).toBeVisible();
  await expectAccessible(page, testInfo, "practical tasks");

  await page.getByRole("button", { name: `Mark ${TASK} in the field` }).click();
  await expect(page.getByRole("heading", { name: "Who are you observing?" })).toBeVisible();
  await expectAccessible(page, testInfo, "student picker");
  await page.getByRole("button", { name: new RegExp(PEOPLE.student.name) }).click();

  const bed = page.getByRole("group", { name: /Bed formed to 1.2 m wide/ });
  await bed.getByRole("button", { name: "Met", exact: true }).click();
  await expect(bed.getByRole("button", { name: "Met", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "4 of 5" }).click();
  await page.getByRole("group", { name: /Tools cleaned and stored/ }).getByRole("button", { name: "Met", exact: true }).click();
  await page.getByLabel("Comments for the student").fill("An even bed and a good tilth.");
  await page.getByLabel("Take a photo").setInputFiles({ name: "bed.png", mimeType: "image/png", buffer: PHOTO });
  await expect(page.getByRole("img", { name: "Photo bed.png" })).toBeVisible();
  if (onPhone(testInfo)) {
    // Big targets for a thumb in the field.
    expect((await bed.getByRole("button", { name: "Not met" }).boundingBox())!.height).toBeGreaterThanOrEqual(48);
    expect((await page.getByRole("button", { name: "Save observation" }).boundingBox())!.height).toBeGreaterThanOrEqual(48);
  }
  await expectAccessible(page, testInfo, "field checklist");

  await page.getByRole("button", { name: "Save observation" }).click();
  await expect(page.getByRole("heading", { name: `Saved: ${PEOPLE.student.name}` })).toBeVisible();
  await expect(page.getByText("Photo sent")).toBeVisible();
  await expectAccessible(page, testInfo, "observation saved");

  await page.getByRole("button", { name: "Back to the class list" }).click();
  await page.getByRole("button", { name: `Release to ${PEOPLE.student.name}` }).click();
  await expect(page.getByText(`Released to ${PEOPLE.student.name}.`)).toBeVisible();
  await expectAccessible(page, testInfo, "practical task");

  // The released observation is evidence for the unit its critical criterion is mapped to.
  await page.getByRole("link", { name: "Competency" }).click();
  await page.getByRole("button", { name: `Record for ${PEOPLE.student.name}` }).click();
  const unit = page.getByRole("form", { name: "U1 Prepare land for planting" });
  await expect(unit.getByText("The evidence suggests:")).toContainText("Competent");
  await expectAccessible(page, testInfo, "competency record");
  await signOut(page);

  await signIn(page, PEOPLE.student.username);
  await openTab(page, "Practicals");
  const observed = page.getByRole("article", { name: new RegExp(`${TASK}, attempt`) }).last();
  await expect(observed).toContainText("An even bed and a good tilth.");
  await expect(observed).toContainText("Every critical criterion met.");
  await expect(observed.getByRole("img", { name: "bed.png" })).toBeVisible();
  await expectAccessible(page, testInfo, "my practicals");
  await page.getByRole("link", { name: "Portfolio" }).click();
  await expect(page.getByRole("heading", { name: "My practical portfolio" })).toBeVisible();
  await expect(page.getByText(new RegExp(`${TASK}, attempt`)).first()).toBeVisible();
  await expectAccessible(page, testInfo, "portfolio");
  await signOut(page);
});

test("a student writes a logbook entry without signal, and it is sent once when the signal returns", async ({ page, context }, testInfo) => {
  await signIn(page, PEOPLE.student.username);
  await openTab(page, "Logbook");
  await expectAccessible(page, testInfo, "my logbook");
  await page.getByRole("button", { name: "Add an entry" }).click();

  // The signal goes while the entry is written in the field.
  await context.setOffline(true);
  const task = `Fed the fingerlings and checked the oxygen (${testInfo.project.name}, ${Date.now()})`;
  await fillEntry(page, task);
  await page.getByLabel("Take a photo").setInputFiles({ name: "pond.png", mimeType: "image/png", buffer: PHOTO });
  await expectAccessible(page, testInfo, "logbook entry");
  await page.getByRole("button", { name: "Save entry" }).click();
  await expect(page.getByText(/Waiting to send\. It is sent when the connection returns\./)).toBeVisible();
  await expect(page.getByText(/1 photo waiting to send/)).toBeVisible();
  await expectAccessible(page, testInfo, "logbook entry waiting");

  await context.setOffline(false);
  await expect(page.getByRole("status").filter({ hasText: /^Sent$/ })).toBeVisible();
  await expect(page.getByText("Photo sent")).toBeVisible();

  // Sent once: after a fresh start, the logbook holds the entry once, with its photo.
  await page.getByRole("button", { name: "Back to my logbook" }).click();
  await page.reload();
  const entries = page.getByRole("article").filter({ hasText: task });
  await expect(entries).toHaveCount(1);
  await expect(entries.getByText("Waiting for sign-off")).toBeVisible();
  await expect(entries.getByRole("img", { name: "pond.png" })).toBeVisible();
  await signOut(page);
});

test("a student adds a logbook entry and the lecturer signs it off", async ({ page }, testInfo) => {
  const task = `Weeded and mulched the tomato rows (${testInfo.project.name}, ${Date.now()})`;
  await signIn(page, PEOPLE.student.username);
  await openTab(page, "Logbook");
  await page.getByRole("button", { name: "Add an entry" }).click();
  await fillEntry(page, task);
  await page.getByRole("combobox", { name: "Where", exact: true }).selectOption({ label: "Crop plot" });
  await page.getByRole("button", { name: "Save entry" }).click();
  await expect(page.getByText("Sent to your supervisor for sign-off.")).toBeVisible();
  await signOut(page);

  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openTab(page, "Logbook");
  await expect(page.getByRole("heading", { name: "Waiting for sign-off" })).toBeVisible();
  await expect(page.getByRole("article").filter({ hasText: task })).toBeVisible();
  await expectAccessible(page, testInfo, "logbook sign-off");
  // Sign off every entry waiting, this one and any the other journeys left, so the Homes stay as expected.
  const signOff = page.getByRole("button", { name: /^Sign off / });
  for (let left = await signOff.count(); left > 0; left -= 1) {
    await signOff.first().click();
    await expect(signOff).toHaveCount(left - 1);
  }
  await expect(page.getByText("Nothing waits for sign-off.")).toBeVisible();
  await signOut(page);

  await signIn(page, PEOPLE.student.username);
  await openTab(page, "Logbook");
  const entry = page.getByRole("article").filter({ hasText: task });
  await expect(entry.getByText("Signed off", { exact: true })).toBeVisible();
  await expect(entry.getByRole("button")).toHaveCount(0); // a signed entry is locked
  await expect(page.getByText(/h signed/).first()).toBeVisible();
  await expectAccessible(page, testInfo, "signed logbook");
  await signOut(page);
});
