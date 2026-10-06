import type { Page } from "@playwright/test";
import { COURSE, PEOPLE, expect, expectAccessible, signIn, signOut, test } from "./support";

/**
 * Item 6.07: outside tools over LTI 1.3. seed_journeys registers a fictional tool, with names and emails off,
 * and places it on AGR101 with a gradebook column. Its addresses do not exist, so the journeys stop at the
 * launch link; the launch itself, content selection, grades and class lists are tested against a fake tool in
 * api/lti/tests.py. AI help (items 6.11, 6.12) is off in the test stack, as it is by default: its screens are
 * covered by the component tests, and here only its absence is checked.
 */

const TOOL = "Crop growth simulator";
const PLACED = "Maize growth simulation";

async function openCourse(page: Page) {
  await page.getByRole("navigation", { name: "Shortcuts" }).getByRole("link", { name: /My courses/ }).click();
  await page.getByRole("button", { name: new RegExp(COURSE.title) }).click();
  await expect(page.getByRole("heading", { name: COURSE.title, level: 1 })).toBeVisible();
}

test("a course administrator sees each tool, what it receives and the LMS's details for its maker", async ({ page }, testInfo) => {
  await signIn(page, "ayesha.ramdin", { code: true });
  await page.goto("/#/admin");
  await page.getByRole("navigation", { name: "Course administration" }).getByRole("link", { name: /Outside tools/ }).click();
  await expect(page.getByRole("heading", { name: "Outside tools", level: 1 })).toBeVisible();
  await expect(page).toHaveURL(/#\/admin\/tools$/);
  const card = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: TOOL }) });
  await expect(card.getByLabel("Send people's names")).not.toBeChecked();
  await expect(card.getByLabel("Send people's email addresses")).not.toBeChecked();
  await expect(card).toContainText("An identifier for each person that means nothing outside this tool");
  await expect(page.getByRole("region", { name: "The LMS's details, for a tool's maker" })).toContainText("/api/lti/jwks/");
  await expectAccessible(page, testInfo, "outside tools");
  await signOut(page);
});

test("the lecturer sees the tool on the course, what it receives, and sets how its column counts", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openCourse(page);
  // AI help is off for the LMS, so the course has no AI help tab.
  await expect(page.getByRole("tab", { name: "AI help" })).toHaveCount(0);
  await page.getByRole("tab", { name: "Tools" }).click();
  await expect(page).toHaveURL(/#\/sites\/\d+\/tools$/);
  const placed = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: PLACED }) }).first();
  await expect(placed).toContainText("Published");
  await expect(page.getByText(`What ${TOOL} receives`)).toBeVisible();
  const column = page.getByRole("form", { name: `How ${PLACED} counts` });
  await column.getByLabel("Weight").fill("1");
  await column.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toContainText(`Saved how “${PLACED}” counts.`);
  await expectAccessible(page, testInfo, "course tools for teaching staff");
  await signOut(page);
});

test("a student opens the course's tools from the Tools tab and from its module", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.student.username);
  await openCourse(page);
  await expect(page.getByRole("link", { name: `Open ${PLACED} (outside tool, new window)` })).toHaveAttribute("href", /^\/api\/lti\/launch\/\d+\/$/);
  await page.getByRole("tab", { name: "Tools" }).click();
  const open = page.getByRole("link", { name: `Open ${PLACED} (opens in a new window)` });
  await expect(open).toHaveAttribute("href", /^\/api\/lti\/launch\/\d+\/$/);
  await expect(open).toHaveAttribute("target", "_blank");
  await expect(page.getByRole("heading", { name: "Add a tool" })).toHaveCount(0);
  await expectAccessible(page, testInfo, "course tools for students");
  await signOut(page);
});
