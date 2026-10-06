import { useEffect, useState } from "react";
import { get } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { Takedown } from "../../api/types-content";
import "../content/content.css";
import { ADMIN_SECTIONS } from "./sections";

/** The course administration part of Admin, for course administrators and administrators (items 2.17, 2.19 and
 * 2.20), shown on the console page with the takedown requests waiting. */
export function CourseAdminLinks({ onNavigate }: { onNavigate: (to: string) => void }) {
  const [waiting, setWaiting] = useState<number | null>(null);
  useEffect(() => {
    get<Paginated<Takedown>>("/takedowns/?status=open")
      .then((page) => setWaiting(page.count))
      .catch(() => setWaiting(null));
  }, []);
  return (
    <>
      <h2>Course administration</h2>
      <nav className="shortcuts" aria-label="Course administration">
        {ADMIN_SECTIONS.map((s) => (
          <a
            key={s.path}
            href={`#${s.path}`}
            onClick={(e) => {
              e.preventDefault();
              onNavigate(s.path);
            }}
          >
            <span className="shortcut-title">
              {s.title}
              {s.path === "/admin/takedowns" && waiting ? ` (${waiting} waiting)` : ""}
            </span>
            <span className="shortcut-sub">{s.sub}</span>
          </a>
        ))}
      </nav>
    </>
  );
}
