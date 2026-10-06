import { lazy } from "react";

// The screens of assignments, marking, rubrics and the gradebook are fetched when first opened, so none of
// them weighs on the application shell every page loads.
export const AssignmentsTab = lazy(() => import("../assignments/AssignmentsTab").then((m) => ({ default: m.AssignmentsTab })));
export const GradebookTab = lazy(() => import("../gradebook/GradebookTab").then((m) => ({ default: m.GradebookTab })));
export const MarkingScreen = lazy(() => import("./MarkingScreen").then((m) => ({ default: m.MarkingScreen })));
export const RubricsScreen = lazy(() => import("../rubrics/RubricsScreen").then((m) => ({ default: m.RubricsScreen })));
export const AccommodationsScreen = lazy(() => import("../accommodations/AccommodationsScreen").then((m) => ({ default: m.AccommodationsScreen })));
export const NotificationSettingsScreen = lazy(() =>
  import("../notifications/NotificationSettingsScreen").then((m) => ({ default: m.NotificationSettingsScreen })),
);
