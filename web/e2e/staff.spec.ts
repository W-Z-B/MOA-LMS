import { readFileSync } from "node:fs";
import { PEOPLE, expect, expectAccessible, passNotice, search, signIn, signOut, test } from "./support";

/**
 * Accounts, staff development, certificates and the console (items 1.10, 1.17 to 1.23, 5.02 to 5.11), on a
 * desktop and a 360px phone: a new student chooses a password from an invitation and signs in, a member of
 * staff joins a course from the catalogue, an administrator checks the audit log, and anyone checks a
 * certificate without signing in.
 */

/** What seed_journeys wrote for the journeys: one invitation link for each project, and a certificate. */
interface Links {
  invitations: string[];
  certificate: { reference: string; code: string };
}

function links(): Links {
  const file = process.env.E2E_LINKS_FILE;
  if (!file) throw new Error("Set E2E_LINKS_FILE to the JOURNEY_LINKS_FILE seed_journeys wrote.");
  return JSON.parse(readFileSync(file, "utf8")) as Links;
}

/** The fictional administrator of the console journeys (seed_journeys), with the same fictional authenticator. */
const ADMINISTRATOR = "ayesha.ramdin";

test("a new student chooses a password from the invitation, then signs in with it", async ({ page }, testInfo) => {
  // One invitation for each project: a link works once.
  const link = links().invitations[testInfo.project.name === "phone" ? 1 : 0];
  test.skip(!link, "This project's invitation has been used: seed_journeys again for a fresh link.");
  await page.goto(link);
  await expect(page.getByRole("heading", { name: "Welcome: choose your password" })).toBeVisible();
  const username = await page.locator("strong").first().innerText();
  await expect(page.getByText(/At least 12 characters/)).toBeVisible();
  await expectAccessible(page, testInfo, "choose a password");

  const chosen = "Mango-Season-Starts-2026";
  await page.getByLabel("New password", { exact: true }).fill(chosen);
  await page.getByLabel("New password again").fill("Something-Else-2026");
  await page.getByRole("button", { name: "Save my password" }).click();
  await expect(page.getByRole("alert")).toHaveText("The two passwords are not the same.");
  await page.getByLabel("New password again").fill(chosen);
  await page.getByRole("button", { name: "Save my password" }).click();

  // Back at sign-in, with the username filled in and a word that the password is saved.
  await expect(page.getByRole("status")).toHaveText("Your password is saved. Sign in with it now.");
  await expect(page.getByLabel("Username")).toHaveValue(username);
  await expectAccessible(page, testInfo, "sign-in after choosing a password");
  await page.getByLabel("Password", { exact: true }).fill(chosen);
  await page.getByRole("button", { name: "Sign in" }).click();
  await passNotice(page);
  await expect(page.getByRole("heading", { name: "Home", level: 1 })).toBeVisible();

  // The link has done its work: it opens nothing now.
  await signOut(page);
  await page.goto(link);
  await expect(page.getByRole("alert")).toContainText("expired or has already been used");
  await page.getByRole("button", { name: "Ask for a new link" }).click();
  await expect(page.getByRole("heading", { name: "Forgot your password?" })).toBeVisible();
  await expectAccessible(page, testInfo, "forgot password");
});

