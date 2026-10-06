import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import type { FrameLocator, Page } from "@playwright/test";
import { COURSE, PEOPLE, expect, expectAccessible, search, signIn, signOut, test } from "./support";

/**
 * Packaged content, the library, interchange and digital badges (items 5.10, 5.12 to 5.14, 6.08, 6.09), on a
 * desktop and a 360px phone: a student works through a SCORM package and an H5P exercise in their sandboxed
 * player and sees the results recorded; the lecturer sees the attempts and statements, puts a package up,
 * uses an open resource from the library, and moves a course's content out as a cartridge and into another
 * course; the holder of a certificate downloads it as a digital badge, which the public page verifies.
 * The packages are seed_journeys' own (api/packages/samples.py), made in code.
 */

test.describe.configure({ mode: "serial" });

const PRACTICE = "Interactive practice";
const SCORM = "Seed spacing check";
const H5P = "Crop pests quiz";

async function openCourse(page: Page, name: RegExp) {
  await page.getByRole("link", { name: "GSA LMS Home" }).click();
  await page.getByRole("navigation", { name: "Shortcuts" }).getByRole("link", { name: /My courses/ }).click();
  await page.getByRole("button", { name }).click();
}

/** Open (or reopen) a package from its screen: Start, Continue or Review, whichever this run finds. */
async function openPackage(page: Page, title: string): Promise<FrameLocator> {
  await page.getByRole("region", { name: PRACTICE }).getByRole("link", { name: title }).click();
  await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
  await page.getByRole("button", { name: /^(Start|Continue|Review your last attempt|Try it \(preview\))$/ }).click();
  await expect(page.getByTitle(`${title}: the package`)).toBeVisible();
  return page.frameLocator(`iframe[title="${title}: the package"]`);
}

function journeyFile(name: string): string {
  const links = process.env.E2E_LINKS_FILE;
  if (!links) throw new Error("Set E2E_LINKS_FILE to the JOURNEY_LINKS_FILE seed_journeys wrote.");
  return join(dirname(links), name);
}

test("a student completes a SCORM package and an H5P exercise in the sandboxed player", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.student.username);
  await openCourse(page, new RegExp(COURSE.title));
  await expect(page.getByRole("region", { name: PRACTICE })).toBeVisible();

  const lesson = await openPackage(page, SCORM);
  await lesson.getByRole("button", { name: "75 cm between rows" }).click();
  await expect(lesson.getByText("Right: saved as passed, with 90.")).toBeVisible();
  await expectAccessible(page, testInfo, "SCORM package in its player");
  await page.getByRole("button", { name: "Close the package" }).click();
  await expect(page.getByRole("region", { name: "Your attempts" })).toContainText("Completed · Passed · 90.0%");
  await page.getByRole("link", { name: `Back to ${COURSE.title}` }).click();

  const quiz = await openPackage(page, H5P);
  // h5p-standalone draws the exercise in the sandboxed page itself (embedType "div").
  await quiz.getByRole("button", { name: "Clay" }).click();
  await expect(quiz.getByText("Right: clay holds the most water.")).toBeVisible();
  await page.getByRole("button", { name: "Close the package" }).click();
  await expect(page.getByRole("region", { name: "Your attempts" })).toContainText("Completed · Passed · 100.0%");
  await expectAccessible(page, testInfo, "H5P exercise, after");
  await page.getByRole("link", { name: `Back to ${COURSE.title}` }).click();
  const practice = page.getByRole("region", { name: PRACTICE });
  await expect(practice.getByText("Complete", { exact: true })).toHaveCount(2);
  await signOut(page);
});

