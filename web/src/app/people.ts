/** Who the signed-in person is, in words, and which parts of the frame are theirs (item 2.07). */

import type { Me } from "../api/types";

/** A person's roles as they say them, never a system code: "Lecturer, AGR101" (from the server). */
export function roleTitle(me: Me): string {
  if (me.title) return me.title;
  if (me.is_superuser) return "System administrator";
  return me.roles.length > 0 ? "" : "No role yet";
}

/** "Mon Repos Campus" reads as "Mon Repos" where space is short. */
export const shortCampus = (name: string) => name.replace(/\s+Campus$/i, "");

/** The campus switch is for staff who look after sites on every campus; students and lecturers see their own. */
export const usesCampusSwitch = (me: Me) =>
  me.persona === "admin" || me.persona === "course_admin" || me.persona === "office";
