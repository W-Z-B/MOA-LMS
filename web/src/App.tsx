import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from "react";
import { setQueueOwner } from "./app/offlineQueue";
import { SIGNED_OUT_EVENT, get } from "./api/client";
import { ADMIN_ROLES, hasAnyRole, type Me } from "./api/types";
import { usesCampusSwitch } from "./app/people";
import { Shell } from "./app/Shell";
import { adminAddress, assessAddress, contentAddress, forumAddress, messageAddress, siteAddress, useHashRoute } from "./app/router";
import { AccountScreen } from "./features/account/AccountScreen";
import { CalendarScreen } from "./features/calendar/CalendarScreen";
import { ForumScreen } from "./features/forums/ForumScreen";
import { ForumsScreen } from "./features/forums/ForumsScreen";
import { ThreadScreen } from "./features/forums/ThreadScreen";
import { MessagesScreen } from "./features/messages/MessagesScreen";
import { AdminScreen } from "./features/admin/AdminScreen";
import { ConfirmEmailScreen } from "./features/auth/ConfirmEmailScreen";
import { ForgotPasswordScreen } from "./features/auth/ForgotPasswordScreen";
import { LoginScreen } from "./features/auth/LoginScreen";
import { SetPasswordScreen } from "./features/auth/SetPasswordScreen";
import { MyCoursesScreen } from "./features/courses/MyCoursesScreen";
import { SiteScreen } from "./features/courses/SiteScreen";
import { HomeScreen } from "./features/home/HomeScreen";
import { markingScreen } from "./features/marking/routes";
import { learningAddress } from "./features/learning/address";
import { LearningScreen } from "./features/learning/LearningScreen";
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
const TemplatesScreen = lazy(() => import("./features/course-admin/TemplatesScreen"));
const TakedownsScreen = lazy(() => import("./features/course-admin/TakedownsScreen"));
const StorageAllowancesScreen = lazy(() => import("./features/course-admin/StorageAllowancesScreen"));
// --- assessment extras: peer review, open short courses and the guidance (items 4.13, 5.07, 6.13), on first use ---
const PeerReviewScreen = lazy(() => import("./features/assess/PeerReviewScreen"));
const ReviewWorkScreen = lazy(() => import("./features/assess/ReviewWorkScreen"));
const AssessmentAndAi = lazy(() => import("./features/assess/AssessmentAndAi"));
const OpenCoursesPage = lazy(() => import("./features/assess/OpenCourses"));
const PublicOpenCourses = lazy(() => import("./features/assess/OpenCourses").then((m) => ({ default: m.PublicOpenCourses })));
const OpenConfirmScreen = lazy(() => import("./features/assess/OpenCourses").then((m) => ({ default: m.OpenConfirmScreen })));
// --- end assessment extras ---

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
  const [knownUsername, setKnownUsername] = useState("");
  // Item 1.18: the privacy notice in force is read before anything else, once per version.
  // Writes kept on the device are sent only for the person signed in now (shared phones).
  const signedIn = me && !(me.mfa_required && !me.mfa_verified) ? me.id : null;
  useEffect(() => setQueueOwner(signedIn), [signedIn]);
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
  // --- assessment extras: the emailed link to finish registering for open short courses (item 5.07) ---
  const assess = assessAddress(path);
  if (assess?.view === "open-confirm")
    return later(
      <OpenConfirmScreen
        token={assess.token}
        onDone={(username) => {
          setKnownUsername(username);
          setSignedOutReason("Your account is ready. Sign in with your email address and the password you chose.");
          setMe(null);
          navigate("/");
        }}
      />,
    );
  // --- end assessment extras ---
  if (me === undefined) return <p className="loading">Loading GSA LMS…</p>;
  if (me === null || (me.mfa_required && !me.mfa_verified)) {
    if (path === "/forgot-password") return <ForgotPasswordScreen onBack={() => navigate("/")} />;
    if (assess?.view === "open-courses") return later(<PublicOpenCourses />); // the public short-course page (item 5.07)
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
  const content = contentAddress(path);
  const admin = adminAddress(path);
  const forum = forumAddress(path);
  const messages = messageAddress(path);
  const campus = usesCampusSwitch(me) ? campusCode : null;
  // Marking, rubrics, accommodations and notification settings have addresses of their own.
  const marking = markingScreen(path, navigate);
  let screen;
  // Everyone opens on their own Home (item 2.07): what waits for them, and the pages their role uses.
  if (path === "/") screen = <HomeScreen me={me} onNavigate={navigate} />;
  else if (path === "/to-do") screen = <ToDoScreen onNavigate={navigate} />;
  else if (marking) screen = marking;
  // --- assessment extras ---
  else if (assess?.view === "peer-review")
    screen = later(<PeerReviewScreen key={assess.assignmentId} siteId={assess.siteId} assignmentId={assess.assignmentId} />);
  else if (assess?.view === "peer-work") screen = later(<ReviewWorkScreen key={assess.reviewId} siteId={assess.siteId} reviewId={assess.reviewId} />);
  else if (assess?.view === "open-courses") screen = later(<OpenCoursesPage />);
  else if (assess?.view === "help-ai") screen = later(<AssessmentAndAi />);
  // --- end assessment extras ---
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
  // Course administration parts of Admin (items 2.17, 2.19, 2.20); the console below owns #/admin itself.
  else if (admin && admin !== "home" && !hasAnyRole(me, ADMIN_ROLES))
    screen = (
      <p role="alert" className="error">
        This part of Admin is for course administrators and administrators.
      </p>
    );
  else if (admin === "templates") screen = later(<TemplatesScreen />);
  else if (admin === "takedowns") screen = later(<TakedownsScreen />);
  else if (admin === "storage") screen = later(<StorageAllowancesScreen />);
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