test("the lecturer sees every attempt and what the packages reported, and puts a package up", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openCourse(page, new RegExp(COURSE.title));
  await page.getByRole("region", { name: PRACTICE }).getByRole("link", { name: SCORM }).click();
  const attempts = page.getByRole("table", { name: "Every learner's attempts" });
  await expect(attempts).toContainText(PEOPLE.student.name);
  await expect(attempts).toContainText("Passed · 90.0%");
  await page.getByRole("button", { name: "Show what the package reported" }).click();
  await expect(page.getByRole("list", { name: "Statements the package reported" })).toContainText(`${PEOPLE.student.studentNo} passed 90%`);
  await expectAccessible(page, testInfo, "package results, teaching");
  await page.getByRole("link", { name: `Back to ${COURSE.title}` }).click();

  const practice = page.getByRole("region", { name: PRACTICE });
  await practice.getByRole("button", { name: "Add a SCORM or H5P package" }).click();
  const form = page.getByRole("form", { name: "Add a SCORM or H5P package" });
  await expect(form).toContainText("H5P exercises are not written in the LMS");
  const title = `Seed spacing, again (${testInfo.project.name})`;
  await form.getByLabel("Package", { exact: true }).setInputFiles({ name: "seed-spacing.zip", mimeType: "application/zip", buffer: readFileSync(journeyFile("seed-spacing.zip")) });
  await form.getByLabel(/^Title/).fill(title);
  await form.getByLabel("Whose material is this?").selectOption({ label: "GSA's own material" });
  await expectAccessible(page, testInfo, "putting a package up");
  await form.getByRole("button", { name: "Put the package up" }).click();
  await expect(page.getByRole("status").filter({ hasText: `Added the package “${title}”.` })).toBeVisible();
  await expect(practice.getByRole("link", { name: title })).toBeVisible();
  await signOut(page);
});

test("the lecturer uses an open resource from the library in another course", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  const dialog = await search(page, testInfo, "Content library");
  await dialog.getByRole("group", { name: "Pages" }).getByRole("option", { name: /^Content library/ }).click();
  await expect(page.getByRole("heading", { name: "Content library", level: 1 })).toBeVisible();
  const items = page.getByRole("list", { name: "Library items" });
  const ipm = items.getByRole("listitem").filter({ hasText: "Integrated pest management for smallholders" });
  await expect(ipm).toContainText("CC BY-NC · FAO");
  await expectAccessible(page, testInfo, "content library");
  await ipm.getByRole("button", { name: "Use in a course" }).click();
  const use = page.getByRole("form", { name: /in a course$/ });
  await use.getByLabel("Course").selectOption({ label: `${COURSE.code} ${COURSE.title}` });
  await use.getByLabel("Module").selectOption({ label: PRACTICE });
  await use.getByRole("button", { name: "Copy into the course" }).click();
  await expect(page.getByRole("status").filter({ hasText: "into the course as a draft" })).toBeVisible();
  await page.getByRole("link", { name: "Question banks" }).click();
  await expect(page.getByRole("heading", { name: "Question banks", level: 2 })).toBeVisible();
  await expectAccessible(page, testInfo, "library question banks");
  await signOut(page);
});

test("the lecturer exports a course as a Common Cartridge and imports it into another", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openCourse(page, new RegExp(COURSE.title));
  await page.getByRole("link", { name: "Import or export content" }).click();
  await expect(page.getByRole("heading", { name: "Import and export content", level: 1 })).toBeVisible();
  await expectAccessible(page, testInfo, "import and export");
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download as a Common Cartridge (.imscc)" }).click();
  const cartridge = await (await download).path();

  await openCourse(page, /Field Crops \(imported\)/);
  await page.getByRole("link", { name: "Import or export content" }).click();
  await page.getByLabel("File to import").setInputFiles({ name: "agr101.imscc", mimeType: "application/zip", buffer: readFileSync(cartridge) });
  await page.getByRole("button", { name: "Import into this course" }).click();
  await expect(page.getByRole("status").filter({ hasText: "From the cartridge:" })).toContainText("all as drafts");
  await expect(page.getByRole("heading", { name: /^Not imported/ })).toBeVisible();
  await expectAccessible(page, testInfo, "import report");
  await signOut(page);
});

test("the holder downloads a certificate as a digital badge, and the public page verifies it", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  const dialog = await search(page, testInfo, "Staff development");
  await dialog.getByRole("group", { name: "Pages" }).getByRole("option", { name: /^Staff development/ }).click();
  await page.getByRole("navigation", { name: "Staff development" }).getByRole("link", { name: "Certificates" }).click();
  const badge = page.getByRole("link", { name: /^Download the digital badge/ }).first();
  await expect(badge).toBeVisible();
  const answer = await page.request.get((await badge.getAttribute("href"))!);
  expect(answer.headers()["content-type"]).toContain("application/vc+jwt");
  const credential = await answer.text();
  expect(credential.split(".")).toHaveLength(3);
  await signOut(page);

  await page.goto("/api/check-certificate/");
  await expect(page.getByRole("heading", { name: "Verify a digital badge" })).toBeVisible();
  await page.getByLabel("Digital badge").fill(credential);
  await page.getByRole("button", { name: "Verify the badge" }).click();
  await expect(page.getByRole("status")).toContainText("This certificate is genuine.");
  await expectAccessible(page, testInfo, "badge verified");
});
