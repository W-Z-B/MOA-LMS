import type { Page, TestInfo } from "@playwright/test";
import { COURSE, PEOPLE, expect, expectAccessible, signIn, signOut, test } from "./support";

/**
 * Insight (items 3.11, 6.01 to 6.06), on a desktop and on a 360px phone: a lecturer reads how the class uses a
 * course, each student's progress and the outcomes, and deals with an early alert (the desktop run dismisses
 * Shania Khan's with a reason, the phone run records what was done about Darren Ally's); a student reads their
 * own progress; a head of department reads the reports, with small groups hidden.
 */

const INSIGHT_COURSE = "Farm Records and Planning";
const HEAD = "gail.henry";

async function openCourse(page: Page, title: string) {
  await page.getByRole("navigation", { name: "Shortcuts" }).getByRole("link", { name: /My courses/ }).click();
  await page.getByRole("button", { name: new RegExp(title) }).click();
  await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
}

const insightPart = (page: Page, name: string) => page.getByRole("navigation", { name: "Insights" }).getByRole("link", { name });

test("a lecturer reads the course's use, progress and outcomes, and deals with an early alert", async ({ page }, testInfo: TestInfo) => {
  const desktop = testInfo.project.name === "desktop";
  const student = desktop ? "Shania Khan" : "Darren Ally";
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openCourse(page, INSIGHT_COURSE);
  await page.getByRole("tab", { name: "Insights" }).click();
  await expect(page).toHaveURL(/#\/sites\/\d+\/insights$/);

  // Course use (6.01): from what is already recorded; nothing about time on a page.
  const work = page.getByRole("region", { name: "Assignments" });
  await expect(work.getByRole("row", { name: /Farm diary/ })).toContainText("2 of 2");
  await expect(page.getByText(/Time spent on a page is not recorded/)).toBeVisible();
  await expectAccessible(page, testInfo, "course use");

  // Progress (6.02), with each student's detail.
  await insightPart(page, "Progress").click();
  await expect(page).toHaveURL(/#\/sites\/\d+\/insights\/progress$/);
  const table = page.getByRole("region", { name: "Progress of each student" });
  await table.getByRole("button", { name: new RegExp(student) }).click();
  const detail = page.getByRole("region", { name: `Progress of ${student}` });
  await expect(detail.getByRole("list", { name: "Work" })).toContainText("Missing, counted as 0");
  await expectAccessible(page, testInfo, "class progress");

  // Outcomes (3.11): the course's own, while the SRMS has none, with the evidence linked.
  await insightPart(page, "Outcomes").click();
  await expect(page.getByRole("list", { name: "Evidence for FR1" })).toContainText("Farm diary");
  await expect(page.getByRole("region", { name: "Standing of each student" })).toContainText(/Met \(75%\)/);
  await expectAccessible(page, testInfo, "outcomes");

  // Early alerts (6.05): the evidence is shown and a person decides.
  await insightPart(page, "Early alerts").click();
  const card = page.getByRole("list", { name: "Early alerts" }).getByRole("listitem").filter({ hasText: student }).first();
  await expect(card.getByRole("list", { name: `Evidence for ${student}` })).toContainText("Input log: nothing handed in by the due date");
  await expectAccessible(page, testInfo, "early alerts");
  if (desktop) {
    await card.getByRole("button", { name: "Dismiss" }).click();
    await card.getByLabel("Why nothing needs doing").fill("On approved leave; work rescheduled.");
    await card.getByRole("button", { name: "Dismiss" }).click();
  } else {
    await card.getByRole("button", { name: "Record what was done" }).click();
    await card.getByLabel("What was done").fill("Spoke to Darren after the practical; he will hand both in on Friday.");
    await card.getByRole("button", { name: "Record" }).click();
  }
  await expect(page.getByRole("list", { name: "Early alerts" }).getByText(student)).toHaveCount(0);
  await page.getByRole("checkbox", { name: "Show alerts already dealt with" }).check();
  await expect(page.getByRole("list", { name: "Early alerts" }).getByText(desktop ? /On approved leave/ : /Spoke to Darren/)).toBeVisible();
  await signOut(page);
});

test("a student reads their own progress and never sees Insights", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.student.username);
  await openCourse(page, COURSE.title);
  await expect(page.getByRole("tab", { name: "Insights" })).toHaveCount(0);
  await page.getByRole("tab", { name: "My progress" }).click();
  await expect(page).toHaveURL(/#\/sites\/\d+\/progress$/);
  await expect(page.getByText("Coursework so far")).toBeVisible();
  await expect(page.getByRole("list", { name: "Your work" })).toContainText("Germination trial report");
  await expectAccessible(page, testInfo, "my progress");
  await signOut(page);
});

test("a head of department reads the reports for their unit, with small groups hidden", async ({ page }, testInfo) => {
  await signIn(page, HEAD, { code: true });
  await page.goto("/#/admin/reports");
  await expect(page.getByRole("heading", { name: "Reports", level: 1 })).toBeVisible();
  const sites = page.getByRole("region", { name: "Each site" });
  await expect(sites.getByRole("row", { name: /AGR150-2026-27-S1-MRP/ })).toContainText("Hidden");
  await expect(page.getByRole("link", { name: "Export to a spreadsheet" })).toHaveAttribute("href", "/api/v1/reports/courses/export/");
  await expectAccessible(page, testInfo, "courses report");
  await page.getByRole("tab", { name: "Staff development" }).click();
  await expect(page.getByRole("region", { name: "By unit" }).getByRole("row", { name: /CROPS/ })).toContainText("Hidden");
  await expectAccessible(page, testInfo, "staff development report");
  await signOut(page);
});
