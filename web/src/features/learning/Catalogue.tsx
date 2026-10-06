import { useState, type FormEvent } from "react";
import { post } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { CatalogueCourse, CompletionProgress, Enrol, MyStatus } from "../../api/types-staff";
import { dmy } from "../../app/format";
import { useCrumb } from "../../app/frame";
import { rows, useAction, useData } from "../admin/data";
import { Said, Section } from "../admin/kit";
import { ENROL, STATUS } from "./words";

const statusChip: Record<MyStatus, string> = {
  none: "chip",
  requested: "chip chip-requested",
  enrolled: "chip chip-waiting",
  completed: "chip chip-done",
  renewal_due: "chip chip-due",
};

export function StatusChip({ status }: { status: MyStatus | null }) {
  if (!status || status === "none") return null;
  return <span className={statusChip[status]}>{STATUS[status]}</span>;
}

function hours(course: CatalogueCourse) {
  return course.length_hours ? `About ${Number(course.length_hours)} ${Number(course.length_hours) === 1 ? "hour" : "hours"}` : "";
}

/** One course in a list, opening its page. */
export function CourseRow({ course, onNavigate }: { course: CatalogueCourse; onNavigate: (to: string) => void }) {
  const facts = [course.audience, hours(course), ENROL[course.self_enrol]].filter(Boolean).join(" · ");
  return (
    <li>
      <div className="row-head">
        <a
          className="strong"
          href={`#/learning/${course.site}`}
          onClick={(e) => {
            e.preventDefault();
            onNavigate(`/learning/${course.site}`);
          }}
        >
          {course.title}
        </a>
        <StatusChip status={course.my_status} />
      </div>
      {course.summary && <p className="muted small-gap">{course.summary}</p>}
      <span className="small muted">{facts}</span>
    </li>
  );
}

/** The catalogue (item 5.02): search by words, and narrow by how one joins and where one stands. */
export function Catalogue({ onNavigate }: { onNavigate: (to: string) => void }) {
  const [words, setWords] = useState("");
  const [query, setQuery] = useState("");
  const [enrol, setEnrol] = useState<"" | Enrol>("");
  const [standing, setStanding] = useState<"" | "new" | "mine">("");
  const { data, error } = useData<Paginated<CatalogueCourse>>(
    `/staff-development/catalogue/${query ? `?q=${encodeURIComponent(query)}` : ""}`,
    "Could not load the catalogue.",
  );

  const search = (e: FormEvent) => {
    e.preventDefault();
    setQuery(words.trim());
  };
  const shown = (data ? rows(data) : []).filter(
    (c) =>
      (!enrol || c.self_enrol === enrol) &&
      (!standing || (standing === "new" ? (c.my_status ?? "none") === "none" : (c.my_status ?? "none") !== "none")),
  );

  return (
    <Section title="Catalogue" intro="Courses open to members of staff. Some you join at once; for others your supervisor approves.">
      <form className="filters" role="search" onSubmit={search}>
        <label className="grow">
          <span className="sr-only">Words in the title or summary</span>
          <input type="search" placeholder="Search the catalogue" value={words} onChange={(e) => setWords(e.target.value)} />
        </label>
        <button type="submit">Search</button>
        <label>
          How to join
          <select value={enrol} onChange={(e) => setEnrol(e.target.value as "" | Enrol)}>
            <option value="">Any</option>
            <option value="open">Join at once</option>
            <option value="approval">Needs approval</option>
            <option value="closed">Course administrators enrol</option>
          </select>
        </label>
        <label>
          Show
          <select value={standing} onChange={(e) => setStanding(e.target.value as "" | "new" | "mine")}>
            <option value="">Every course</option>
            <option value="new">Not joined yet</option>
            <option value="mine">Mine</option>
          </select>
        </label>
      </form>
      <Said error={error} />
      {!data && !error && <p className="loading">Loading…</p>}
      {data && shown.length === 0 && <p className="muted">No course matches.</p>}
      {shown.length > 0 && (
        <ul className="rows flush" aria-label="Courses">
          {shown.map((course) => (
            <CourseRow key={course.site} course={course} onNavigate={onNavigate} />
          ))}
        </ul>
      )}
    </Section>
  );
}

