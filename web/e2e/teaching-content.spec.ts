import type { Page } from "@playwright/test";
import { COURSE, PEOPLE, expect, expectAccessible, onPhone, signIn, signOut, test } from "./support";

/**
 * Items 2.12 to 2.18: a lecturer writes a page with a heading, a picture and a formula, is warned by the
 * accessibility check as they write, and publishes it; a student reads it with the formula drawn by KaTeX;
 * the lecturer copies last year's course into this year's with every date moved. Desktop and a 360px phone.
 * Named to run after courses.spec.ts, whose student reads the privacy notice at their first sign-in.
 */

test.describe.configure({ mode: "serial" });

// A one-pixel PNG: a real photograph's first bytes, which the server checks.
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64");

/** A one-page PDF with a green square on it, built with its cross-reference table so PDF.js reads it cleanly. */
function onePagePdf(): Buffer {
  const drawing = "0 0.5 0 rg 50 50 200 200 re f";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 4 0 R >>",
    `<< /Length ${drawing.length} >>\nstream\n${drawing}\nendstream`,
  ];
  let body = "%PDF-1.4\n";
  const offsets = objects.map((object, at) => {
    const offset = body.length;
    body += `${at + 1} 0 obj\n${object}\nendobj\n`;
    return offset;
  });
  const xref = body.length;
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  body += offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(body, "latin1");
}

const WEEK = "Week 1: What a crop needs";
const ALT = "Maize seedlings in a germination tray";

const names = (project: string) => ({
  photo: `Seedling tray (${project})`,
  page: `Germination notes (${project})`,
  pdf: `Germination record sheet (${project})`,
});

async function openCourse(page: Page, name: RegExp) {
  await page.getByRole("navigation", { name: "Shortcuts" }).getByRole("link", { name: /My courses/ }).click();
  await page.getByRole("button", { name }).click();
}

