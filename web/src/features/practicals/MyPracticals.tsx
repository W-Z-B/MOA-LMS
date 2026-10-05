/** A student's Practicals tab (items 3.12, 3.13 and 5.15): the site's practical tasks with their own
 * observations once released (criteria, comments and photos), their competency results, and their
 * portfolio to read and download. */

import { useEffect, useState } from "react";
import { errorMessage, get } from "../../api/client";
import type { Paginated } from "../../api/types";
import { unitLabel, type CompetencySheet, type Observation, type Portfolio, type PracticalTask } from "../../api/types-practicals";
import { dmy, dmyTime } from "../../app/format";
import { StatusChip } from "./CompetencyScreen";
import { ObservationCard } from "./ObservationCard";
import { windowText } from "./helpers";

export function MyPracticals({ siteId }: { siteId: number }) {
  const [tasks, setTasks] = useState<PracticalTask[] | null>(null);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [sheet, setSheet] = useState<CompetencySheet | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Paginated<PracticalTask>>(`/practical-tasks/?site=${siteId}`)
      .then((r) => setTasks(r.results))
      .catch((err) => setError(errorMessage(err, "Could not load the practical tasks.")));
    get<Paginated<Observation>>(`/observations/?site=${siteId}`)
      .then((r) => setObservations(r.results))
      .catch(() => setObservations([]));
    get<CompetencySheet>(`/sites/${siteId}/competency/`)
      .then(setSheet)
      .catch(() => setSheet(null));
  }, [siteId]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (tasks === null) return <p className="loading">Loading…</p>;
  const units = sheet?.rows[0]?.units ?? [];

  return (
    <>
      {tasks.length === 0 && <p className="muted">No practical tasks on this course yet.</p>}
      {tasks.map((t) => {
        const mine = observations.filter((o) => o.task === t.id);
        return (
          <section key={t.id} className="task-block" aria-labelledby={`task-${t.id}`}>
            <h3 id={`task-${t.id}`}>{t.title}</h3>
            <p className="muted small">
              {unitLabel(t.unit_type)}
              {t.location && `, ${t.location}`} · {windowText(t)} · up to {t.max_attempts} attempts
            </p>
            {t.instructions && <p className="pre">{t.instructions}</p>}
            {t.criteria.length > 0 && (
              <details>
                <summary>What the assessor looks for ({t.criteria.length})</summary>
                <ol>
                  {t.criteria.map((c) => (
                    <li key={c.id}>
                      {c.text} {c.is_critical && <span className="pill critical">Critical</span>}
                    </li>
                  ))}
                </ol>
              </details>
            )}
            {mine.length === 0 ? (
              <p className="muted">No observation released to you yet.</p>
            ) : (
              mine.map((o) => <ObservationCard key={o.id} observation={o} />)
            )}
          </section>
        );
      })}
      {units.length > 0 && (
        <section aria-labelledby="my-competency">
          <h3 id="my-competency">My competency</h3>
          <ul className="plain">
            {units.map((u) => (
              <li key={u.unit_id} className="spread module">
                <span>
                  {u.unit_code} {u.unit_title} <span className="muted small">({u.framework})</span>
                </span>
                {u.result ? (
                  <span className="actions">
                    <StatusChip status={u.result.status} />
                    <span className="muted small">
                      {u.result.assessor}, {dmy(u.result.decided_on)}
                    </span>
                  </span>
                ) : (
                  <span className="muted small">Not assessed yet</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

/** The portfolio: what has been signed off and released, kept after the course ends (item 5.15). */
export function PortfolioScreen({ siteId }: { siteId: number }) {
  const [data, setData] = useState<Portfolio | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Portfolio>(`/portfolio/?site=${siteId}`)
      .then(setData)
      .catch((err) => setError(errorMessage(err, "Could not load your portfolio.")));
  }, [siteId]);

  return (
    <>
      <h2>My practical portfolio</h2>
      <p className="muted">Signed logbook entries, released observations and competency results only. It stays yours after the course ends.</p>
      <div className="actions download-row">
        <a className="button" href={`/api/v1/portfolio/?site=${siteId}&as=html`}>
          Download this course (page to print)
        </a>
        <a className="button" href="/api/v1/portfolio/?as=html">
          Download every course (page to print)
        </a>
        <a className="button" href="/api/v1/portfolio/" download="practical-portfolio.json">
          Download as data (JSON)
        </a>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {data && data.sites.length === 0 && <p className="muted">Nothing has been signed off or released on this course yet.</p>}
      {data?.sites.map((block) => (
        <section key={block.site.id} aria-label={`Portfolio for ${block.site.title}`}>
          <p className="muted small">Produced {dmyTime(data.generated_at)}</p>
          {block.competencies.length > 0 && (
            <>
              <h3>Competency results</h3>
              <ul className="plain">
                {block.competencies.map((c) => (
                  <li key={c.unit_code} className="module">
                    <strong>
                      {c.unit_code} {c.unit_title}
                    </strong>
                    : {c.status} <span className="muted small">({c.assessor}, {dmy(c.decided_on)})</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {block.observations.length > 0 && (
            <>
              <h3>Practical observations</h3>
              <ul className="plain">
                {block.observations.map((o) => (
                  <li key={`${o.task}-${o.attempt}`} className="module">
                    <strong>{o.task}</strong>, attempt {o.attempt}: {o.score}
                    {o.critical_passed ? "" : ", a critical criterion not met"}{" "}
                    <span className="muted small">
                      ({o.assessor}, {dmyTime(o.observed_at)}
                      {o.photos.length > 0 && `, ${o.photos.length} photos`})
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {block.logbook.length > 0 && (
            <>
              <h3>Logbook (signed entries)</h3>
              <ul className="plain">
                {block.logbook.map((e, i) => (
                  <li key={i} className="module">
                    {dmy(e.date)} · {e.unit_type}
                    {e.unit && `, ${e.unit}`}: {e.task} · {e.hours} h <span className="muted small">(signed by {e.signed_by})</span>
                  </li>
                ))}
              </ul>
              <p className="muted small">Hours signed off: {block.logbook_hours.map((h) => `${h.label} ${h.signed_hours}`).join("; ")}</p>
            </>
          )}
        </section>
      ))}
    </>
  );
}
