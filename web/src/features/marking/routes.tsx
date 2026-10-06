import { Suspense, type ReactNode } from "react";
import { markingAddress } from "../../app/router";
import { AccommodationsScreen, MarkingScreen, NotificationSettingsScreen, RubricsScreen } from "./lazy";

/** While a screen's code arrives. */
const opening = <p className="loading">Opening…</p>;

/**
 * The screens of assignments, marking, rubrics, accommodations and notification settings that have an address
 * of their own, or null when the address is none of theirs. The server decides who may see what; a person
 * without the role is refused there and the screen says so.
 */
export function markingScreen(path: string, navigate: (to: string) => void): ReactNode | null {
  const at = markingAddress(path);
  let screen: ReactNode = null;
  if (at?.kind === "marking")
    screen = <MarkingScreen key={at.assignmentId} siteId={at.siteId} assignmentId={at.assignmentId} submissionId={at.submissionId} onNavigate={navigate} />;
  else if (at?.kind === "site-rubrics") screen = <RubricsScreen key={at.siteId} siteId={at.siteId} />;
  else if (path === "/rubrics") screen = <RubricsScreen siteId={null} />;
  else if (path === "/accommodations") screen = <AccommodationsScreen />;
  else if (path === "/notification-settings") screen = <NotificationSettingsScreen />;
  return screen && <Suspense fallback={opening}>{screen}</Suspense>;
}
