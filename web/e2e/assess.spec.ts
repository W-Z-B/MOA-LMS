import { readFileSync } from "node:fs";
import type { Page, TestInfo } from "@playwright/test";
import { PEOPLE, expect, expectAccessible, onPhone, passNotice, search, signIn, signOut, test } from "./support";

/**
 * The similarity check (3.20), paper quizzes (3.24), peer review (4.13), open short courses (5.07) and the
 * guidance on assessment and AI (6.13), on a desktop and a 360px phone. seed_journeys's AGR210 holds three
 * essays, Nadia's copying a passage of Lisa's, each checked and given out for peer review; the desktop run
 * reviews as Lisa, the phone run as Omar. Two registrations for the open course wait for their links.
 */

const FORAGE = { code: "AGR210-2026-27-S1-MRP", title: "Pasture and Forage" } as const;
const REVIEWERS = {
  desktop: { username: "lisa.thomas", name: "Lisa Thomas" },
  phone: { username: "omar.khan", name: "Omar Khan" },
} as const;

function openCourseLink(testInfo: TestInfo): string | undefined {
  const file = process.env.E2E_LINKS_FILE;
  if (!file) throw new Error("Set E2E_LINKS_FILE to the JOURNEY_LINKS_FILE seed_journeys wrote.");
  const links = JSON.parse(readFileSync(file, "utf8")) as { open_courses?: string[] };
  return links.open_courses?.[onPhone(testInfo) ? 1 : 0];
}

async function openForage(page: Page, tab: "Assignments" | "Quizzes") {
  await page.getByRole("navigation", { name: "Shortcuts" }).getByRole("link", { name: /My courses/ }).click();
  await page.getByRole("button", { name: new RegExp(FORAGE.title) }).click();
  await expect(page.getByRole("heading", { name: FORAGE.title, level: 1 })).toBeVisible();
  await page.getByRole("tab", { name: tab }).click();
}

