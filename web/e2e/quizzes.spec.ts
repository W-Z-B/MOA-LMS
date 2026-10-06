import type { Page, TestInfo } from "@playwright/test";
import { COURSE, PEOPLE, expect, expectAccessible, signIn, signOut, test } from "./support";

/**
 * Feature 10 (items 3.01 to 3.08): a lecturer writes a multiple-choice question, builds a quiz and publishes it;
 * a student takes it, on a desktop and on a 360px phone, and sees the result the review options allow.
 * Each run (desktop, phone) makes its own question and quiz, named after the run, in the course's seeded bank.
 */

const named = (testInfo: TestInfo) => ({
  question: `Plant nutrients (${testInfo.project.name})`,
  quiz: `Quick check (${testInfo.project.name})`,
});

async function openQuizzes(page: Page) {
  await page.getByRole("navigation", { name: "Shortcuts" }).getByRole("link", { name: /My courses/ }).click();
  await page.getByRole("button", { name: new RegExp(COURSE.title) }).click();
  await expect(page.getByRole("heading", { name: COURSE.title, level: 1 })).toBeVisible();
  await page.getByRole("tab", { name: "Quizzes" }).click();
  await expect(page).toHaveURL(/#\/sites\/\d+\/quizzes$/);
}

test("a lecturer writes a question, builds a quiz and publishes it once it is ready", async ({ page }, testInfo) => {
  const names = named(testInfo);
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openQuizzes(page);

  // The question, in the course's bank.
  await page.getByRole("button", { name: "Question banks" }).click();
  await expect(page.getByRole("heading", { name: "Question banks" })).toBeVisible();
  await expect(page.getByLabel("Bank")).toHaveValue(/\d+/);
  await page.getByRole("button", { name: "New question" }).click();
  const editor = page.getByRole("form", { name: /New question: Multiple choice/ });
  await editor.getByLabel(/^Name/).fill(names.question);
  await editor.getByLabel("Question text").fill("Which of these is a plant nutrient?");
  for (const [n, text] of [[1, "Nitrogen"], [2, "Sand"], [3, "Glass"]] as const) {
    await editor.getByRole("group", { name: `Choice ${n}` }).getByLabel("Text").fill(text);
  }
  await editor.getByRole("group", { name: "Choice 1" }).getByLabel("Feedback if chosen").fill("Right: plants take it up as nitrate.");
  await expectAccessible(page, testInfo, "question editor");
  await editor.getByRole("button", { name: "Save question" }).click();
  await expect(page.getByRole("status")).toHaveText(`Saved “${names.question}”.`);
  await expectAccessible(page, testInfo, "question bank");

  // The quiz: the server refuses to publish it without questions, and says why.
  await page.getByRole("button", { name: /All quizzes/ }).click();
  await page.getByLabel("New quiz").fill(names.quiz);
  await page.getByRole("button", { name: "Create quiz" }).click();
  await expect(page.getByRole("heading", { name: names.quiz })).toBeVisible();
  const parts = page.getByRole("navigation", { name: "Parts of the quiz" });
  await parts.getByRole("link", { name: "Settings" }).click();
  await page.getByRole("button", { name: "Publish to students" }).click();
  const refusal = page.getByRole("alert");
  await expect(refusal).toContainText("The quiz cannot be published yet:");
  await expect(refusal).toContainText("Add at least one question.");
  await expectAccessible(page, testInfo, "quiz settings");

  await parts.getByRole("link", { name: "Questions" }).click();
  await page.getByRole("button", { name: "Add questions" }).click();
  await page.getByRole("button", { name: `Add “${names.question}”` }).click();
  await expect(page.getByText(`1. ${names.question}`)).toBeVisible();
  await expectAccessible(page, testInfo, "quiz questions");

  // A practice quiz with a time limit, so it never changes anyone's coursework.
  await parts.getByRole("link", { name: "Settings" }).click();
  await page.getByLabel(/Time limit in minutes/).fill("10");
  await page.getByLabel(/Practice quiz/).check();
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Publish to students" }).click();
  await expect(page.getByText("Students on this course can see it.")).toBeVisible();
  await expectAccessible(page, testInfo, "published quiz");
  await signOut(page);
});

test("a student takes the quiz, each answer is sent, and the review shows what the quiz allows", async ({ page }, testInfo) => {
  const names = named(testInfo);
  await signIn(page, PEOPLE.student.username);
  await openQuizzes(page);
  await expect(page.getByRole("button", { name: "Question banks" })).toHaveCount(0);
  await expectAccessible(page, testInfo, "student quizzes");

  await page.getByRole("link", { name: names.quiz }).last().click();
  await expect(page.getByText("Time limit: 10 minutes, counted by the server from when you start")).toBeVisible();
  await expectAccessible(page, testInfo, "quiz before starting");
  await page.getByRole("button", { name: "Start the quiz" }).click();

  // The countdown comes from the server; the answer is saved as it is given.
  await expect(page.getByRole("timer")).toHaveText(/^(10:00|9:\d\d)$/);
  const question = page.getByRole("region", { name: "Question 1" });
  await expect(question).toContainText("Which of these is a plant nutrient?");
  await question.getByRole("radio", { name: "Nitrogen" }).check();
  await expect(question.getByRole("status")).toHaveText("Sent");
  await expectAccessible(page, testInfo, "attempt");

  await page.getByRole("button", { name: "Finish attempt…" }).click();
  const confirm = page.getByRole("region", { name: "Submit your answers?" });
  await expect(confirm).toContainText("You have answered every question.");
  await expectAccessible(page, testInfo, "submit confirmation");
  await confirm.getByRole("button", { name: "Submit my answers" }).click();

  // Marks and feedback straight away; the right answers only after the quiz closes, which this one never does.
  await expect(page.getByText(/Attempt 1: submitted/)).toBeVisible();
  await expect(page.getByText("100.00%")).toBeVisible();
  const reviewed = page.getByRole("region", { name: "Question 1" });
  await expect(reviewed.getByText("Correct", { exact: true })).toBeVisible();
  await expect(reviewed).toContainText("Answer given: Nitrogen");
  await expect(reviewed).toContainText("Right: plants take it up as nitrate.");
  await expect(reviewed.getByText(/Right answer:/)).toHaveCount(0);
  await expectAccessible(page, testInfo, "review");

  await page.getByRole("button", { name: /All quizzes/ }).click();
  await expect(page.getByText(/1\.00 out of 1 \(100\.00%\)/)).toBeVisible();
  await signOut(page);
});
