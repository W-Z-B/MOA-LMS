import type { StudentProgress } from "../../api/types-insights";
import { ProgressDetail } from "./ProgressDetail";
import { Waiting } from "./shared";
import { useLoad } from "./words";
import "./insights.css";

/** My progress on a course (item 6.02): items done, work handed in and to come, marks so far, and outcomes. */
export function MyProgress({ siteId }: { siteId: number }) {
  const { data, error } = useLoad<StudentProgress>(`/sites/${siteId}/my-progress/`, "Could not load your progress.");
  if (!data) return <Waiting error={error} />;
  return (
    <div className="insights">
      <ProgressDetail data={data} own />
    </div>
  );
}
