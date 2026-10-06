import { insightsSection, useHashRoute, type InsightsSection } from "../../app/router";
import { AlertsView } from "./AlertsView";
import { AnalyticsView } from "./AnalyticsView";
import { ClassProgress } from "./ClassProgress";
import { OutcomesView } from "./OutcomesView";
import "./insights.css";

const SECTIONS: { key: InsightsSection; label: string }[] = [
  { key: "overview", label: "Course use" },
  { key: "progress", label: "Progress" },
  { key: "outcomes", label: "Outcomes" },
  { key: "alerts", label: "Early alerts" },
];

/**
 * The Insights tab of a course site, for its teaching staff (items 6.01, 6.02, 3.11, 6.05): how the class uses
 * the course, each student's progress, the learning outcomes, and the early alerts. Each part has an address
 * of its own: #/sites/4/insights/alerts.
 */
export function InsightsTab({ siteId }: { siteId: number }) {
  const [path, navigate] = useHashRoute();
  const section = insightsSection(path);
  const base = `/sites/${siteId}/insights`;
  return (
    <div className="insights">
      <nav aria-label="Insights">
        <ul className="tabs plain-tabs sub-tabs">
          {SECTIONS.map((s) => {
            const to = s.key === "overview" ? base : `${base}/${s.key}`;
            return (
              <li key={s.key}>
                <a
                  className={section === s.key ? "tab active" : "tab"}
                  aria-current={section === s.key ? "page" : undefined}
                  href={`#${to}`}
                  onClick={(e) => {
                    e.preventDefault();
                    navigate(to);
                  }}
                >
                  {s.label}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
      {section === "overview" && <AnalyticsView siteId={siteId} />}
      {section === "progress" && <ClassProgress siteId={siteId} />}
      {section === "outcomes" && <OutcomesView siteId={siteId} />}
      {section === "alerts" && <AlertsView siteId={siteId} />}
    </div>
  );
}
