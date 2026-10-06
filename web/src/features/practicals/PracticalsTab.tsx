/** A site's Practicals tab (items 3.12, 3.13, 3.15 and 5.15). Each screen has an address under
 * #/sites/:id/practicals, read here so the site screen needs no more than the tab. */

import { useEffect } from "react";
import { usePending } from "../../app/offlineQueue";
import { useHashRoute } from "../../app/router";
import { ChecklistScreen } from "./ChecklistScreen";
import { CompetencyScreen } from "./CompetencyScreen";
import { MyPracticals, PortfolioScreen } from "./MyPracticals";
import { startPhotoOutbox, useWaitingPhotos } from "./photoOutbox";
import { practicalsPath, practicalsView } from "./routes";
import { TaskList } from "./TaskList";
import { TaskScreen } from "./TaskScreen";
import "./practicals.css";

/** What waits on this phone for signal: records and photos. Nothing when nothing does. */
export function FieldWaiting() {
  const records = usePending().filter((q) => q.kind === "practical").length;
  const photos = useWaitingPhotos();
  if (records === 0 && photos === 0) return null;
  const parts = [records > 0 && `${records} ${records === 1 ? "record" : "records"}`, photos > 0 && `${photos} ${photos === 1 ? "photo" : "photos"}`];
  return (
    <p className="sync waiting field-waiting" role="status">
      {parts.filter(Boolean).join(" and ")} waiting on this phone. They are sent when the signal returns.
    </p>
  );
}

export function PracticalsTab({ siteId, teaching }: { siteId: number; teaching: boolean }) {
  const [path, navigate] = useHashRoute();
  const view = practicalsView(path);
  useEffect(startPhotoOutbox, []);

  const sections = teaching
    ? [
        { label: "Tasks", to: practicalsPath(siteId), on: view.view !== "competency" },
        { label: "Competency", to: practicalsPath(siteId, "competency"), on: view.view === "competency" },
      ]
    : [
        { label: "My practicals", to: practicalsPath(siteId), on: view.view !== "portfolio" },
        { label: "Portfolio", to: practicalsPath(siteId, "portfolio"), on: view.view === "portfolio" },
      ];

  let screen;
  if (!teaching) screen = view.view === "portfolio" ? <PortfolioScreen siteId={siteId} /> : <MyPracticals siteId={siteId} />;
  else if (view.view === "observe") screen = <ChecklistScreen siteId={siteId} taskId={view.taskId} personId={view.personId} onNavigate={navigate} />;
  else if (view.view === "task") screen = <TaskScreen siteId={siteId} taskId={view.taskId} onNavigate={navigate} />;
  else if (view.view === "competency") screen = <CompetencyScreen siteId={siteId} personId={view.personId} onNavigate={navigate} />;
  else screen = <TaskList siteId={siteId} onNavigate={navigate} />;

  return (
    <div className="practicals">
      {view.view !== "observe" && (
        <nav className="section-links" aria-label="Practicals">
          {sections.map((s) => (
            <a key={s.label} href={`#${s.to}`} aria-current={s.on ? "page" : undefined}>
              {s.label}
            </a>
          ))}
        </nav>
      )}
      <FieldWaiting />
      {screen}
    </div>
  );
}