test("a member of staff joins a course from the catalogue and finds it under My learning", async ({ page }, testInfo) => {
  await signIn(page, PEOPLE.lecturer.username, { code: true });
  const dialog = await search(page, testInfo, "Staff development");
  await dialog.getByRole("group", { name: "Pages" }).getByRole("option", { name: /^Staff development/ }).click();
  await expect(page.getByRole("heading", { name: "Staff development", level: 1 })).toBeVisible();
  const courses = page.getByRole("list", { name: "Courses" });
  await expect(courses.getByRole("link", { name: "Safe use of farm machinery" })).toBeVisible();
  await expectAccessible(page, testInfo, "staff-development catalogue");

  await page.getByRole("searchbox", { name: "Words in the title or summary" }).fill("machinery");
  await page.getByRole("region", { name: "Catalogue" }).getByRole("button", { name: "Search", exact: true }).click();
  await expect(courses.getByRole("listitem")).toHaveCount(1);
  await courses.getByRole("link", { name: "Safe use of farm machinery" }).click();
  await expect(page.getByRole("heading", { name: "Safe use of farm machinery", level: 2 })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("listitem")).toHaveText([
    "Home",
    "Staff development",
    "Safe use of farm machinery",
  ]);
  // The desktop run joins; the phone run, on the same data, finds the course already joined.
  const join = page.getByRole("button", { name: "Join the course" });
  if (await join.isVisible()) {
    await join.click();
    await expect(page.getByRole("status")).toContainText("You are on the course.");
  }
  await expect(page.getByRole("button", { name: "Open the course" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Completion rules" })).toBeVisible();
  await expectAccessible(page, testInfo, "a staff-development course");

  await page.getByRole("navigation", { name: "Staff development" }).getByRole("link", { name: "My learning" }).click();
  const mine = page.getByRole("list", { name: "My courses" });
  await expect(mine.getByRole("link", { name: "Safe use of farm machinery" })).toBeVisible();
  await expect(mine).toContainText("On the course");
  await expect(mine).toContainText("First aid in the field"); // completed, with its certificate
  await expectAccessible(page, testInfo, "my learning");

  await page.getByRole("navigation", { name: "Staff development" }).getByRole("link", { name: "Certificates" }).click();
  await expect(page.getByRole("link", { name: /^Download \(PDF\): GSA\/LMS\// })).toBeVisible();
  await expectAccessible(page, testInfo, "my certificates");
  await signOut(page);
});

test("an administrator opens the audit log and checks the chain", async ({ page }, testInfo) => {
  await signIn(page, ADMINISTRATOR, { code: true });
  const dialog = await search(page, testInfo, "audit log");
  await dialog.getByRole("group", { name: "Pages" }).getByRole("option", { name: /^Admin/ }).click();
  await expect(page.getByRole("heading", { name: "Admin", level: 1 })).toBeVisible();
  const sections = page.getByRole("navigation", { name: "Admin sections" });
  await expect(sections.getByRole("link")).toHaveCount(8);
  await expectAccessible(page, testInfo, "admin");

  await sections.getByRole("link", { name: /Audit log/ }).click();
  await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();
  await expect(page).toHaveURL(/#\/admin\/audit$/);
  await expect(page.getByRole("list", { name: "Audit entries" }).getByRole("listitem").first()).toBeVisible();
  await page.getByRole("button", { name: "Check the chain now" }).click();
  await expect(page.getByRole("status")).toContainText("Every entry matches its fingerprint");
  await expect(page.getByText("Intact", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Export to a spreadsheet (CSV)" })).toHaveAttribute("href", /\/api\/v1\/audit\/export\//);
  await expectAccessible(page, testInfo, "audit log");

  // The check is itself in the log.
  await page.reload();
  await page.getByLabel("What was done").selectOption({ label: "Audit log checked" });
  await page.getByRole("button", { name: "Show the entries" }).click();
  await expect(page.getByRole("list", { name: "Audit entries" })).toContainText("Audit log checked");
  await signOut(page);
});

test("anyone shown a certificate checks it from the sign-in page, without signing in", async ({ page }, testInfo) => {
  const { reference, code } = links().certificate;
  await page.goto("/");
  await page.getByRole("link", { name: "Check a GSA certificate" }).click();
  await expect(page.getByRole("heading", { name: /Check a certificate from/ })).toBeVisible();
  await page.getByLabel("Reference").fill(reference);
  await page.getByLabel("Code").fill("WRONG-CODE-0000");
  await page.getByRole("button", { name: "Check" }).click();
  await expect(page.getByRole("status")).toContainText("No certificate matches");

  await page.getByLabel("Code").fill(code.toLowerCase());
  await page.getByRole("button", { name: "Check" }).click();
  const answer = page.getByRole("status");
  await expect(answer).toContainText("This certificate is genuine");
  await expect(answer).toContainText("Marlon Bacchus");
  await expect(answer).toContainText("First aid in the field");
  await expect(answer).toContainText("Valid until");
  await expectAccessible(page, testInfo, "certificate check");
});

test("the sign-in page offers a link for a forgotten password", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Forgot your password?" }).click();
  await page.getByLabel("Username or email address").fill("S2026999");
  await page.getByRole("button", { name: "Email me a link" }).click();
  await expect(page.getByRole("status")).toContainText("a link to choose a new password is on its way");
  await expectAccessible(page, testInfo, "forgot password sent");
  await page.getByRole("button", { name: "Back to sign in" }).click();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});
