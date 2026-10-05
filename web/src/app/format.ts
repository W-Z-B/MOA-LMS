/** How dates and figures are written everywhere in the application (as in the HRMS). */

/** 2026-03-02 reads as 02/03/2026. */
export function dmy(iso: string | null | undefined): string {
  if (!iso) return "";
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}/${month}/${year}`;
}

export function dmyTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** A moment this week, as people say it: "Tuesday 14:00". Further off, the date and time. */
export function when(iso: string, now = new Date()): string {
  const at = new Date(iso);
  const days = Math.abs(at.getTime() - now.getTime()) / 86_400_000;
  const time = at.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  if (days < 6) return `${at.toLocaleDateString("en-GB", { weekday: "long" })} ${time}`;
  return dmyTime(iso);
}

/** "Natasha Khan" reads as "NK", "Indira Devi Narine" as "IN"; a single name gives one letter. */
export function initials(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  const first = parts[0][0];
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** 2026-10-02 reads as "Friday 2 October 2026", the same on every device. */
export function longDate(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  return `${WEEKDAYS[weekday]} ${day} ${MONTHS[month - 1]} ${year}`;
}

export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
