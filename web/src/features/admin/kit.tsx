/** Small pieces the staff-development and console screens share: what a change said, sections and tabs. */

import type { ReactNode } from "react";
import "./staff.css";

/** What a change said: a status when it worked, an alert when it did not. */
export function Said({ done, error }: { done?: string | null; error?: string | null }) {
  return (
    <>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {done && (
        <p role="status" className="notice good">
          {done}
        </p>
      )}
    </>
  );
}

/** A section of a page: a card with a heading and what belongs under it. */
export function Section({ title, intro, children }: { title: string; intro?: ReactNode; children: ReactNode }) {
  const id = `section-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <section className="panel-card padded staff-section" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {intro && <p className="muted">{intro}</p>}
      {children}
    </section>
  );
}

/** Tabs that are links, each with an address of its own (item 2.10). */
export function NavTabs({
  label,
  tabs,
  current,
  onNavigate,
}: {
  label: string;
  tabs: { to: string; label: string }[];
  current: string;
  onNavigate: (to: string) => void;
}) {
  return (
    <nav aria-label={label}>
      <ul className="tabs plain-tabs">
        {tabs.map((tab) => (
          <li key={tab.to}>
            <a
              className={tab.to === current ? "tab active" : "tab"}
              aria-current={tab.to === current ? "page" : undefined}
              href={`#${tab.to}`}
              onClick={(e) => {
                e.preventDefault();
                onNavigate(tab.to);
              }}
            >
              {tab.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
