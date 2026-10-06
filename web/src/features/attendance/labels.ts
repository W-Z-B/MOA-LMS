/** Words and rules the class screens share (items 4.14, 4.15). */

import type { AttendanceStatus, ClassSession } from "../../api/types-talk";
import { longDate } from "../../app/format";
import { clock } from "../forums/shared";

export const STATUS_LABEL: Record<AttendanceStatus, string> = {
  present: "Present",
  late: "Late",
  excused: "Excused",
  absent: "Absent",
};

/** Check-in opens 15 minutes before a class and closes when it ends (attendance.api). */
export function checkInOpen(session: ClassSession, now = Date.now()): boolean {
  return session.takes_attendance && now >= new Date(session.starts_at).getTime() - 15 * 60_000 && now <= new Date(session.ends_at).getTime();
}

/** A day as "2026-10-05" in the device's time. */
export const localDay = (iso: string) => {
  const at = new Date(iso);
  return `${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, "0")}-${String(at.getDate()).padStart(2, "0")}`;
};

/** "Monday 5 October 2026, 09:00 to 10:00", in the device's time. */
export const sessionWhen = (s: ClassSession) => `${longDate(localDay(s.starts_at))}, ${clock(s.starts_at)} to ${clock(s.ends_at)}`;