/** How far through the completion rules the person is (item 5.03). */
function Progress({ site }: { site: number }) {
  const { data } = useData<CompletionProgress>(`/staff-development/catalogue/${site}/progress/`);
  if (!data) return null;
  return (
    <Section title="Your progress">
      {data.rules.length === 0 ? (
        <p className="muted">A course administrator records when you have completed this course.</p>
      ) : (
        <ul className="rows flush" aria-label="Completion rules">
          {data.rules.map((rule) => (
            <li key={rule.code} className="row-head">
              <span>{rule.label}</span>
              <span className={rule.met ? "chip chip-done" : "chip"}>
                {rule.met ? "Done" : `${rule.done} of ${rule.total}`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

/** One course: what it is, joining it or asking to, and progress once on it. */
export function CoursePage({ site, onNavigate }: { site: number; onNavigate: (to: string) => void }) {
  const { data: course, error, reload } = useData<CatalogueCourse>(`/staff-development/catalogue/${site}/`, "Could not load the course.");
  const [reason, setReason] = useState("");
  const action = useAction();
  useCrumb(course?.title);

  if (error) return <Said error={error} />;
  if (!course) return <p className="loading">Loading…</p>;
  const status = course.my_status;
  const full = course.places_left !== null && course.places_left <= 0;
  const canJoin = (status === "none" || status === "renewal_due") && course.self_enrol !== "closed" && !full;

  const join = (e: FormEvent) => {
    e.preventDefault();
    action.run(async () => {
      const done = await post<{ outcome: "enrolled" | "requested" }>(`/staff-development/catalogue/${site}/join/`, { reason });
      reload();
      return done.outcome === "enrolled"
        ? "You are on the course. It is under My learning and My courses."
        : "Your request has been sent. You will be told when it is decided.";
    });
  };

  return (
    <>
      <Section title={course.title} intro={course.summary || course.description}>
        <dl className="facts">
          <dt>Code</dt>
          <dd>{course.code}</dd>
          {course.audience && (
            <>
              <dt>For</dt>
              <dd>{course.audience}</dd>
            </>
          )}
          {hours(course) && (
            <>
              <dt>Length</dt>
              <dd>{hours(course)}</dd>
            </>
          )}
          <dt>Joining</dt>
          <dd>{ENROL[course.self_enrol]}</dd>
          {course.places_left !== null && (
            <>
              <dt>Places left</dt>
              <dd>{course.places_left}</dd>
            </>
          )}
          {status && (
            <>
              <dt>You</dt>
              <dd>
                {STATUS[status]}
                {course.completed_on && ` on ${dmy(course.completed_on)}`}
                {course.expires_on && `, valid until ${dmy(course.expires_on)}`}
              </dd>
            </>
          )}
        </dl>
        {canJoin && (
          <form className="stack" onSubmit={join}>
            {course.self_enrol === "approval" && (
              <label>
                Why you want to take it (for whoever approves)
                <textarea value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} />
              </label>
            )}
            <div className="actions">
              <button type="submit" disabled={action.busy}>
                {course.self_enrol === "open" ? "Join the course" : "Ask to join"}
              </button>
            </div>
          </form>
        )}
        {status === "none" && full && <p className="muted">The course is full. Ask the course administrator about another run.</p>}
        {status === "none" && course.self_enrol === "closed" && (
          <p className="muted">This course is not open to join. Ask the course administrator.</p>
        )}
        <Said done={action.done} error={action.error} />
        {(status === "enrolled" || status === "completed" || status === "renewal_due") && (
          <div className="actions">
            <button type="button" onClick={() => onNavigate(`/sites/${site}`)}>
              Open the course
            </button>
          </div>
        )}
      </Section>
      {status && status !== "none" && status !== "requested" && <Progress site={site} />}
    </>
  );
}
