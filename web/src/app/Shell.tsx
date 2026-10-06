import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { get, post } from "../api/client";
import type { Campus, Me, WaitingItem } from "../api/types";
import { AccountMenu } from "./AccountMenu";
import { Breadcrumbs } from "./Breadcrumbs";
import { CampusSwitch } from "./CampusSwitch";
import { Crest } from "./Crest";
import { FrameContext, usePhone, type Frame } from "./frame";
import { helpLink } from "./help";
import { MessagesLink } from "../features/messages/MessagesLink";
import { NotificationsBell } from "./NotificationsBell";
import { usesCampusSwitch } from "./people";
import { SearchPalette } from "./SearchPalette";
import { PendingCount } from "./SendState";

interface Props {
  me: Me;
  path: string;
  onNavigate: (to: string) => void;
  onLogout: () => void;
  campusCode: string | null;
  onCampusChange: (code: string | null) => void;
  children: ReactNode;
}

const POLL_MS = 60_000;
/** Moving between pages fetches the To do count again, but no more often than this. */
const FRESH_MS = 10_000;

/** How many things wait for this person, kept fresh as they move about. */
function useWaitingCount(path: string): [number, () => void] {
  const [count, setCount] = useState(0);
  const fetchedAt = useRef(0);

  const load = useCallback((force: boolean) => {
    if (!force && Date.now() - fetchedAt.current < FRESH_MS) return;
    fetchedAt.current = Date.now();
    get<WaitingItem[]>("/to-do/")
      .then((items) => setCount(items.length))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const handle = setInterval(() => load(true), POLL_MS);
    return () => clearInterval(handle);
  }, [load]);
  useEffect(() => load(false), [path, load]);

  return [count, useCallback(() => load(true), [load])];
}

/**
 * The frame around every page (item 2.07, the HRMS's frame): the crest's colours, Home, search for everything
 * (Ctrl K), To do, notifications and the person's own pages. No permanent menu: a breadcrumb leads back to
 * Home. Phones get four tabs at the bottom (Home, To do, Search, Me) and sheets in place of drop-downs.
 */
export function Shell({ me, path, onNavigate, onLogout, campusCode, onCampusChange, children }: Props) {
  const phone = usePhone();
  const [menu, setMenu] = useState<"bell" | "account" | null>(null);
  const [searching, setSearching] = useState(false);
  const [crumb, setCrumb] = useState<string | null>(null);
  const [waiting, refreshWaiting] = useWaitingCount(path);
  const [campuses, setCampuses] = useState<Campus[]>([]);
  const opener = useRef<HTMLElement | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const [shownPath, setShownPath] = useState(path);
  const switchable = usesCampusSwitch(me);

  // A new page starts with nothing left open over it.
  if (shownPath !== path) {
    setShownPath(path);
    setMenu(null);
    setSearching(false);
  }

  useEffect(() => {
    if (!switchable) return;
    get<Campus[]>("/reference/campuses/")
      .then(setCampuses)
      .catch(() => setCampuses([]));
  }, [switchable]);

  const frame: Frame = useMemo(() => ({ setCrumb, decided: refreshWaiting }), [refreshWaiting]);

  const openSearch = useCallback(() => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setMenu(null);
    setSearching(true);
  }, []);

  const closeSearch = useCallback(() => {
    setSearching(false);
    opener.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openSearch();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openSearch]);

  // ...and at its top.
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = 0;
  }, [path]);

  const go = (to: string) => {
    setSearching(false);
    setMenu(null);
    onNavigate(to);
  };
  const link = (to: string) => ({
    href: `#${to}`,
    onClick: (e: { preventDefault: () => void }) => {
      e.preventDefault();
      go(to);
    },
  });
  const closeMenu = useCallback(() => setMenu(null), []);

  async function signOut() {
    await post("/auth/logout/").catch(() => undefined);
    // No class list kept for the field stays on the phone (ADR 0011).
    await import("../features/practicals/fieldCopy").then((m) => m.clearFieldCopies()).catch(() => undefined);
    onLogout();
  }

  const campusSwitch =
    switchable && campuses.length > 1 ? <CampusSwitch campuses={campuses} value={campusCode} onChange={onCampusChange} /> : null;
  const count = waiting > 0 && (
    <span className="count">
      {waiting} <span className="sr-only">waiting</span>
    </span>
  );
  const what = me.persona === "student" ? "Search courses, work and pages" : "Search courses, work, people and pages";

  return (
    <FrameContext.Provider value={frame}>
      <div className={phone ? "frame phone" : "frame"}>
        <header className="masthead">
          <a className="home-link" aria-label="GSA LMS Home" {...link("/")}>
            <Crest size={phone ? 32 : 40} />
            <span className="brand">
              <span className="brand-name">GSA LMS</span>
              {!phone && <span className="brand-sub">Guyana School of Agriculture</span>}
            </span>
          </a>
          {!phone && (
            <button type="button" className="search-bar" aria-haspopup="dialog" aria-keyshortcuts="Control+K" onClick={openSearch}>
              <span>{what}</span>
              <kbd aria-hidden="true">Ctrl K</kbd>
            </button>
          )}
          <div className="masthead-tools">
            <PendingCount />
            {!phone && campusSwitch}
            {!phone && (
              <a className="todo-link" aria-current={path === "/to-do" ? "page" : undefined} {...link("/to-do")}>
                To do{" "}
                {count}
              </a>
            )}
            <MessagesLink path={path} onNavigate={go} />
            <NotificationsBell
              open={menu === "bell"}
              phone={phone}
              onToggle={() => setMenu(menu === "bell" ? null : "bell")}
              onClose={closeMenu}
              onNavigate={go}
            />
            <AccountMenu
              me={me}
              open={menu === "account"}
              phone={phone}
              onToggle={() => setMenu(menu === "account" ? null : "account")}
              onClose={closeMenu}
              onNavigate={go}
              onSignOut={signOut}
              campusSwitch={phone ? campusSwitch : null}
            />
          </div>
        </header>
        <div className="scroller" ref={scroller}>
          <main className="content">
            {phone && path === "/" && (
              <button type="button" className="search-field" aria-haspopup="dialog" onClick={openSearch}>
                {what}
              </button>
            )}
            {/* The way back, and help with this page (item 7.17), except on the help pages themselves. */}
            <div className="crumb-row">
              <Breadcrumbs path={path} item={crumb} onNavigate={go} />
              {!path.startsWith("/help") && (
                <a className="help-link" {...link(helpLink(path))}>
                  Help<span className="sr-only"> with this page</span>
                </a>
              )}
            </div>
            {children}
          </main>
        </div>
        {phone && (
          <nav className="tabbar" aria-label="Main">
            <a aria-current={path === "/" && !searching ? "page" : undefined} {...link("/")}>
              Home
            </a>
            <a aria-current={path === "/to-do" && !searching ? "page" : undefined} {...link("/to-do")}>
              To do{" "}
              {count}
            </a>
            <button type="button" aria-haspopup="dialog" aria-pressed={searching} onClick={openSearch}>
              Search
            </button>
            <button
              type="button"
              aria-expanded={menu === "account"}
              onClick={() => setMenu(menu === "account" ? null : "account")}
            >
              Me
            </button>
          </nav>
        )}
        {searching && <SearchPalette me={me} phone={phone} onGo={go} onClose={closeSearch} />}
      </div>
    </FrameContext.Provider>
  );
}
