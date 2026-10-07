import { useState } from "react";
import { hasAnyRole, type Me } from "../../api/types";
import { COURSE_REPORT_READERS, STAFF_REPORT_READERS, type CourseReport, type StaffReport } from "../../api/types-insights";
import { Figure, Waiting } from "./shared";
import { useLoad } from "./words";
import "./insights.css";

const query = (filters: Record<string, string>) => {
  const kept = Object.entries(filters).filter(([, value]) => value);
  return kept.length ? `?${new URLSearchParams(kept).toString()}` : "";
};

/**
 * Reports that leave a course (items 6.03, 6.04): courses for heads of department and the Registrar, staff
 * development for HR and the Ministry. Each reader sees the rows their role grants cover; groups smaller than
 * five are hidden (item 6.06). Each view and export is in the audit log.
 */
export default function ReportsSection({ me }: { me: Me }) {
  const courses = hasAnyRole(me, COURSE_REPORT_READERS);
  const staff = hasAnyRole(me, STAFF_REPORT_READERS);
  const [which, setWhich] = useState<"courses" | "staff">(courses ? "courses" : "staff");
  return (
    <div className="reports">
      {courses && staff && (
        <div className="tabs sub-tabs" role="tablist" aria-label="Reports">
          <button type="button" role="tab" aria-selected={which === "courses"} className={which === "courses" ? "tab active" : "tab"} onClick={() => setWhich("courses")}>
            Courses
          </button>
          <button type="button" role="tab" aria-selected={which === "staff"} className={which === "staff" ? "tab active" : "tab"} onClick={() => setWhich("staff")}>
            Staff development
          </button>
        </div>
      )}
      {which === "courses" && courses ? <CoursesReport /> : <StaffDevelopmentReport />}
    </div>
  );
}

