import type { Page, TestInfo } from "@playwright/test";
import { PEOPLE, expect, expectAccessible, onPhone, signIn, signOut, test } from "./support";

/**
 * Features 9, 11 to 13, 17 and 18: a lecturer marks a report with its rubric beside the PDF and releases the
 * mark; the student reads the mark, the late penalty and the working of the coursework total; marks come
 * from a spreadsheet, checked before they are applied. seed_journeys's second course (AGR205) holds the work:
 * the desktop run marks Ria Ramdial's, the phone run Andre Fung's, so each run finds work still to mark.
 * Sending coursework to the SRMS is covered by the component tests only: the test stack has no SRMS.
 */

const SOILS = { code: "AGR205-2026-27-S1-MRP", title: "Soil Science and Fertility" } as const;
const STUDENTS = {
  desktop: { username: "ria.ramdial", name: "Ria Ramdial", studentNo: "S2026911" },
  phone: { username: "andre.fung", name: "Andre Fung", studentNo: "S2026912" },
} as const;
const studentFor = (testInfo: TestInfo) => (onPhone(testInfo) ? STUDENTS.phone : STUDENTS.desktop);

async function openSoils(page: Page, tab: "Assignments" | "Gradebook") {
  await page.getByRole("navigation", { name: "Shortcuts" }).getByRole("link", { name: /My courses/ }).click();
  await page.getByRole("button", { name: new RegExp(SOILS.title) }).click();
  await expect(page.getByRole("heading", { name: SOILS.title, level: 1 })).toBeVisible();
  await page.getByRole("tab", { name: tab }).click();
}

async function openMarking(page: Page, assignment: string) {
  await openSoils(page, "Assignments");
  await page.getByRole("region", { name: assignment }).getByRole("link", { name: "Mark" }).click();
  await expect(page.getByRole("heading", { name: assignment, level: 1 })).toBeVisible();
  await expect(page).toHaveURL(/#\/sites\/\d+\/assignments\/\d+\/marking\/\d+$/);
}

test("the lecturer marks a late report with the rubric beside the PDF, and releases the mark", async ({ page }, testInfo) => {
  const student = studentFor(testInfo);
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openMarking(page, "Soil profile report");
  await page.getByRole("combobox", { name: "Student" }).selectOption({ label: `${student.studentNo} ${student.name} · not marked` });
  await expect(page.getByRole("heading", { name: `${student.name} (${student.studentNo})` })).toBeVisible();

  // The work beside the mark: the PDF in the browser's own viewer, framed only by the application itself.
  const work = page.getByRole("region", { name: `Work handed in by ${student.name} (${student.studentNo})` });
  await expect(work.locator("object")).toHaveAttribute("data", /\/submission-files\/\d+\/download\/\?inline=1$/);
  await expect(page.getByRole("complementary", { name: "Mark and feedback" }).getByText("Late", { exact: true })).toBeVisible();
  await expectAccessible(page, testInfo, "marking screen");

  await page.getByText("Every horizon described").click();
  await page.getByText("Some reasoning").click();
  await expect(page.getByText("The rubric fills the mark: 15 out of 20.")).toBeVisible();
  await expect(page.getByText(/5% of the maximum \(1\) is taken, so it counts as 14/)).toBeVisible();
  await page.getByLabel("Feedback", { exact: true }).fill("Every horizon is described. Say more about drainage.");
  await page.getByRole("button", { name: "Save and release" }).click();
  await expect(page.getByRole("status").filter({ hasText: `Released to ${student.name}.` })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Student" })).toContainText(`${student.studentNo} ${student.name} · released`);
  await expectAccessible(page, testInfo, "marking screen after release");
  await signOut(page);
});

test("the student reads the mark, the late penalty and how the coursework total is worked out", async ({ page }, testInfo) => {
  const student = studentFor(testInfo);
  await signIn(page, student.username);
  await openSoils(page, "Assignments");
  const report = page.getByRole("region", { name: "Soil profile report" });
  await expect(report.getByText("Marked", { exact: true })).toBeVisible();
  await report.getByRole("button", { name: "Open" }).click();
  const mark = report.getByRole("region", { name: "Your mark" });
  await expect(mark).toContainText("Marked: 14 out of 20");
  await expect(mark).toContainText("Late penalty: 1 (5% of the maximum) taken from 15.");
  await expect(mark).toContainText("Say more about drainage.");
  await expect(report.getByText("Late work loses 5% of the maximum mark for each day or part of a day late, at most 20%.")).toBeVisible();
  await expectAccessible(page, testInfo, "student's mark");

  await page.getByRole("tab", { name: "Gradebook" }).click();
  const working = page.getByRole("region", { name: "How your coursework total is worked out" });
  await expect(working).toContainText("Coursework total: 70.00%");
  await expect(working).toContainText("15 less a late penalty of 1 = 14 out of 20");
  // The test was handed in but its marks are not released: it waits, and does not count yet.
  await expect(working.getByRole("listitem").filter({ hasText: "Soil texture test" }).getByText("Pending", { exact: true })).toBeVisible();
  await expectAccessible(page, testInfo, "student's working");
  await signOut(page);
});

test("marks from a spreadsheet are checked line by line, then applied", async ({ page }, testInfo) => {
  // Each run gives different marks, so the phone run's lines are changes, not repeats of the desktop run's.
  const [ria, andre] = onPhone(testInfo) ? ["7", "6"] : ["8", "9"];
  const csv = (lines: string[]) => ({ name: "marks.csv", mimeType: "text/csv", buffer: Buffer.from(["student number,mark,feedback", ...lines].join("\n")) });
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openMarking(page, "Soil texture test");
  await page.getByText("The whole class: release, download, marks from a spreadsheet").click();

  const upload = page.getByLabel("Spreadsheet (CSV)");
  await upload.setInputFiles(csv([`S2026911,${ria},Good`, `S2099999,${andre},`]));
  await page.getByRole("button", { name: "Check the file" }).click();
  await expect(page.getByText("1 line is refused. Correct the file and check it again.")).toBeVisible();
  const lines = page.getByRole("region", { name: "Each line of the file" });
  await expect(lines.getByRole("row").filter({ hasText: "S2099999" })).toContainText("Refused: unknown student");
  await expect(page.getByRole("button", { name: /^Apply/ })).toHaveCount(0);
  await expectAccessible(page, testInfo, "spreadsheet check");

  await upload.setInputFiles(csv([`S2026911,${ria},Good`, `S2026912,${andre},Tidy`]));
  await page.getByRole("button", { name: "Check the file" }).click();
  await expect(page.getByText("Checked: 2 marks to save, nothing refused.")).toBeVisible();
  await page.getByRole("button", { name: "Apply 2 marks" }).click();
  await expect(page.getByText("Saved 2 marks as drafts.")).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Student" })).toContainText("S2026912 Andre Fung · draft");
  await signOut(page);
});
