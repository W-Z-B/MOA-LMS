import type { BrowserContextOptions, Locator, Page } from "@playwright/test";
import { COURSE, PEOPLE, expect, expectAccessible, onPhone, search, signIn, signOut, test } from "./support";

/**
 * Items 4.08 to 4.15 and 2.32: forums with the conduct statement, moderation, messages through the offline
 * queue, the register on a phone, check-in with the code in the room, and the calendar; desktop and 360px.
 * Each journey runs twice (desktop, then phone) on the same data, so each copes with what the first left.
 */

const TEVIN = "tevin.joseph";

/** From Home: My courses, the journey course, and one of its tabs. */
async function openCourse(page: Page, tab: string) {
  await page.getByRole("navigation", { name: "Shortcuts" }).getByRole("link", { name: /My courses/ }).click();
  await page.getByRole("button", { name: new RegExp(COURSE.title) }).click();
  await expect(page.getByRole("heading", { name: COURSE.title, level: 1 })).toBeVisible();
  await page.getByRole("tab", { name: tab }).click();
  await expect(page.getByRole("tab", { name: tab })).toHaveAttribute("aria-selected", "true");
}

/** Accept the conduct statement if it is asked for (the first post or message of each person). */
async function acceptConductIfAsked(page: Page, then: Locator) {
  const accept = page.getByRole("button", { name: "I accept these rules" });
  await expect(accept.or(then).first()).toBeVisible();
  if (await accept.isVisible()) {
    await expect(page.getByText(/Cybercrime Act 2018/)).toBeVisible();
    await accept.click();
  }
  await expect(then).toBeVisible();
}

test("a student answers in a question-and-answer forum after accepting the conduct statement", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.student.username);
  await openCourse(page, "Discussion");
  await expectAccessible(page, testInfo, "discussion tab");
  await page.getByRole("link", { name: /Questions on germination/ }).click();
  await expect(page.getByRole("heading", { name: "Questions on germination", level: 1 })).toBeVisible();
  await expect(page.getByText(/Post your answer to see what others have written/)).toBeVisible();
  await expectAccessible(page, testInfo, "forum");

  await page.getByRole("link", { name: /Why did some seeds not germinate/ }).click();
  await expect(page.getByRole("heading", { name: "Why did some seeds not germinate?", level: 1 })).toBeVisible();
  const answer = page.getByLabel("Your answer", { exact: true });
  const accept = page.getByRole("button", { name: "I accept these rules" });
  await expect(accept.or(answer).first()).toBeVisible();
  if (await accept.isVisible()) {
    await expect(page.getByText(/Cybercrime Act 2018/)).toBeVisible();
    await expectAccessible(page, testInfo, "conduct statement");
    await accept.click();
  }
  await expect(answer).toBeVisible();
  const tevins = page.getByText("The tray was watered too often, so the seeds rotted.");
  // Before her first answer, Kezia does not see Tevin's.
  if (await page.getByText(/This is a question-and-answer forum: post your answer/).isVisible()) await expect(tevins).toHaveCount(0);
  const mine = `They were sown too deep to reach the light (${testInfo.project.name}).`;
  await answer.fill(mine);
  await page.getByRole("button", { name: "Post your answer" }).click();
  await expect(page.getByText(mine)).toBeVisible();
  await expect(tevins).toBeVisible();
  await expect(page.getByRole("article").filter({ hasText: mine }).getByText(/You can change or remove your post until/)).toBeVisible();
  await expectAccessible(page, testInfo, "question and answer");
  await signOut(page);
});

test("the lecturer removes a post with a reason, and pins and locks a discussion", async ({ page }, testInfo) => {
  // Tevin posts an advertisement...
  await signIn(page, TEVIN);
  await openCourse(page, "Discussion");
  await page.getByRole("link", { name: /Class discussion/ }).click();
  await page.getByRole("link", { name: /Where do you buy your seed/ }).click();
  const reply = page.getByLabel("Your reply", { exact: true });
  await acceptConductIfAsked(page, reply);
  const advert = `Cheap seed at my shop, call 600 0000 (${testInfo.project.name})`;
  await reply.fill(advert);
  await page.getByRole("button", { name: "Post reply" }).click();
  await expect(page.getByText(advert)).toBeVisible();
  await signOut(page);

  // ...and the lecturer, a moderator, removes it with a reason everyone sees.
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openCourse(page, "Discussion");
  await page.getByRole("link", { name: /Class discussion/ }).click();
  await page.getByRole("link", { name: /Where do you buy your seed/ }).click();
  const post = page.getByRole("article").filter({ hasText: advert });
  await post.getByRole("button", { name: "Remove" }).click();
  await page.getByLabel(/Why is it removed/).fill("Advertising is not allowed.");
  await page.getByRole("button", { name: "Remove post" }).click();
  await expect(page.getByText("The post is removed.")).toBeVisible();
  await expect(page.getByText(advert)).toHaveCount(0);
  await expect(page.getByText("This post was removed: Advertising is not allowed.").first()).toBeVisible();

  const pin = page.getByRole("button", { name: /^(Pin to the top|Unpin)$/ });
  const pinned = (await pin.textContent()) === "Unpin";
  await pin.click();
  await expect(page.getByRole("button", { name: pinned ? "Pin to the top" : "Unpin" })).toBeVisible();
  await page.getByRole("button", { name: "Lock" }).click();
  await expect(page.getByText("The discussion is locked.")).toBeVisible();
  await expectAccessible(page, testInfo, "moderated discussion");
  // Unlocked again, so the next run can post.
  await page.getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByText("The discussion is unlocked.")).toBeVisible();
  await signOut(page);
});