test("a lecturer writes a page with a heading, a picture and a formula, is warned of a skipped heading, and publishes it", async ({ page }, testInfo) => {
  const { photo, pdf, page: title } = names(testInfo.project.name);
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openCourse(page, new RegExp(COURSE.title));
  await expect(page.getByRole("heading", { name: COURSE.title, level: 1 })).toBeVisible();

  // The picture is a file on the course first: pages show only the course's own files.
  const week = page.getByRole("region", { name: WEEK });
  await week.getByRole("button", { name: "Upload a file" }).click();
  await week.getByLabel("Title").fill(photo);
  await week.getByLabel(/^File/).setInputFiles({ name: "tray.png", mimeType: "image/png", buffer: PNG });
  await week.getByLabel("Whose material is this?").selectOption({ label: "GSA's own material" });
  await week.getByRole("button", { name: "Upload file" }).click();
  await expect(page.getByRole("status").filter({ hasText: `Added “${photo}”.` })).toBeVisible();
  // And a PDF, which students can see in the page (item 2.14).
  await week.getByRole("button", { name: "Upload a file" }).click();
  await week.getByLabel("Title").fill(pdf);
  await week.getByLabel(/^File/).setInputFiles({ name: "record.pdf", mimeType: "application/pdf", buffer: onePagePdf() });
  await week.getByLabel("Whose material is this?").selectOption({ label: "GSA's own material" });
  await week.getByRole("button", { name: "Upload file" }).click();
  await expect(page.getByRole("status").filter({ hasText: `Added “${pdf}”.` })).toBeVisible();
  await expectAccessible(page, testInfo, "content tab, teaching");

  await week.getByRole("link", { name: "Add a page" }).click();
  await expect(page.getByRole("heading", { name: "New page", level: 1 })).toBeVisible();
  await page.getByLabel("Title").fill(title);
  const text = page.getByRole("textbox", { name: "Page text" });
  const toolbar = page.getByRole("toolbar", { name: "Formatting" });
  await text.click();
  await page.keyboard.type("How seeds wake up");
  // A level 3 heading straight under the page title skips level 2: the check says so as the lecturer writes.
  await toolbar.getByRole("button", { name: "Heading 3" }).click();
  const check = page.getByRole("complementary", { name: "Accessibility check" });
  await expect(check).toContainText("A level 3 heading follows a level 1 heading");

  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await page.keyboard.type("The germination rate is ");
  await toolbar.getByRole("button", { name: "Maths" }).click();
  await page.getByLabel("Formula, written in TeX").fill("\\frac{g}{n} \\times 100");
  await expect(page.getByRole("group", { name: "Maths" }).locator(".katex")).toBeVisible();
  await page.getByRole("button", { name: "Add formula" }).click();

  await toolbar.getByRole("button", { name: "Picture" }).click();
  await page.getByLabel("Picture from this course's files").selectOption({ label: photo });
  await expect(page.getByRole("button", { name: "Add picture" })).toBeDisabled();
  await page.getByLabel(/What the picture shows/).fill(ALT);
  await page.getByRole("button", { name: "Add picture" }).click();
  await expect(text.getByRole("img", { name: ALT })).toBeVisible();
  await expect(text.locator(".katex")).toBeVisible();
  await expectAccessible(page, testInfo, "page editor");

  await page.getByRole("button", { name: "Save and publish" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved and published." })).toHaveText(
    "Saved and published. The accessibility check found 1 thing to look at.",
  );
  await expect(check).toContainText("A level 3 heading follows a level 1 heading");
  await expect(page).toHaveURL(/#\/sites\/\d+\/pages\/\d+\/edit$/);
  await signOut(page);
});

test("a student reads the page, with its picture and the formula drawn", async ({ page }, testInfo) => {
  const { page: title, pdf } = names(testInfo.project.name);
  await signIn(page, PEOPLE.student.username);
  await openCourse(page, new RegExp(COURSE.title));
  await page.getByRole("link", { name: title }).click();
  await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "How seeds wake up", level: 3 })).toBeVisible();
  // A phone is in data-light mode until the person chooses (item 4.05): the picture waits to be asked for.
  if (onPhone(testInfo)) await page.getByRole("button", { name: `Show picture: ${ALT}` }).click();
  const picture = page.getByRole("img", { name: ALT });
  await expect(picture).toBeVisible();
  expect(await picture.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  // KaTeX draws the TeX the page stores, with MathML for screen readers.
  const formula = page.locator("article .katex");
  await expect(formula).toBeVisible();
  await expect(formula.locator("math")).toHaveCount(1);
  await expect(page.getByRole("button", { name: /Edit page/ })).toHaveCount(0);
  await expectAccessible(page, testInfo, "page as a student reads it");

  // Opening the page completed it: the course's Content tab shows it ticked off.
  await page.getByRole("link", { name: `Back to ${COURSE.title}` }).click();
  const item = page.getByRole("region", { name: WEEK }).getByRole("listitem").filter({ hasText: title });
  await expect(item.getByText("Complete", { exact: true })).toBeVisible();
  await expectAccessible(page, testInfo, "content tab, student");

  // A PDF is shown in the page by PDF.js, only when asked (item 2.14).
  const sheet = page.getByRole("region", { name: WEEK }).getByRole("listitem").filter({ hasText: pdf });
  await sheet.getByRole("button", { name: "Show the document here" }).click();
  await expect(sheet.getByText("Page 1 of 1")).toBeVisible();
  await expect(sheet.getByRole("img", { name: `${pdf}, page 1 of 1` })).toBeVisible();
  await expectAccessible(page, testInfo, "PDF in the page");
  await signOut(page);
});

test("a lecturer copies last year's course into this year's with every date moved", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openCourse(page, /AGR102-2026-27-S1-MRP/);
  await page.getByRole("link", { name: /Course setup/ }).click();
  await expect(page.getByRole("heading", { name: "Course setup", level: 1 })).toBeVisible();

  const copy = page.getByRole("region", { name: "Copy from an earlier course" });
  await copy.getByLabel("Course to copy from").selectOption({ label: "Soils and Plant Nutrition (2025-26) (AGR102-2025-26-S1-MRP)" });
  // Last year's first date was Wednesday 1 October 2025; this year the course starts on Monday 5 October 2026.
  await copy.getByLabel("New start date", { exact: true }).fill("2026-10-05");
  // The phone run copies again over the desktop run's copy.
  await copy.getByLabel(/Replace this course's/).check();
  await copy.getByRole("button", { name: "Copy the course" }).click();
  await expect(copy.getByRole("status")).toContainText(/Copied 1 module, 1 item and (1 assignment|0 assignments); every date moved by 369 days\./);

  const dates = page.getByRole("region", { name: "Dates" });
  await expect(dates.getByLabel("Opens: Soil texture report")).toHaveValue("2026-10-05T13:00");
  await expect(dates.getByLabel("Due: Soil texture report")).toHaveValue("2026-10-19T13:00");
  await expect(dates.getByLabel("Shown from: Week 1: Soil texture")).toHaveValue("2026-10-10T08:00");
  await expectAccessible(page, testInfo, "course setup");

  await page.getByRole("link", { name: "Back to Soils and Plant Nutrition" }).click();
  await expect(page.getByRole("heading", { name: "Week 1: Soil texture", level: 2 })).toBeVisible();
  await expect(page.getByText("Shown from 10/10/2026 08:00.")).toBeVisible();
  await signOut(page);
});