function CoursesReport() {
  const [filters, setFilters] = useState({ campus: "", programme: "", term: "" });
  const { data, error } = useLoad<CourseReport>(`/reports/courses/${query(filters)}`, "Could not load the report.");
  const set = (key: keyof typeof filters) => (e: { target: { value: string } }) => setFilters((prev) => ({ ...prev, [key]: e.target.value }));
  return (
    <section aria-labelledby="courses-report">
      <h2 id="courses-report">Courses</h2>
      <p className="muted">Content, marking turnaround and coursework sent to the SRMS, by campus and programme.</p>
      {data && (
        <div className="filters">
          <label>
            Campus
            <select value={filters.campus} onChange={set("campus")}>
              <option value="">Every campus</option>
              {data.choices.campuses.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            Programme
            <select value={filters.programme} onChange={set("programme")}>
              <option value="">Every programme</option>
              {data.choices.programmes.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
          <label>
            Term
            <select value={filters.term} onChange={set("term")}>
              <option value="">Every term</option>
              {data.choices.terms.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </label>
          <a className="button" href={`/api/v1/reports/courses/export/${query(filters)}`} download>
            Export to a spreadsheet
          </a>
        </div>
      )}
      {!data ? (
        <Waiting error={error} />
      ) : (
        <>
          <p className="totals" aria-label="Totals">
            <span>{data.total.sites} sites</span>
            <span>{data.total.sites_without_content} with no content</span>
            <span>
              <Figure value={data.total.students} hidden={data.total.hidden} /> students
            </span>
            <span>
              Average days to mark: <Figure value={data.total.turnaround_days} hidden={data.total.hidden} />
            </span>
            <span>
              Waiting more than {data.marking_days} days: <Figure value={data.total.waiting_too_long} hidden={data.total.hidden} />
            </span>
          </p>
          <p className="muted small">Figures about fewer than {data.min_group} people are hidden, with one more group where the total would give them away.</p>
          <h3 id="by-programme">By campus and programme</h3>
          <div className="scroll-x" tabIndex={0} role="region" aria-labelledby="by-programme">
            <table>
              <thead>
                <tr>
                  <th>Campus</th>
                  <th>Programme</th>
                  <th className="num">Sites</th>
                  <th className="num">No content</th>
                  <th className="num">Students</th>
                  <th className="num">Marked</th>
                  <th className="num">Days to mark</th>
                  <th className="num">Sent to the SRMS</th>
                </tr>
              </thead>
              <tbody>
                {data.groups.map((g) => (
                  <tr key={`${g.campus_code}-${g.programme}`}>
                    <td>{g.campus_code || "–"}</td>
                    <td>{g.programme}</td>
                    <td className="num">{g.sites}</td>
                    <td className="num">{g.sites_without_content}</td>
                    <td className="num">
                      <Figure value={g.students} hidden={g.hidden} />
                    </td>
                    <td className="num">
                      <Figure value={g.marked} hidden={g.hidden} />
                    </td>
                    <td className="num">
                      <Figure value={g.turnaround_days} hidden={g.hidden} />
                    </td>
                    <td className="num">
                      <Figure value={g.srms_sent} hidden={g.hidden} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3 id="by-site">Each site</h3>
          {data.sites.length === 0 ? (
            <p className="muted">No sites match.</p>
          ) : (
            <div className="scroll-x" tabIndex={0} role="region" aria-labelledby="by-site">
              <table>
                <thead>
                  <tr>
                    <th>Site</th>
                    <th className="num">Items</th>
                    <th className="num">Students</th>
                    <th className="num">Handed in</th>
                    <th className="num">Marked</th>
                    <th className="num">Days to mark</th>
                    <th className="num">Waiting too long</th>
                    <th className="num">Sent to the SRMS</th>
                  </tr>
                </thead>
                <tbody>
                  {data.sites.map((s) => (
                    <tr key={s.id}>
                      <td>
                        {s.code}
                        <br />
                        <span className="small muted">
                          {s.title}
                          {s.no_content && " · no content"}
                          {!s.is_published && " · not published"}
                        </span>
                      </td>
                      <td className="num">{s.items}</td>
                      <td className="num">
                        <Figure value={s.students} hidden={s.hidden} />
                      </td>
                      <td className="num">
                        <Figure value={s.handed_in} hidden={s.hidden} />
                      </td>
                      <td className="num">
                        <Figure value={s.marked} hidden={s.hidden} />
                      </td>
                      <td className="num">
                        <Figure value={s.turnaround_days} hidden={s.hidden} />
                      </td>
                      <td className="num">
                        <Figure value={s.waiting_too_long} hidden={s.hidden} />
                      </td>
                      <td className="num">
                        {s.hidden ? (
                          <span className="muted">Hidden</span>
                        ) : (
                          `${s.srms_sent} (${s.srms_accepted} accepted${s.srms_unknown ? `, ${s.srms_unknown} not known` : ""})`
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function StaffDevelopmentReport() {
  const [filters, setFilters] = useState({ campus: "", since: "" });
  const { data, error } = useLoad<StaffReport>(`/reports/staff-development/${query(filters)}`, "Could not load the report.");
  return (
    <section aria-labelledby="staff-report">
      <h2 id="staff-report">Staff development</h2>
      <p className="muted">Completions by unit, and required training that is overdue.</p>
      <div className="filters">
        <label>
          Campus
          <input value={filters.campus} onChange={(e) => setFilters((prev) => ({ ...prev, campus: e.target.value.toUpperCase() }))} maxLength={10} placeholder="Every campus" />
        </label>
        <label>
          Completed since
          <input type="date" value={filters.since} onChange={(e) => setFilters((prev) => ({ ...prev, since: e.target.value }))} />
        </label>
        <a className="button" href={`/api/v1/reports/staff-development/export/${query(filters)}`} download>
          Export to a spreadsheet
        </a>
      </div>
      {!data ? (
        <Waiting error={error} />
      ) : (
        <>
          <p className="totals" aria-label="Totals">
            <span>
              <Figure value={data.total.staff} hidden={data.total.hidden} /> staff
            </span>
            <span>
              <Figure value={data.total.completions} hidden={data.total.hidden} /> completions
            </span>
            <span>
              Required training overdue: <Figure value={data.total.overdue} hidden={data.total.hidden} />
            </span>
          </p>
          <p className="muted small">Figures about fewer than {data.min_group} people are hidden, with one more group where the total would give them away.</p>
          <div className="scroll-x" tabIndex={0} role="region" aria-label="By unit">
            <table>
              <thead>
                <tr>
                  <th>Unit</th>
                  <th className="num">Staff</th>
                  <th className="num">Completions</th>
                  <th className="num">Required done</th>
                  <th className="num">Overdue</th>
                </tr>
              </thead>
              <tbody>
                {data.units.map((u) => (
                  <tr key={u.unit_code}>
                    <td>{u.unit_code}</td>
                    <td className="num">
                      <Figure value={u.staff} hidden={u.hidden} />
                    </td>
                    <td className="num">
                      <Figure value={u.completions} hidden={u.hidden} />
                    </td>
                    <td className="num">
                      {u.hidden ? <span className="muted">Hidden</span> : `${u.required_done} of ${u.required}`}
                    </td>
                    <td className="num">
                      <Figure value={u.overdue} hidden={u.hidden} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>By course</h3>
          {data.courses.length === 0 ? (
            <p className="muted">No completions.</p>
          ) : (
            <ul className="rows flush" aria-label="Completions by course">
              {data.courses.map((c) => (
                <li key={c.site} className="bar-row">
                  <span className="bar-name">
                    {c.title} <span className="muted small">{c.code}</span>
                  </span>
                  <span>
                    <Figure value={c.completions} hidden={c.hidden} /> {c.hidden ? "" : "completed"}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="muted small">Who exactly is overdue is in Staff development, under Required training, for course administrators.</p>
        </>
      )}
    </section>
  );
}