test("a student writes to the teaching staff without a connection, and it is sent when it returns", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.student.username);
  await page.getByRole("banner").getByRole("link", { name: /^Messages, \d+ unread$/ }).click();
  await expect(page.getByRole("heading", { name: "Messages", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "New message" }).click();
  const subject = page.getByLabel("Subject");
  await acceptConductIfAsked(page, subject);
  // On one course only, it is chosen already; with no one ticked the message goes to all the teaching staff.
  await expect(page.getByLabel("Course")).not.toHaveValue("");
  await expect(page.getByLabel(new RegExp(PEOPLE.lecturer.name))).toBeVisible();
  const title = `Boots for the field trip (${testInfo.project.name})`;
  await subject.fill(title);
  await page.getByLabel("Message", { exact: true }).fill("May I bring my own **boots**?");
  await expectAccessible(page, testInfo, "new message");

  await page.context().setOffline(true);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Waiting to send. It is sent when the connection returns.").first()).toBeVisible();
  await expect(page.getByRole("banner").getByText("1 waiting to send")).toBeVisible();
  // The header keeps everything on the screen while a write waits, even at 360px.
  await expect(page.getByRole("button", { name: /^Signed in as / })).toBeInViewport();
  await expectAccessible(page, testInfo, "message waiting to send");
  await page.context().setOffline(false);
  await expect(page.getByText("Sent", { exact: true })).toBeVisible();
  await expect(page.getByRole("banner").getByText("1 waiting to send")).toHaveCount(0);

  const conversation = page.getByRole("link", { name: new RegExp(title.replace(/[()]/g, "\\$&")) });
  await expect(conversation).toBeVisible();
  await conversation.click();
  await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
  await expect(page.getByRole("list", { name: "Messages" }).getByText("boots")).toBeVisible();
  await expect(page.getByText("Not read yet")).toBeVisible();
  await expectAccessible(page, testInfo, "conversation");
  await signOut(page);
});

test("the lecturer takes the register on a phone, and sees the groups", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openCourse(page, "Classes");
  await page.getByRole("link", { name: "Field practical: seed sowing" }).click();
  const students = page.getByRole("list", { name: "Students" });
  await expect(students.getByRole("radiogroup")).toHaveCount(2);
  if (onPhone(testInfo))
    for (const choice of await students.locator(".seg").all()) expect((await choice.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await expectAccessible(page, testInfo, "register");

  // Each run changes Tevin, so there is always something to save; the rest are present at one tap.
  await page.getByRole("radiogroup", { name: "Tevin Joseph" }).getByText(onPhone(testInfo) ? "Excused" : "Late").click();
  await page.getByRole("button", { name: "Mark the rest present" }).click();
  await page.getByRole("button", { name: /^Save register/ }).click();
  await expect(page.getByText(/^Register saved:/)).toBeVisible();
  await expect(page.getByRole("button", { name: "No changes to save" })).toBeDisabled();

  await page.getByRole("link", { name: "All classes" }).click();
  await expect(page.getByRole("region", { name: "Totals by student" })).toContainText("Tevin Joseph");
  await expect(page.getByRole("button", { name: "Send to the SRMS" })).toBeVisible();
  await expectAccessible(page, testInfo, "classes");

  await page.getByRole("tab", { name: "Groups" }).click();
  await expect(page.getByRole("list", { name: "Groups" })).toContainText("Lab group A");
  await expectAccessible(page, testInfo, "groups");
  await signOut(page);
});

test("a student checks in with the code shown in the room", async ({ page, browser }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await openCourse(page, "Classes");
  await page.getByRole("link", { name: "Soil science lecture" }).click();
  await page.getByRole("link", { name: "Show the check-in code in the room" }).click();
  const shown = page.locator(".check-code [data-code]");
  await expect(shown).toHaveText(/^[A-HJ-NP-Z2-9]{6}$/);
  const code = (await shown.textContent())!.trim();
  await expectAccessible(page, testInfo, "check-in code");

  // The student, on their own phone or computer.
  const context = await browser.newContext(testInfo.project.use as BrowserContextOptions);
  const student = await context.newPage();
  await signIn(student, PEOPLE.student.username);
  await openCourse(student, "Classes");
  await student.getByRole("link", { name: "Soil science lecture" }).click();
  const box = student.getByLabel("Code on the screen");
  const done = student.getByText(/^Your attendance: /);
  await expect(box.or(done).first()).toBeVisible();
  if (await box.isVisible()) {
    await expectAccessible(student, testInfo, "check in");
    await box.fill(code.toLowerCase());
    await student.getByRole("button", { name: "Check in" }).click();
  }
  await expect(student.getByText(/^Your attendance: (present|late)\.$/)).toBeVisible();
  await context.close();
  await signOut(page);
});

test("a student's calendar shows the work due, as an agenda", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.student.username);
  const dialog = await search(page, testInfo, "calendar");
  await dialog.getByRole("option", { name: /^Calendar/ }).click();
  await expect(page.getByRole("heading", { name: "Calendar", level: 1 })).toBeVisible();
  const agenda = page.getByRole("button", { name: "Agenda" });
  // A phone opens on the agenda; a wider screen on the month.
  if (onPhone(testInfo)) await expect(agenda).toHaveAttribute("aria-pressed", "true");
  else {
    await expect(page.getByRole("grid")).toBeVisible();
    await expectAccessible(page, testInfo, "calendar month");
    await agenda.click();
  }
  const due = page.getByRole("link", { name: "Due: Field notebook check" });
  await expect(due).toBeVisible();
  await expect(page.getByRole("link", { name: "Soil science lecture" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your calendar on your phone" })).toBeVisible();
  await expectAccessible(page, testInfo, "calendar agenda");
  await due.click();
  await expect(page.getByRole("tab", { name: "Assignments" })).toHaveAttribute("aria-selected", "true");
  await signOut(page);
});
