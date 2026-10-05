import { useCallback, useEffect, useState } from "react";
import { SIGNED_OUT_EVENT, get } from "./api/client";
import type { Me } from "./api/types";
import { usesCampusSwitch } from "./app/people";
import { Shell } from "./app/Shell";
import { siteAddress, useHashRoute } from "./app/router";
import { AccountScreen } from "./features/account/AccountScreen";
import { LoginScreen } from "./features/auth/LoginScreen";
import { MyCoursesScreen } from "./features/courses/MyCoursesScreen";
import { SiteScreen } from "./features/courses/SiteScreen";
import { HomeScreen } from "./features/home/HomeScreen";
import { markingScreen } from "./features/marking/routes";
import { ComingSoon } from "./features/placeholder/ComingSoon";
import { MyDataScreen } from "./features/privacy/MyDataScreen";
import { PrivacyNoticeScreen } from "./features/privacy/PrivacyNoticeScreen";
import { ToDoScreen } from "./features/todo/ToDoScreen";

const CAMPUS_KEY = "gsa-lms.campus";

function readCampus(): string | null {
  try {
    return localStorage.getItem(CAMPUS_KEY);
  } catch {
    return null;
  }
}

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [path, navigate] = useHashRoute();
  const [campusCode, setCampusCode] = useState<string | null>(readCampus);
  const [signedOutReason, setSignedOutReason] = useState<string | null>(null);
  // Item 1.18: the privacy notice in force is read before anything else, once per version.
  const noticeRead = useCallback(() => setMe((m) => (m ? { ...m, privacy_notice_due: null } : m)), []);

  useEffect(() => {
    get<Me>("/auth/me/")
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  useEffect(() => {
    const signedOut = (event: Event) => {
      setSignedOutReason((event as CustomEvent<string>).detail);
      setMe(null);
    };
    window.addEventListener(SIGNED_OUT_EVENT, signedOut);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, signedOut);
  }, []);

  function changeCampus(code: string | null) {
    setCampusCode(code);
    try {
      if (code) localStorage.setItem(CAMPUS_KEY, code);
      else localStorage.removeItem(CAMPUS_KEY);
    } catch {
      /* per-viewer convenience only */
    }
  }

  if (me === undefined) return <p className="loading">Loading GSA LMS…</p>;
  if (me === null || (me.mfa_required && !me.mfa_verified))
    return (
      <LoginScreen
        notice={signedOutReason}
        onSignedIn={(signedIn) => {
          setSignedOutReason(null);
          setMe(signedIn);
        }}
      />
    );
  if (me.privacy_notice_due) return <PrivacyNoticeScreen onAcknowledged={noticeRead} />;

  // Every page has an address of its own (item 2.10), down to a course site's tab: #/sites/4/gradebook.
  const site = siteAddress(path);
  const campus = usesCampusSwitch(me) ? campusCode : null;
  // Marking, rubrics, accommodations and notification settings have addresses of their own.
  const marking = markingScreen(path, navigate);
  let screen;
  // Everyone opens on their own Home (item 2.07): what waits for them, and the pages their role uses.
  if (path === "/") screen = <HomeScreen me={me} onNavigate={navigate} />;
  else if (path === "/to-do") screen = <ToDoScreen onNavigate={navigate} />;
  else if (marking) screen = marking;
  else if (site)
    screen = (
      <SiteScreen
        key={site.id}
        siteId={site.id}
        tab={site.tab}
        onTab={(tab) => navigate(tab === "content" ? `/sites/${site.id}` : `/sites/${site.id}/${tab}`)}
      />
    );
  else if (path === "/courses" || path === "/sites") screen = <MyCoursesScreen campusCode={campus} onNavigate={navigate} />;
  else if (path === "/account") screen = <AccountScreen />;
  else if (path.startsWith("/my-data")) screen = <MyDataScreen />;
  else if (path.startsWith("/admin"))
    screen = <ComingSoon title="Admin" sprint="a later sprint" requirement="site creation and ecosystem sync controls" />;
  else screen = <ComingSoon title="Not found" sprint="a later sprint" requirement="unknown route" />;

  return (
    <Shell
      me={me}
      path={path}
      onNavigate={navigate}
      onLogout={() => setMe(null)}
      campusCode={campusCode}
      onCampusChange={changeCampus}
    >
      {screen}
    </Shell>
  );
}
