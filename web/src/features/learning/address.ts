export type LearningTab = "catalogue" | "course" | "mine" | "paths" | "certificates" | "approvals" | "required" | "templates";

/**
 * Which part of staff development an address opens. The server's links say /staff-development/... (to-do,
 * notifications, search) and /certificates; the screen's own say /learning/....
 */
export function learningAddress(path: string): { tab: LearningTab; id: number | null } | null {
  const bare = path.split("?")[0];
  const number = (text: string | undefined) => (text ? Number(text) : null);
  if (bare === "/learning" || bare === "/staff-development") return { tab: "catalogue", id: null };
  if (bare === "/certificates" || bare === "/learning/certificates") return { tab: "certificates", id: null };
  let match = bare.match(/^\/staff-development\/requests(?:\/(\d+))?$/);
  if (match) return { tab: "approvals", id: number(match[1]) };
  match = bare.match(/^\/(?:learning|staff-development)\/(\d+)$/);
  if (match) return { tab: "course", id: Number(match[1]) };
  match = bare.match(/^\/learning\/paths(?:\/(\d+))?$/);
  if (match) return { tab: "paths", id: number(match[1]) };
  const tab = bare.match(/^\/learning\/(mine|approvals|required|templates)$/)?.[1] as LearningTab | undefined;
  return tab ? { tab, id: null } : null;
}
