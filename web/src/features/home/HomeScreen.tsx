import { useEffect, useState, type ReactNode } from "react";
import { ApiError, get } from "../../api/client";
import { ADMIN_ROLES, hasAnyRole, type HomeSummary, type Me, type Work } from "../../api/types";
import { roleTitle } from "../../app/people";
import { dmy, dmyTime, longDate, plural, when } from "../../app/format";

interface Props {
  me: Me;
  onNavigate: (to: string) => void;
}

interface Shortcut {
  title: string;
  sub: string;
  to: string;
}

interface Figure {
  label: string;
  value: string | number;
  note: string;
}

interface Item {
  key: string;
  tag: string;
  alert?: boolean;
  who: string;
  detail: string;
  action?: { label: string; to: string };
}

function Shortcuts({ items, onNavigate }: { items: Shortcut[]; onNavigate: (to: string) => void }) {
  return (
    <nav className="shortcuts" aria-label="Shortcuts">
      {items.map((s) => (
        <a
          key={s.title}
          href={`#${s.to}`}
          onClick={(e) => {
            e.preventDefault();
            onNavigate(s.to);
          }}
        >
          <span className="shortcut-title">{s.title}</span>
          <span className="shortcut-sub">{s.sub}</span>
        </a>
      ))}
    </nav>
  );
}

function Figures({ items }: { items: Figure[] }) {
  if (items.length === 0) return null;
  return (
    <section className="figures" aria-label="Figures">
      {items.map((f) => (
        <div className="figure" key={f.label}>
          <span className="figure-label">{f.label}</span>
          <span className="figure-value">{f.value}</span>
          <span className="figure-note">{f.note}</span>
        </div>
      ))}
    </section>
  );
}

function Panel({ title, more, children }: { title: string; more?: { label: string; to: string; go: (to: string) => void }; children: ReactNode }) {
  const id = `panel-${title.toLowerCase().replace(/[^a-z]+/g, "-")}`;
  return (
    <section className="panel-card" aria-labelledby={id}>
      <div className="panel-card-head">
        <h2 id={id}>{title}</h2>
        {more && (
          <a
            href={`#${more.to}`}
            onClick={(e) => {
              e.preventDefault();
              more.go(more.to);
            }}
          >
            {more.label}
          </a>
        )}
      </div>
      {children}
    </section>
  );
}

