/** How staff development says a course is joined, and where the person stands on it, in words. */

import type { Enrol, MyStatus } from "../../api/types-staff";

export const ENROL: Record<Enrol, string> = {
  open: "Join at once",
  approval: "Needs approval",
  closed: "Course administrators enrol",
};

export const STATUS: Record<MyStatus, string> = {
  none: "Not joined",
  requested: "Asked to join",
  enrolled: "On the course",
  completed: "Completed",
  renewal_due: "Due for renewal",
};
