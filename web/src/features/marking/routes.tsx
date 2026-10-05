import type { ReactNode } from "react";
import { markingAddress } from "../../app/router";
import { AccommodationsScreen } from "../accommodations/AccommodationsScreen";
import { NotificationSettingsScreen } from "../notifications/NotificationSettingsScreen";
import { RubricsScreen } from "../rubrics/RubricsScreen";
import { MarkingScreen } from "./MarkingScreen";

/**
 * The screens of assignments, marking, rubrics, accommodations and notification settings that have an address
 * of their own, or null when the address is none of theirs. The server decides who may see what; a person
 * without the role is refused there and the screen says so.
 */
export function markingScreen(path: string, navigate: (to: string) => void): ReactNode | null {
  const at = markingAddress(path);
  if (at?.kind === "marking")
    return <MarkingScreen key={at.assignmentId} siteId={at.siteId} assignmentId={at.assignmentId} submissionId={at.submissionId} onNavigate={navigate} />;
  if (at?.kind === "site-rubrics") return <RubricsScreen key={at.siteId} siteId={at.siteId} />;
  if (path === "/rubrics") return <RubricsScreen siteId={null} />;
  if (path === "/accommodations") return <AccommodationsScreen />;
  if (path === "/notification-settings") return <NotificationSettingsScreen />;
  return null;
}
