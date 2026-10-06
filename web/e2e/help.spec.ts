import type { Page, TestInfo } from "@playwright/test";
import { COURSE, PEOPLE, expect, expectAccessible, onPhone, search, signIn, signOut, test } from "./support";

/**
 * Item 7.17: help inside the LMS and a way to ask for it. A student opens the help for the page they are on,
 * finds a task through search, and asks for help with the page sent along; the administrator (the journey
 * cast has no course administrator, so requests go to the administrators) answers from To do; the student
 * reads the answer. On a desktop and on a 360px phone; each run asks its own question.
 */

/** The fictional administrator of the console journeys (seed_journeys). */
const ADMINISTRATOR = "ayesha.ramdin";

const subject = (testInfo: TestInfo) => `Where is the practice quiz? (${testInfo.project.name})`;

async function openToDo(page: Page, testInfo: TestInfo) {
  if (onPhone(testInfo)) await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: /^To do/ }).click();
  else await page.getByRole("banner").getByRole("link", { name: /^To do/ }).click();
  await expect(page.getByRole("heading", { name: "To do", level: 1 })).toBeVisible();
}

test("a student opens the help for the page they are on, finds a task through search, and asks for help", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.student.username);
  await page.getByRole("navigation", { name: "Shortcuts" }).getByRole("link", { name: /My courses/ }).click();
  await page.getByRole("button", { name: new RegExp(COURSE.title) }).click();
  await page.getByRole("tab", { name: "Quizzes" }).click();
  await expect(page).toHaveURL(/#\/sites\/\d+\/quizzes$/);
  const quizzes = new URL(page.url()).hash.slice(1);

  // The Help link at the top of the page opens the student's own help at quizzes.
  await page.getByRole("link", { name: "Help with this page" }).click();
  await expect(page.getByRole("heading", { name: "Help for students", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Take a quiz", level: 3 })).toBeFocused();
  await expect(page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("listitem")).toHaveText(["Home", "Help", "Students"]);
  await expectAccessible(page, testInfo, "help for students");

  // Search finds help as well as pages.
  const dialog = await search(page, testInfo, "logbook entry");
  const help = dialog.getByRole("group", { name: "Help" });
  await help.getByRole("option", { name: /Write a logbook entry/ }).click();
  await expect(page).toHaveURL(/#\/help\/student\/logbook$/);
  await expect(page.getByRole("heading", { name: "Write a logbook entry", level: 3 })).toBeFocused();

  // Ask for help, from the quizzes page: the page goes with the question.
  await page.goto(`/#/help?topic=quizzes&from=${encodeURIComponent(quizzes)}`);
  await page.getByRole("link", { name: "Ask for help" }).first().click();
  await expect(page.getByRole("heading", { name: "Ask for help", level: 1 })).toBeVisible();
  await page.getByLabel("What do you need help with?").fill(subject(testInfo));
  await page.getByLabel("What were you trying to do, and what happened?").fill("I was told there is a practice quiz, but I cannot see it.");
  await expect(page.getByLabel(/Send the page I was on/)).toBeChecked();
  await expectAccessible(page, testInfo, "ask for help");
  await page.getByRole("button", { name: "Send to the course administrators" }).click();
  await expect(page.getByRole("status")).toContainText("Sent. The course administrators have your request");
  await page.getByRole("link", { name: "My help requests" }).click();
  const mine = page.getByRole("listitem").filter({ hasText: subject(testInfo) });
  await expect(mine).toContainText("Waiting for an answer");
  await expect(mine.getByRole("link", { name: "Open the page I was on" })).toHaveAttribute("href", `#${quizzes}`);
  await expectAccessible(page, testInfo, "my help requests");
  await signOut(page);
});

test("the administrator answers the request from To do, and the student reads the answer", async ({ page }, testInfo) => {
  await signIn(page, ADMINISTRATOR, { code: true });
  await openToDo(page, testInfo);
  const waiting = page.getByRole("list", { name: "Waiting for you" }).getByRole("listitem").filter({ hasText: subject(testInfo) });
  await expect(waiting).toContainText("Help request to answer");
  await waiting.getByRole("button", { name: /^Open: / }).click();
  await expect(page.getByRole("heading", { name: "Help requests", level: 1 })).toBeVisible();
  const card = page.getByRole("listitem").filter({ hasText: subject(testInfo) });
  await expect(card).toContainText(`From ${PEOPLE.student.name}`);
  await expect(card.getByRole("link", { name: "Open the page they were on" })).toHaveAttribute("href", /#\/sites\/\d+\/quizzes$/);
  await expectAccessible(page, testInfo, "help requests");
  await card.getByLabel("Your answer").fill("The practice quiz is in the orientation course, on its Quizzes tab.");
  await card.getByRole("button", { name: "Send the answer" }).click();
  await expect(page.getByRole("status")).toContainText("is sent");
  await signOut(page);

  await signIn(page, PEOPLE.student.username);
  await page.getByRole("button", { name: /^Notifications/ }).click();
  await page.getByRole("dialog", { name: "Notifications" }).getByText(`Your help request is answered: ${subject(testInfo)}`).click();
  await expect(page).toHaveURL(/#\/help\/requests$/);
  await expect(page.getByRole("listitem").filter({ hasText: subject(testInfo) })).toContainText("The practice quiz is in the orientation course");
  await signOut(page);
});
