import type { Analytics } from "../../api/types-insights";
import { dmy } from "../../app/format";
import { Waiting } from "./shared";
import { percent, useLoad } from "./words";

/**
 * How the class uses the course (item 6.01): who has opened each item, the work handed in and its marks, and the
 * quizzes, each linked to its question statistics. Only what the LMS already records; no time on a page.
 */
export function AnalyticsView({ siteId }: { siteId: number }) {
  const { data, error } = useLoad<Analytics>(`/sites/${siteId}/insights/`, "Could not load how the course is used.");
  if (!data) return <Waiting error={error} />;
  const of = (n: number) => `${n} of ${data.students}`;
  return (
    <>
      <p className="muted">
        {data.students} students. {data.not_recorded}
      </p>

      <h2 id="use-items">Content</h2>
      {data.items.length === 0 ? (
        <p className="muted">No content yet.</p>
      ) : (
        <div className="scroll-x" tabIndex={0} role="region" aria-labelledby="use-items">
          <table>
            <thead>
              <tr>
                <th>Item</th>
                <th>Module</th>
                <th className="num">Opened by</th>
                <th className="num">Downloads</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    {item.title}
                    {!item.is_published && <span className="muted small"> (draft)</span>}
                  </td>
                  <td>{item.module}</td>
                  <td className="num">
                    {of(item.opened)} ({percent(item.opened_percent)})
                  </td>
                  <td className="num">{item.downloads ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 id="use-work">Assignments</h2>
      {data.assignments.length === 0 ? (
        <p className="muted">No published assignments.</p>
      ) : (
        <div className="scroll-x" tabIndex={0} role="region" aria-labelledby="use-work">
          <table>
            <thead>
              <tr>
                <th>Assignment</th>
                <th>Due</th>
                <th className="num">Handed in</th>
                <th className="num">Late</th>
                <th className="num">Missing</th>
                <th className="num">Marked</th>
                <th className="num">Average</th>
                <th className="num">Range</th>
              </tr>
            </thead>
            <tbody>
              {data.assignments.map((a) => (
                <tr key={a.id}>
                  <td>{a.title}</td>
                  <td>{dmy(a.due_at)}</td>
                  <td className="num">{of(a.handed_in)}</td>
                  <td className="num">{a.late}</td>
                  <td className="num">{a.missing}</td>
                  <td className="num">
                    {a.marked} ({a.released} released)
                  </td>
                  <td className="num">{percent(a.average_percent)}</td>
                  <td className="num">{a.lowest_percent == null ? "–" : `${percent(a.lowest_percent)} to ${percent(a.highest_percent)}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 id="use-quizzes">Quizzes</h2>
      {data.quizzes.length === 0 ? (
        <p className="muted">No published quizzes.</p>
      ) : (
        <ul className="rows flush" aria-labelledby="use-quizzes">
          {data.quizzes.map((q) => (
            <li key={q.id} className="bar-row">
              <span className="bar-name">
                <strong>{q.title}</strong>
                {q.is_practice && <span className="muted small"> (practice)</span>}
                <br />
                <span className="small muted">
                  Taken by {of(q.students_attempted)} · {q.attempts} attempts · average {percent(q.average_percent)}
                </span>
              </span>
              <a href={`#${q.statistics}`}>Question statistics</a>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
