import { useEffect, useState, type ReactNode } from "react";
import { get, post } from "../api/client";
import type { Campus, Me } from "../api/types";
import { NotificationsBell } from "./NotificationsBell";
import { NAV } from "./router";

interface Props {
  me: Me;
  path: string;
  onNavigate: (to: string) => void;
  onLogout: () => void;
  campusCode: string | null;
  onCampusChange: (code: string | null) => void;
  children: ReactNode;
}

/** Common frame of the GSA ecosystem: top bar, campus switch, role-aware navigation, bottom bar on phones. */
export function Shell({ me, path, onNavigate, onLogout, campusCode, onCampusChange, children }: Props) {
  const [campuses, setCampuses] = useState<Campus[]>([]);

  useEffect(() => {
    get<Campus[]>("/reference/campuses/").then(setCampuses).catch(() => setCampuses([]));
  }, []);

  async function logout() {
    await post("/auth/logout/").catch(() => undefined);
    onLogout();
  }

  const visible = NAV.filter((item) => me.is_superuser || !item.roles || item.roles.some((r) => me.roles.includes(r)));

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">GSA LMS</span>
        <label className="campus">
          <span className="sr-only">Campus</span>
          <select id="campus-switch" value={campusCode ?? ""} onChange={(e) => onCampusChange(e.target.value || null)}>
            <option value="">All campuses</option>
            {campuses.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <span className="spacer" />
        <NotificationsBell onNavigate={onNavigate} />
        <span className="user">
          {me.name} <small>{me.roles.join(", ") || (me.is_superuser ? "superuser" : "no role")}</small>
        </span>
        <button className="link" onClick={logout}>
          Sign out
        </button>
      </header>
      <nav className="sidenav" aria-label="Main">
        {visible.map((item) => (
          <a
            key={item.path}
            href={`#${item.path}`}
            aria-current={path === item.path || (item.path !== "/" && path.startsWith(item.path)) ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              onNavigate(item.path);
            }}
          >
            {item.label}
          </a>
        ))}
      </nav>
      <main className="content">{children}</main>
    </div>
  );
}
