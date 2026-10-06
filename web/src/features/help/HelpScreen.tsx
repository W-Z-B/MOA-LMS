import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Me } from "../../api/types";
import { useCrumb } from "../../app/frame";
import type { HelpView } from "../../app/router";
import { AskForHelp } from "./AskForHelp";
import { HelpRequests } from "./HelpRequests";
import { HELP_ROLES, ownRole, roleById, searchAll, taskForTopic, type HelpRole } from "./topics";
import "./help.css";

interface Props {
  me: Me;
  view: HelpView;
  onNavigate: (to: string) => void;
}

/** "Choose **Hand in**": the words on the screen in bold, the rest as written. */
function rich(text: string): ReactNode {
  return text.split(/\*\*(.+?)\*\*/).map((part, at) => (at % 2 ? <strong key={at}>{part}</strong> : <Fragment key={at}>{part}</Fragment>));
}

/**
 * Help inside the LMS (item 7.17): a page for each role with every task as numbered steps, reached from the
 * Help link at the top of every page (which opens the reader's own help at that page's topic), from search,
 * and from the account menu. Anyone can ask for help from here; course administrators answer.
 */
export default function HelpScreen({ me, view, onNavigate }: Props) {
  if (view.view === "ask") return <AskForHelp from={view.from} onNavigate={onNavigate} />;
  if (view.view === "requests") return <HelpRequests me={me} focus={view.id} onNavigate={onNavigate} />;
  if (view.view === "role") {
    const role = roleById(view.role);
    if (!role)
      return (
        <p role="alert" className="error">
          There is no help page at this address. <a href="#/help">See all the help</a>.
        </p>
      );
    return <RolePage role={role} task={view.task} from="" onNavigate={onNavigate} />;
  }
  if (view.view === "topic") {
    const found = taskForTopic(me, view.topic);
    const role = found?.role ?? ownRole(me);
    return <RolePage role={role} task={found?.task.id ?? null} from={view.from} onNavigate={onNavigate} />;
  }
  return <HelpIndex me={me} onNavigate={onNavigate} />;
}

function AskButton({ from, onNavigate }: { from: string; onNavigate: (to: string) => void }) {
  const to = from ? `/help/ask?from=${encodeURIComponent(from)}` : "/help/ask";
  return (
    <a
      className="button-like"
      href={`#${to}`}
      onClick={(e) => {
        e.preventDefault();
        onNavigate(to);
      }}
    >
      Ask for help
    </a>
  );
}

function HelpIndex({ me, onNavigate }: { me: Me; onNavigate: (to: string) => void }) {
  useCrumb(null);
  const own = ownRole(me);
  const [words, setWords] = useState("");
  const hits = useMemo(() => searchAll(words), [words]);
  return (
    <>
      <div className="page-head">
        <h1>Help</h1>
        <AskButton from="/help" onNavigate={onNavigate} />
      </div>
      <p className="lead">How to do each task in the GSA LMS, step by step. Your own help is first.</p>
      <label className="help-search">
        Search the help
        <input type="search" value={words} onChange={(e) => setWords(e.target.value)} placeholder="For example: hand in, register, password" />
      </label>
      {words.trim().length >= 2 && (
        <section aria-label="Help found">
          {hits.length === 0 ? (
            <p className="muted">No help matches that. Try other words, or ask for help.</p>
          ) : (
            <ul className="plain help-hits">
              {hits.map((hit) => (
                <li key={hit.key}>
                  <a href={`#${hit.to}`}>{hit.title}</a> <span className="muted small">{hit.sub}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      <ul className="plain help-roles">
        {[own, ...HELP_ROLES.filter((role) => role !== own)].map((role) => (
          <li key={role.id} className="panel-card padded">
            <h2>
              <a href={`#/help/${role.id}`}>{role === own ? `${role.title} (your help)` : role.title}</a>
            </h2>
            <p className="muted small">{role.who}</p>
          </li>
        ))}
      </ul>
      <p>
        <a href="#/help/requests">{me.roles.some((r) => r === "course_admin" || r === "administrator") ? "Help requests" : "My help requests"}</a>
      </p>
    </>
  );
}

function RolePage({ role, task, from, onNavigate }: { role: HelpRole; task: string | null; from: string; onNavigate: (to: string) => void }) {
  useCrumb(role.title);
  useEffect(() => {
    if (!task) return;
    const heading = document.getElementById(`help-${task}`);
    heading?.scrollIntoView?.({ block: "start" });
    heading?.focus();
  }, [task]);
  return (
    <>
      <div className="page-head">
        <h1>Help for {role.title.toLowerCase()}</h1>
        <AskButton from={from || `/help/${role.id}`} onNavigate={onNavigate} />
      </div>
      <p className="lead">{role.who}</p>
      <nav aria-label="On this page" className="help-contents panel-card padded">
        {role.sections.map((section) => (
          <div key={section.title}>
            <h2 className="small-heading">{section.title}</h2>
            <ul className="plain">
              {section.tasks.map((t) => (
                <li key={t.id}>
                  <a href={`#/help/${role.id}/${t.id}`}>{t.title}</a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      {role.sections.map((section) => (
        <section key={section.title} className="help-section">
          <h2>{section.title}</h2>
          {section.tasks.map((t) => (
            <article key={t.id} className={t.id === task ? "help-task focus" : "help-task"}>
              <h3 id={`help-${t.id}`} tabIndex={-1}>
                {t.title}
              </h3>
              <ol>
                {t.steps.map((step, at) => (
                  <li key={at}>{rich(step)}</li>
                ))}
              </ol>
              {t.note && <p className="help-note">{rich(t.note)}</p>}
            </article>
          ))}
        </section>
      ))}
      <p className="help-foot">
        Still stuck? <AskButton from={from || `/help/${role.id}`} onNavigate={onNavigate} /> <a href="#/help">All the help</a>
      </p>
    </>
  );
}
