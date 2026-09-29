import { useEffect, useState } from "react";
import { get } from "./api/client";
import type { Me } from "./api/types";
import { Shell } from "./app/Shell";
import { useHashRoute } from "./app/router";
import { LoginScreen } from "./features/auth/LoginScreen";
import { MyCoursesScreen } from "./features/courses/MyCoursesScreen";
import { SiteScreen } from "./features/courses/SiteScreen";
import { ComingSoon } from "./features/placeholder/ComingSoon";

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

  useEffect(() => {
    get<Me>("/auth/me/")
      .then(setMe)
      .catch(() => setMe(null));
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
  if (me === null || (me.mfa_required && !me.mfa_verified)) return <LoginScreen onSignedIn={setMe} />;

  const site = path.match(/^\/sites\/(\d+)/);
  let screen;
  if (site) screen = <SiteScreen key={site[1]} siteId={Number(site[1])} onNavigate={navigate} />;
  else if (path === "/" || path.startsWith("/sites")) screen = <MyCoursesScreen campusCode={campusCode} onNavigate={navigate} />;
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
