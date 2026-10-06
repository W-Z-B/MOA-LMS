import { describe, expect, it } from "vitest";
import { classAddress, forumAddress, messageAddress, pageOf, siteAddress } from "./router";

describe("addresses of forums, messages and classes (items 4.08 to 4.15)", () => {
  it("reads every forum, one forum, and a thread in it", () => {
    expect(forumAddress("/forums")).toEqual({ forum: null, thread: null });
    expect(forumAddress("/forums/3")).toEqual({ forum: 3, thread: null });
    expect(forumAddress("/forums/3/threads/7")).toEqual({ forum: 3, thread: 7 });
    expect(forumAddress("/forumsx")).toBeNull();
    expect(pageOf("/forums/3/threads/7")?.label).toBe("Discussion");
  });

  it("reads the conversations and one of them, with a query for a new message", () => {
    expect(messageAddress("/messages")).toEqual({ conversation: null });
    expect(messageAddress("/messages/12")).toEqual({ conversation: 12 });
    expect(messageAddress("/messages?site=4")).toEqual({ conversation: null });
    expect(messageAddress("/message")).toBeNull();
  });

  it("opens a class on the Classes tab, and its check-in code", () => {
    expect(siteAddress("/sites/4/classes/9")).toEqual({ id: 4, tab: "classes" });
    expect(classAddress("/sites/4/classes/9")).toEqual({ session: 9, code: false });
    expect(classAddress("/sites/4/classes/9/code")).toEqual({ session: 9, code: true });
    expect(classAddress("/sites/4/classes")).toBeNull();
    expect(siteAddress("/sites/4/discussion")).toEqual({ id: 4, tab: "discussion" });
    expect(siteAddress("/sites/4/groups")).toEqual({ id: 4, tab: "groups" });
  });
});
