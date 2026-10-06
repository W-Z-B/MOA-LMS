/** What the Admin page lists, and helpers its screens share (items 2.17, 2.19 and 2.20). */

/** A part of the Admin page: one line each, to the screen that does the work. */
export interface AdminSection {
  path: string;
  title: string;
  sub: string;
}

/**
 * The parts of Admin built so far. Only screens that exist are listed: the audit viewer, integration runs,
 * access review and privacy tools join this list when their screens are built.
 */
export const ADMIN_SECTIONS: readonly AdminSection[] = [
  { path: "/admin/templates", title: "Course templates", sub: "The layout every new course starts with" },
  { path: "/admin/takedowns", title: "Takedown requests", sub: "Material reported as not allowed: withdraw it or restore it" },
  { path: "/admin/storage", title: "Storage allowances", sub: "How much each course may keep in files" },
  // --- tools and AI help ---
  { path: "/admin/tools", title: "Outside tools", sub: "Tools courses open without a second sign-in, and what each receives" },
];

/** Plain text written in a template's form becomes paragraphs; text with tags is kept for the server to clean. */
export function asHtml(text: string): string {
  if (/<[a-z][\s\S]*>/i.test(text)) return text;
  return text
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => `<p>${p.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\n/g, "<br>")}</p>`)
    .join("");
}