test("the lecturer reads the similarity report beside the mark, and the guidance on reading it", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openForage(page, "Assignments");
  await page.getByRole("region", { name: "Grazing plan essay" }).getByRole("link", { name: "Mark" }).click();
  await expect(page.getByRole("heading", { name: "Grazing plan essay", level: 1 })).toBeVisible();
  await page.getByRole("combobox", { name: "Student" }).selectOption({ label: "S2026933 Nadia Ali · not marked" });
  await expect(page.getByRole("heading", { name: "Nadia Ali (S2026933)" })).toBeVisible();

  await page.getByText("Similarity with other GSA work").click();
  await expect(page.getByText("Overlap is evidence for a person to judge, not a verdict.", { exact: false })).toBeVisible();
  await expect(page.getByText(/% found in other GSA work/)).toBeVisible();
  // Both essays are on a course the lecturer teaches, so the other work is named.
  const match = page.getByRole("heading", { name: /shared with Lisa Thomas \(S2026931\), Grazing plan essay/ });
  await expect(match).toBeVisible();
  const passages = page.getByRole("list", { name: /Matching passages with Lisa Thomas/ });
  await expect(passages.getByText(/six paddocks with electric fencing/).first()).toBeVisible();
  await expectAccessible(page, testInfo, "similarity report");

  await page.getByRole("link", { name: "How to read this report" }).click();
  await expect(page.getByRole("heading", { name: "Assessment and AI: guidance for lecturers", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Why there is no AI detector" })).toBeVisible();
  await expectAccessible(page, testInfo, "assessment and AI guidance");
  // It is found from search too.
  const dialog = await search(page, testInfo, "Assessment and AI");
  await expect(dialog.getByRole("option", { name: /Assessment and AI/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await signOut(page);
});

test("a student reviews a classmate's essay without names, against the rubric", async ({ page }, testInfo) => {
  const reviewer = onPhone(testInfo) ? REVIEWERS.phone : REVIEWERS.desktop;
  await signIn(page, reviewer.username);
  await openForage(page, "Assignments");
  await page.getByRole("region", { name: "Grazing plan essay" }).getByRole("link", { name: "Peer review" }).click();
  await expect(page.getByRole("heading", { name: "Peer review: Grazing plan essay", level: 1 })).toBeVisible();
  await expect(page.getByText(/Names are hidden both ways/)).toBeVisible();
  await expectAccessible(page, testInfo, "peer review list");

  await page.getByRole("link", { name: "Work 1" }).click();
  await expect(page.getByRole("heading", { name: "Grazing plan essay: Work 1", level: 1 })).toBeVisible();
  const work = page.getByRole("region", { name: "The work" });
  await expect(work).not.toContainText(/Lisa|Omar|Nadia|S20269/);
  await page.getByRole("radio", { name: "10 Thorough and accurate" }).check();
  await page.getByRole("radio", { name: "5 Some use" }).check();
  await page.getByLabel("Comment for the student").fill("A clear rotation. Say how the records shaped the plan.");
  await page.getByRole("button", { name: /^Send/ }).click();
  await expect(page.getByRole("status")).toHaveText("Review sent: 15 out of 20.");
  await expectAccessible(page, testInfo, "a review sent");
  await signOut(page);
});

test("the lecturer reads the reviews, and prints a quiz and keys an answer sheet back", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openForage(page, "Assignments");
  await page.getByRole("region", { name: "Grazing plan essay" }).getByRole("link", { name: "Peer review" }).click();
  await expect(page.getByRole("heading", { name: "The work and its reviews" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Show students their reviews" })).toBeVisible();
  await page.getByText(/^S2026931: peer mark/).click();
  await expect(page.getByText(/^Reviewer S20269/).first()).toBeVisible();
  await expectAccessible(page, testInfo, "peer review for the lecturer");

  // A paper for a room without devices, keyed back for one student.
  await page.getByRole("link", { name: "Back to assignments" }).click();
  await page.getByRole("tab", { name: "Quizzes" }).click();
  await page.getByRole("link", { name: "Forage quiz" }).click();
  await page.getByRole("navigation", { name: "Parts of the quiz" }).getByRole("link", { name: "On paper" }).click();
  await page.getByLabel("Title").fill(`Paper test (${testInfo.project.name})`);
  await page.getByLabel("Versions").selectOption({ label: "A only" });
  await page.getByRole("button", { name: "Make the paper" }).click();
  const paper = page.getByRole("region", { name: `Paper test (${testInfo.project.name})` });
  await expect(paper.getByRole("link", { name: "Question paper (A)" })).toHaveAttribute("href", /part=questions/);
  const grid = paper.getByRole("region", { name: "Answers keyed in" });
  await grid.getByLabel("Question 1, Omar Khan").fill("A");
  await grid.getByLabel("Question 2, Omar Khan").fill("T");
  await grid.getByLabel("Question 3, Omar Khan").fill("B");
  await paper.getByRole("button", { name: "Save the answers keyed" }).click();
  await expect(paper.getByRole("status")).toContainText("1 answer sheet saved and marked.");
  await expect(grid.getByRole("row", { name: /Omar Khan/ })).toContainText("3 / 3");
  await expectAccessible(page, testInfo, "a paper quiz keyed");
  await signOut(page);
});

test("someone registers for a short course, finishes from the emailed link and finds it", async ({ page }, testInfo) => {
  await page.goto("/#/open-courses");
  await expect(page.getByRole("heading", { name: "Short courses for farmers and extension officers" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Backyard poultry keeping" })).toBeVisible();
  await page.getByLabel("First name").fill("Visitor");
  await page.getByLabel("Last name").fill(testInfo.project.name);
  await page.getByLabel("Email address").fill(`visitor.${testInfo.project.name}@example.org`);
  await page.getByLabel(/I have read the privacy notice/).check();
  await page.getByRole("button", { name: "Register" }).click();
  await expect(page.getByRole("status")).toContainText("Follow the link in the email");
  await expectAccessible(page, testInfo, "short courses, public");

  // The emailed link (seed_journeys holds one for each project): a password, then sign in with the address.
  const link = openCourseLink(testInfo);
  test.skip(!link, "This project's registration link has been used: seed_journeys again for a fresh one.");
  await page.goto(link!);
  await expect(page.getByRole("heading", { name: "Finish registering" })).toBeVisible();
  const email = onPhone(testInfo) ? "farmer.phone@example.org" : "farmer.desktop@example.org";
  await expect(page.getByText(email)).toBeVisible();
  await expectAccessible(page, testInfo, "finish registering");
  const chosen = "Laying-Hens-Need-Shade-2026";
  await page.getByLabel("Choose a password").fill(chosen);
  await page.getByLabel("The password again").fill(chosen);
  await page.getByRole("button", { name: "Make my account" }).click();
  await expect(page.getByRole("status")).toContainText("Your account is ready.");
  await expect(page.getByLabel("Username")).toHaveValue(email);
  await page.getByLabel("Password", { exact: true }).fill(chosen);
  await page.getByRole("button", { name: "Sign in" }).click();
  await passNotice(page);

  const dialog = await search(page, testInfo, "Short courses");
  await dialog.getByRole("option", { name: /Short courses/ }).click();
  await expect(page.getByRole("heading", { name: "Short courses", level: 1 })).toBeVisible();
  const course = page.getByRole("region", { name: "Backyard poultry keeping" });
  await expect(course.getByRole("link", { name: "Open the course" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "My certificates" })).toBeVisible();
  await expectAccessible(page, testInfo, "short courses, signed in");
  await course.getByRole("link", { name: "Open the course" }).click();
  await expect(page.getByRole("heading", { name: "Backyard poultry keeping", level: 1 })).toBeVisible();
  await signOut(page);
});
