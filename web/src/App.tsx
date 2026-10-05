import { useCallback, useEffect, useState } from "react";
import { SIGNED_OUT_EVENT, get } from "./api/client";
import type { Me } from "./api/types";
import { usesCampusSwitch } from "./app/people";
import { Shell } from "./app/Shell";
import { siteAddress, useHashRoute } from "./app/router";
import { AccountScreen } from "./features/account/AccountScreen";
import { AdminScreen } from "./features/admin/AdminScreen";
import { ConfirmEmailScreen } from "./features/auth/ConfirmEmailScreen";
import { ForgotPasswordScreen } from "./features/auth/ForgotPasswordScreen";
import { LoginScreen } from "./features/auth/LoginScreen";
import { SetPasswordScreen } from "./features/auth/SetPasswordScreen";
import { MyCoursesScreen } from "./features/courses/MyCoursesScreen";
import { SiteScreen } from "./features/courses/SiteScreen";
import { HomeScreen } from "./features/home/HomeScreen";
import { learningAddress } from "./features/learning/address";
import { LearningScreen } from "./features/learning/LearningScreen";
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
  const [knownUsername, setKnownUsername] = useState("");
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

  // --- accounts (items 1.10, 1.22): emailed links open their page whether or not someone is signed in ---
  const link = path.match(/^\/set-password\/([^/]+)\/([^/]+)$/);
  if (link)
    return (
      <SetPasswordScreen
        uid={link[1]}
        token={link[2]}
        onDone={(username) => {
          setKnownUsername(username);
          setSignedOutReason("Your password is saved. Sign in with it now.");
          setMe(null);
          navigate("/");
        }}
        onAskAgain={() => navigate("/forgot-password")}
      />
    );
  const confirmEmail = path.match(/^\/confirm-email\/([^/]+)$/);
  if (confirmEmail) return <ConfirmEmailScreen token={confirmEmail[1]} onDone={() => navigate("/")} />;
  // --- end of accounts ---
  if (me === undefined) return <p className="loading">Loading GSA LMS…</p>;
  if (me === null || (me.mfa_required && !me.mfa_verified)) {
    if (path === "/forgot-password") return <ForgotPasswordScreen onBack={() => navigate("/")} />;
    return (
      <LoginScreen
        key={knownUsername}
        knownUsername={knownUsername}
        onForgot={() => navigate("/forgot-password")}
        notice={signedOutReason}
        onSignedIn={(signedIn) => {
          setSignedOutReason(null);
          setMe(signedIn);
        }}
      />
    );
  }
  if (me.privacy_notice_due) return <PrivacyNoticeScreen onAcknowledged={noticeRead} />;

  // Every page has an address of its own (item 2.10), down to a course site's tab: #/sites/4/gradebook.
  const site = siteAddress(path);
  const campus = usesCampusSwitch(me) ? campusCode : null;
  let screen;
  // Everyone opens on their own Home (item 2.07): what waits for them, and the pages their role uses.
  if (path === "/") screen = <HomeScreen me={me} onNavigate={navigate} />;
  else if (path === "/to-do") screen = <ToDoScreen onNavigate={navigate} />;
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
  // --- staff development and the console (items 1.17 to 1.23, 5.02 to 5.11) ---
  else if (learningAddress(path)) screen = <LearningScreen me={me} path={path} onNavigate={navigate} />;
  else if (path === "/admin" || path.startsWith("/admin/")) screen = <AdminScreen me={me} path={path} onNavigate={navigate} />;
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
