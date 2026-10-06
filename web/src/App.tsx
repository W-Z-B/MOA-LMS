import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from "react";
import { SIGNED_OUT_EVENT, get } from "./api/client";
import { ADMIN_ROLES, hasAnyRole, type Me } from "./api/types";
import { usesCampusSwitch } from "./app/people";
import { Shell } from "./app/Shell";
import { adminAddress, contentAddress, forumAddress, messageAddress, siteAddress, useHashRoute } from "./app/router";
import { AccountScreen } from "./features/account/AccountScreen";
import { CalendarScreen } from "./features/calendar/CalendarScreen";
import { ForumScreen } from "./features/forums/ForumScreen";
import { ForumsScreen } from "./features/forums/ForumsScreen";
import { ThreadScreen } from "./features/forums/ThreadScreen";
import { MessagesScreen } from "./features/messages/MessagesScreen";
import { LoginScreen } from "./features/auth/LoginScreen";
import { MyCoursesScreen } from "./features/courses/MyCoursesScreen";
import { SiteScreen } from "./features/courses/SiteScreen";
import { HomeScreen } from "./features/home/HomeScreen";
import { ComingSoon } from "./features/placeholder/ComingSoon";
import { MyDataScreen } from "./features/privacy/MyDataScreen";
import { PrivacyNoticeScreen } from "./features/privacy/PrivacyNoticeScreen";
import { ToDoScreen } from "./features/todo/ToDoScreen";

const CAMPUS_KEY = "gsa-lms.campus";

// Teaching content and course administration (items 2.12 to 2.20), fetched when first opened: the page
// editor and KaTeX in particular stay out of what every page loads.
const PageScreen = lazy(() => import("./features/content/PageScreen"));
const PageEditorScreen = lazy(() => import("./features/content/PageEditorScreen"));
const CourseSetupScreen = lazy(() => import("./features/content/CourseSetupScreen"));
const AdminScreen = lazy(() => import("./features/course-admin/AdminScreen"));
const TemplatesScreen = lazy(() => import("./features/course-admin/TemplatesScreen"));
const TakedownsScreen = lazy(() => import("./features/course-admin/TakedownsScreen"));
const StorageAllowancesScreen = lazy(() => import("./features/course-admin/StorageAllowancesScreen"));

const later = (screen: ReactNode) => <Suspense fallback={<p className="loading">Opening…</p>}>{screen}</Suspense>;

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
  const content = contentAddress(path);
  const admin = adminAddress(path);
  const forum = forumAddress(path);
  const messages = messageAddress(path);
  const campus = usesCampusSwitch(me) ? campusCode : null;
  let screen;
  // Everyone opens on their own Home (item 2.07): what waits for them, and the pages their role uses.
  if (path === "/") screen = <HomeScreen me={me} onNavigate={navigate} />;
  else if (path === "/to-do") screen = <ToDoScreen onNavigate={navigate} />;
  else if (content?.view === "setup") screen = later(<CourseSetupScreen siteId={content.siteId} />);
  else if (content?.view === "page") screen = later(<PageScreen key={content.itemId} siteId={content.siteId} itemId={content.itemId} />);
  else if (content?.view === "edit")
    screen = later(
      <PageEditorScreen
        key={`editor-${content.siteId}`}
        siteId={content.siteId}
        itemId={content.itemId}
        moduleId={content.moduleId}
        onNavigate={navigate}
      />,
    );
  // --- talk: forums, messages and the calendar (items 4.08 to 4.11, 2.32) ---
  else if (forum?.thread) screen = <ThreadScreen key={forum.thread} forumId={forum.forum ?? 0} threadId={forum.thread} />;
  else if (forum?.forum) screen = <ForumScreen key={forum.forum} forumId={forum.forum} onNavigate={navigate} />;
  else if (forum) screen = <ForumsScreen />;
  else if (messages)
    screen = <MessagesScreen conversationId={messages.conversation} query={path.split("?")[1] ?? ""} onNavigate={navigate} />;
  else if (path === "/calendar") screen = <CalendarScreen onNavigate={navigate} />;
  // --- end talk ---
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
  else if (admin && !hasAnyRole(me, ADMIN_ROLES))
    screen = (
      <p role="alert" className="error">
        Admin is for course administrators and administrators.
      </p>
    );
  else if (admin === "home") screen = later(<AdminScreen onNavigate={navigate} />);
  else if (admin === "templates") screen = later(<TemplatesScreen />);
  else if (admin === "takedowns") screen = later(<TakedownsScreen />);
  else if (admin === "storage") screen = later(<StorageAllowancesScreen />);
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
