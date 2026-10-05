import { COURSE, PEOPLE, expect, expectAccessible, password, signIn, signOut, test } from "./support";

/** Item 0.20: the first journeys, sign-in, My courses and a course site, on desktop and a 360px phone. */

test("the sign-in page is accessible and refuses a wrong password", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "GSA LMS" })).toBeVisible();
  await expectAccessible(page, testInfo, "sign-in");

  await page.getByLabel("Username").fill(PEOPLE.student.username);
  await page.getByLabel("Password", { exact: true }).fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("Username or password is incorrect.");
});

test("a lecturer cannot go past sign-in without the authenticator code", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username").fill(PEOPLE.lecturer.username);
  await page.getByLabel("Password", { exact: true }).fill(password());
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByLabel("Authenticator code").fill("000000");
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("alert")).toHaveText("The code is not valid.");
  await expect(page.getByRole("heading", { name: "My courses" })).toHaveCount(0);
});

test("a student finds their course, reads the content, and sees their released mark", async ({ page }, testInfo) => {
  const noticeShown = await signIn(page, PEOPLE.student.username);
  // The student reads the privacy notice at their first sign-in (the desktop run comes first), never again.
  if (testInfo.project.name === "desktop" && testInfo.retry === 0) expect(noticeShown).toBe(true);
  if (testInfo.project.name === "phone") expect(noticeShown).toBe(false);
  const course = page.getByRole("button", { name: new RegExp(COURSE.title) });
  await expect(course).toContainText(COURSE.code);
  await expect(course).toContainText("Student");
  await expectAccessible(page, testInfo, "my courses");

  await course.click();
  await expect(page.getByRole("heading", { name: COURSE.title, level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Week 1: What a crop needs" })).toBeVisible();
  await expect(page.getByText("Light, water, air and nutrients")).toBeVisible();
  // Students never see the authoring controls.
  await expect(page.getByRole("button", { name: "Unpublish" })).toHaveCount(0);
  await expectAccessible(page, testInfo, "course content");

  await page.getByRole("tab", { name: "Assignments" }).click();
  await expect(page.getByRole("heading", { name: "Germination trial report" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Crop calendar for a kitchen garden" })).toBeVisible();
  await expectAccessible(page, testInfo, "assignments");

  await page.getByRole("tab", { name: "Gradebook" }).click();
  const rows = page.getByRole("row");
  // A student sees their own row only: the header and one line.
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(1)).toContainText(PEOPLE.student.studentNo);
  await expect(rows.nth(1)).toContainText("76.00");
  await expectAccessible(page, testInfo, "gradebook");

  await page.getByRole("tab", { name: "Announcements" }).click();
  await expect(page.getByRole("heading", { name: "Welcome to the course" })).toBeVisible();
  await signOut(page);
});

test("the lecturer gives an authenticator code and sees the whole class in the gradebook", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await page.getByRole("button", { name: new RegExp(COURSE.title) }).click();
  await expect(page.getByRole("button", { name: "Unpublish" })).toBeVisible();
  await page.getByRole("tab", { name: "Gradebook" }).click();
  await expect(page.getByRole("row")).toHaveCount(3);
  await expectAccessible(page, testInfo, "lecturer gradebook");
  await signOut(page);
});