function Items({ items, empty, go }: { items: Item[]; empty: string; go: (to: string) => void }) {
  if (items.length === 0) return <p className="panel-empty">{empty}</p>;
  return (
    <ul className="rows">
      {items.map((it) => (
        <li key={it.key} className="item-row">
          <span className="stacked grow">
            {it.tag && <span className={it.alert ? "item-tag alert" : "item-tag"}>{it.tag}</span>}
            <span className="strong">{it.who}</span>
            <span className="muted small">{it.detail}</span>
          </span>
          {it.action && (
            <button className="secondary small-button" onClick={() => go(it.action!.to)} aria-label={`${it.action.label}: ${it.who}`}>
              {it.action.label}
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

const KIND: Record<string, string> = { assignment: "Assignment", quiz: "Quiz", practical: "Practical" };

/** One piece of work due: when, what, and where it is handed in. */
function workItem(w: Work, overdue: boolean): Item {
  return {
    key: `${w.kind}-${w.id}`,
    tag: overdue ? `${KIND[w.kind]}, was due ${dmyTime(w.due_at)}` : `${KIND[w.kind]}, due ${when(w.due_at)}`,
    alert: overdue,
    who: w.title,
    detail: overdue && !w.can_still_submit ? `${w.site_title} · no longer accepted` : w.site_title,
    action: overdue && !w.can_still_submit ? undefined : { label: w.kind === "quiz" ? "Open quiz" : "Hand in", to: w.link },
  };
}

/**
 * Home (items 2.07 to 2.09, the HRMS's Home for each role): each person sees their own work first. A student
 * sees what is due this week, what is overdue, new feedback and their progress in each course; teaching staff
 * see work waiting to be marked, sites with nothing new for the coming week and students not seen lately;
 * course administrators and administrators see the sites as a whole. Shortcuts lead to the pages the role
 * uses; search finds the rest.
 */
export function HomeScreen({ me, onNavigate }: Props) {
  const [summary, setSummary] = useState<HomeSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<HomeSummary>("/home/")
      .then((s) => {
        setSummary(s);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Could not load your Home. Try again in a moment."));
  }, []);

  if (!summary)
    return (
      <>
        <h1>Home</h1>
        {error ? (
          <p role="alert" className="error">
            {error}
          </p>
        ) : (
          <p className="loading">Loading…</p>
        )}
      </>
    );

  const go = onNavigate;
  const { student, teaching, sites, persona, waiting } = summary;
  const toDo: Shortcut = { title: "To do", sub: waiting > 0 ? `${waiting} waiting for you` : "Nothing waiting for you", to: "/to-do" };
  const marking = teaching?.to_mark.reduce((n, m) => n + m.count, 0) ?? 0;

  let shortcuts: Shortcut[];
  let figures: Figure[] = [];
  if (persona === "admin" || persona === "course_admin" || persona === "office") {
    shortcuts = [
      { title: "Course sites", sub: sites ? plural(sites.total, "site", "sites") : "Every course site", to: "/courses" },
      toDo,
      ...(hasAnyRole(me, ADMIN_ROLES) ? [{ title: "Admin", sub: "Site creation and ecosystem sync", to: "/admin" }] : []),
      { title: "My account", sub: "Authenticator and signed-in devices", to: "/account" },
    ];
  } else {
    shortcuts = [
      {
        title: "My courses",
        sub: student ? plural(student.progress.length, "course", "courses") : "The sites you teach",
        to: "/courses",
      },
      toDo,
      { title: "My data", sub: "What the LMS holds about you", to: "/my-data" },
    ];
  }
  if (sites)
    figures.push(
      { label: "Course sites", value: sites.total, note: `${sites.published} published · ${sites.drafts} not yet` },
      { label: "Students", value: sites.students, note: "Enrolled in at least one site" },
      { label: "Without a lecturer", value: sites.without_teacher, note: sites.without_teacher ? "Sites nobody teaches yet" : "Every site has one" },
      { label: "Takedown requests", value: sites.open_takedowns, note: sites.open_takedowns ? "Waiting for review" : "None open" },
    );
  if (teaching)
    figures.push(
      { label: "Waiting to be marked", value: marking, note: marking ? plural(teaching.to_mark.length, "piece of work", "pieces of work") : "Nothing waiting" },
      { label: "Nothing new this week", value: teaching.quiet_sites.length, note: teaching.quiet_sites.length ? "Sites to add to" : "Every site has something" },
      { label: `Not seen in ${teaching.not_seen_days} days`, value: teaching.not_seen_count, note: teaching.not_seen_count ? "Students to follow up" : "Everyone has signed in" },
    );
  if (student)
    figures.push(
      { label: "Due this week", value: student.due.length, note: student.due[0] ? `Next: ${student.due[0].title}` : "Nothing due" },
      { label: "Overdue", value: student.overdue.length, note: student.overdue.length ? "Hand it in as soon as you can" : "Nothing overdue" },
      { label: "New feedback", value: student.feedback.length, note: student.feedback.length ? "Marks released lately" : "Nothing new" },
    );
  if (!sites && !teaching && !student) figures = [];

  const title = roleTitle(me);
  const eyebrow = [longDate(summary.as_at), title].filter(Boolean).join(" · ");

  return (
    <div className="home">
      <div className="page-head">
        <div className="stacked">
          <span className="eyebrow">{eyebrow}</span>
          <h1>Home</h1>
        </div>
      </div>

      <Shortcuts items={shortcuts} onNavigate={go} />
      <Figures items={figures} />

      <div className="home-columns">
        <div className="home-main">
          {student && (
            <>
              <Panel title="Due this week" more={{ label: "To do", to: "/to-do", go }}>
                <Items go={go} items={student.due.map((w) => workItem(w, false))} empty="Nothing is due in the next seven days." />
              </Panel>
              {student.overdue.length > 0 && (
                <Panel title="Overdue">
                  <Items go={go} items={student.overdue.map((w) => workItem(w, true))} empty="" />
                </Panel>
              )}
            </>
          )}
          {teaching && (
            <Panel title="Waiting to be marked" more={{ label: "To do", to: "/to-do", go }}>
              <Items
                go={go}
                empty="Nothing is waiting to be marked."
                items={teaching.to_mark.map((m) => ({
                  key: `${m.kind}-${m.link}-${m.title}`,
                  tag: `Waiting since ${dmy(m.oldest)}`,
                  who: m.title,
                  detail: m.site_title,
                  action: { label: "Open", to: m.link },
                }))}
              />
            </Panel>
          )}
          {sites && !teaching && !student && (
            <Panel title="Waiting for you" more={{ label: "All of To do", to: "/to-do", go }}>
              <p className="panel-empty">
                {waiting > 0 ? `${plural(waiting, "thing waits", "things wait")} for you under To do.` : "Nothing is waiting for you."}
              </p>
            </Panel>
          )}
        </div>

        <div className="home-side">
          {student && (
            <>
              <Panel title="New feedback">
                <Items
                  go={go}
                  empty="No marks or feedback were released to you in the last two weeks."
                  items={student.feedback.map((f) => ({
                    key: `${f.kind}-${f.id}`,
                    tag: `${KIND[f.kind]} · released ${dmy(f.released_at)}`,
                    who: f.title,
                    detail: `${f.result} · ${f.site_title}`,
                    action: { label: "Read", to: f.link },
                  }))}
                />
              </Panel>
              <Panel title="Your progress" more={{ label: "My courses", to: "/courses", go }}>
                {student.progress.length === 0 ? (
                  <p className="panel-empty">You are not enrolled on a course yet.</p>
                ) : (
                  <ul className="rows">
                    {student.progress.map((p) => (
                      <li key={p.site_id} className="progress-row">
                        <span className="stacked bar-name">
                          <a
                            href={`#/sites/${p.site_id}`}
                            onClick={(e) => {
                              e.preventDefault();
                              go(`/sites/${p.site_id}`);
                            }}
                          >
                            {p.title}
                          </a>
                          <span className="muted small">
                            {p.released > 0 ? `${p.completed} of ${p.released} items completed` : "Nothing released yet"}
                            {p.coursework_percent !== null ? ` · coursework so far ${p.coursework_percent}%` : ""}
                          </span>
                        </span>
                        <span
                          className="bar"
                          role="img"
                          aria-label={`${Math.round(p.share * 100)}% of ${p.title} completed`}
                        >
                          <span style={{ width: `${Math.min(100, Math.round(p.share * 100))}%` }} />
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </>
          )}
          {teaching && (
            <>
              <Panel title="Nothing new this week">
                <Items
                  go={go}
                  empty="Every site you teach has something new for students this week or next."
                  items={teaching.quiet_sites.map((s) => ({
                    key: String(s.site_id),
                    tag: s.next_item_at ? `Next item opens ${dmy(s.next_item_at)}` : "Nothing set to open",
                    alert: true,
                    who: s.title,
                    detail: s.code,
                    action: { label: "Add content", to: `/sites/${s.site_id}` },
                  }))}
                />
              </Panel>
              <Panel title={`Not seen in ${teaching.not_seen_days} days`}>
                <Items
                  go={go}
                  empty="Every student has signed in lately."
                  items={teaching.not_seen.map((a) => ({
                    key: String(a.person_id),
                    tag: a.last_seen ? `Last seen ${dmy(a.last_seen)}` : "Never signed in",
                    alert: true,
                    who: a.name,
                    detail: [a.student_no, ...a.sites].join(" · "),
                  }))}
                />
                {teaching.not_seen_count > teaching.not_seen.length && (
                  <p className="panel-more">{plural(teaching.not_seen_count - teaching.not_seen.length, "more student", "more students")} not seen</p>
                )}
              </Panel>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
