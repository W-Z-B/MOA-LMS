/**
 * The Help link at the top of every page (item 7.17): which help topic an address belongs to. Kept small, as
 * the frame loads it on every page; the help itself (features/help) loads only when it is opened.
 */

const TOPICS: readonly [RegExp, string][] = [
  [/^\/sites\/\d+\/assignments\/\d+\/marking/, "marking"],
  [/^\/sites\/\d+\/rubrics/, "rubrics"],
  [/^\/sites\/\d+\/setup/, "setup"],
  [/^\/sites\/\d+\/pages\//, "pages"],
  [/^\/sites\/\d+\/(assignments|gradebook|quizzes|announcements|classes|groups|practicals|logbook)/, "$1"],
  [/^\/sites\/\d+\/discussion/, "forums"],
  [/^\/sites\/\d+/, "content"],
  [/^\/(courses|sites)/, "courses"],
  [/^\/to-do/, "todo"],
  [/^\/messages/, "messages"],
  [/^\/calendar/, "calendar"],
  [/^\/forums/, "forums"],
  [/^\/account/, "account"],
  [/^\/my-data/, "my-data"],
  [/^\/notification-settings/, "notification-settings"],
  [/^\/rubrics/, "rubrics"],
  [/^\/accommodations/, "accommodations"],
  [/^\/(learning|staff-development|certificates)/, "learning"],
  [/^\/admin\/(templates|takedowns|storage)/, "course-admin"],
  [/^\/admin/, "admin"],
];

/** The help topic of an address: "quizzes" for #/sites/4/quizzes/12. Home's for anything else. */
export function helpTopic(path: string): string {
  const bare = path.split("?")[0];
  for (const [pattern, topic] of TOPICS) {
    const match = bare.match(pattern);
    if (match) return topic.replace("$1", match[1] ?? "");
  }
  return "home";
}

/** Where the Help link on a page goes: the reader's help at the page's topic, remembering the page. */
export const helpLink = (path: string) => `/help?topic=${helpTopic(path)}&from=${encodeURIComponent(path)}`;
