import { describe, expect, it } from "vitest";
import { documentKind, sizeInWords } from "../../api/types-content";
import { adminAddress, contentAddress, pageOf } from "../../app/router";
import { fromLocalInput, toLocalInput } from "./dates";

describe("addresses of pages and course setup (items 2.10 and 2.12)", () => {
  it("reads a page, its editor, a new page in a module and a course's setup from the address", () => {
    expect(contentAddress("/sites/4/setup")).toEqual({ view: "setup", siteId: 4 });
    expect(contentAddress("/sites/4/pages/12")).toEqual({ view: "page", siteId: 4, itemId: 12 });
    expect(contentAddress("/sites/4/pages/12/edit")).toEqual({ view: "edit", siteId: 4, itemId: 12, moduleId: null });
    expect(contentAddress("/sites/4/pages/new?module=7")).toEqual({ view: "edit", siteId: 4, itemId: null, moduleId: 7 });
    expect(contentAddress("/sites/4/pages/new?module=x")).toEqual({ view: "edit", siteId: 4, itemId: null, moduleId: null });
    expect(contentAddress("/sites/4")).toBeNull();
    expect(contentAddress("/sites/4/assignments")).toBeNull();
    // Under My courses in the breadcrumb, as the site itself is.
    expect(pageOf("/sites/4/pages/12")?.label).toBe("My courses");
  });

  it("reads the parts of Admin, and nothing else", () => {
    expect(adminAddress("/admin")).toBe("home");
    expect(adminAddress("/admin/templates")).toBe("templates");
    expect(adminAddress("/admin/takedowns")).toBe("takedowns");
    expect(adminAddress("/admin/storage?x=1")).toBe("storage");
    expect(adminAddress("/admin/audit")).toBeNull();
    expect(adminAddress("/administer")).toBeNull();
    expect(pageOf("/admin/templates")?.label).toBe("Admin");
  });
});

describe("words and dates on these screens", () => {
  it("writes sizes as people read them", () => {
    expect(sizeInWords(0)).toBe("nothing");
    expect(sizeInWords(100)).toBe("1 KB");
    expect(sizeInWords(5 * 1024 * 1024)).toBe("5 MB");
    expect(sizeInWords(2 * 1024 ** 3)).toBe("2 GB");
    expect(sizeInWords(1.5 * 1024 ** 3)).toBe("1.5 GB");
  });

  it("tells documents shown in the page from those only downloaded", () => {
    expect(documentKind("Map.PDF")).toBe("pdf");
    expect(documentKind("a.jpeg")).toBe("image");
    expect(documentKind("a.webp")).toBe("image");
    expect(documentKind("a.heic")).toBe("other");
    expect(documentKind(null)).toBe("other");
  });

  it("turns moments into the date fields' values and back", () => {
    expect(toLocalInput(null)).toBe("");
    expect(fromLocalInput("")).toBeNull();
    const local = "2027-01-12T09:05";
    expect(toLocalInput(fromLocalInput(local))).toBe(local);
  });
});
