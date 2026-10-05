import { COURSE, PEOPLE, expect, expectAccessible, onPhone, search, signIn, signOut, test } from "./support";

/**
 * Items 2.07 to 2.10: a Home for each role, To do, search for everything, breadcrumbs and shareable
 * addresses, on a desktop and a 360px phone with four tabs at the bottom.
 */

test("a student's Home shows what is due this week, new feedback and progress, and To do lists the work", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.student.username);
  await expect(page.getByText(/· Student$/)).toBeVisible();
  const due = page.getByRole("region", { name: "Due this week" });
  await expect(due.getByText("Field notebook check")).toBeVisible();
  await expect(page.getByRole("region", { name: "New feedback" })).toContainText("38 out of 50");
  const progress = page.getByRole("region", { name: "Your progress" });
  await expect(progress.getByRole("link", { name: COURSE.title })).toBeVisible();
  await expectAccessible(page, testInfo, "student home");

  if (onPhone(testInfo)) {
    // Four tabs at the bottom of a phone, each a touch target of 44px or more.
    const tabs = page.getByRole("navigation", { name: "Main" });
    await expect(tabs.getByRole("link")).toHaveText(["Home", /^To do/]);
    await expect(tabs.getByRole("button")).toHaveText(["Search", "Me"]);
    for (const tab of await tabs.locator("a, button").all()) expect((await tab.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await tabs.getByRole("link", { name: /^To do/ }).click();
  } else {
    await page.getByRole("link", { name: /^To do/ }).click();
  }
  await expect(page.getByRole("heading", { name: "To do", level: 1 })).toBeVisible();
  const list = page.getByRole("list", { name: "Waiting for you" });
  await expect(list.getByText("Field notebook check")).toBeVisible();
  await expectAccessible(page, testInfo, "student to do");

  // Search finds the course's assignments, and nobody else: a student never finds people.
  const dialog = await search(page, testInfo, "germination");
  await expect(dialog.getByRole("group", { name: "Assignments" }).getByRole("option", { name: /Germination trial report/ })).toBeVisible();
  await expect(dialog.getByRole("group", { name: "People" })).toHaveCount(0);
  await expectAccessible(page, testInfo, "search");
  await dialog.getByRole("option", { name: /Germination trial report/ }).click();
  await expect(page).toHaveURL(/#\/sites\/\d+\/assignments$/);
  await expect(page.getByRole("tab", { name: "Assignments" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("listitem")).toHaveText([
    "Home",
    "My courses",
    COURSE.title,
  ]);
  await expectAccessible(page, testInfo, "assignments from search");

  // Me: the person's own pages, as a sheet on a phone.
  if (onPhone(testInfo)) {
    await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: "Me" }).click();
    const sheet = page.getByRole("dialog", { name: "Your account" });
    await expect(sheet.getByRole("link", { name: /My data/ })).toBeVisible();
    await expectAccessible(page, testInfo, "me sheet");
    await page.keyboard.press("Escape");
  }
  await signOut(page);
});

test("a lecturer's Home shows work waiting to be marked and students not seen lately", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  await expect(page.getByText(/· Lecturer/)).toBeVisible();
  const marking = page.getByRole("region", { name: "Waiting to be marked" });
  await expect(marking.getByRole("listitem").first()).toContainText("to mark");
  await expect(page.getByRole("region", { name: "Not seen in 14 days" })).toBeVisible();
  await expectAccessible(page, testInfo, "lecturer home");

  // The work to mark opens where it is marked.
  await marking.getByRole("button", { name: /^Open:/ }).first().click();
  await expect(page).toHaveURL(/#\/sites\/\d+\/assignments$/);
  await expect(page.getByRole("heading", { name: COURSE.title, level: 1 })).toBeVisible();

  // Staff find people on the sites they teach.
  const dialog = await search(page, testInfo, "Joseph");
  await expect(dialog.getByRole("group", { name: "People" }).getByRole("option", { name: /Tevin Joseph/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Search" })).toHaveCount(0);
  await signOut(page);
});
