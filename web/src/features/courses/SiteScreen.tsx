import { Suspense, lazy, useCallback, useEffect, useState, type FormEvent } from "react";
import { errorMessage, get, patch, post } from "../../api/client";
import { canTeach, type SiteContents } from "../../api/types";
import { useCrumb } from "../../app/frame";
import { SITE_TABS, type SiteTab } from "../../app/router";
import { ClassesTab } from "../attendance/ClassesTab";
import { DiscussionTab } from "../forums/DiscussionTab";
import { GroupsTab } from "../groups/GroupsTab";
import { ContentTab } from "../content/ContentTab";
import { AssignmentsTab, GradebookTab } from "../marking/lazy";
import { showsAiTab, useAiStatus } from "../ai/status";

// Practicals and the logbook load only when their tab is opened (items 3.12 to 3.15).
const PracticalsTab = lazy(() => import("../practicals/PracticalsTab").then((m) => ({ default: m.PracticalsTab })));
const LogbookTab = lazy(() => import("../practicals/LogbookTab").then((m) => ({ default: m.LogbookTab })));

// The quiz screens load when the Quizzes tab is first opened, so they add nothing to the shell (page weight).
const QuizzesTab = lazy(() => import("../quizzes/QuizzesTab").then((m) => ({ default: m.QuizzesTab })));

// --- insight --- (items 6.01, 6.02, 3.11, 6.05): Insights for teaching staff, My progress for students, loaded when opened.
const InsightsTab = lazy(() => import("../insights/InsightsTab").then((m) => ({ default: m.InsightsTab })));
const MyProgress = lazy(() => import("../insights/MyProgress").then((m) => ({ default: m.MyProgress })));
const tabFor = (tab: SiteTab, teaching: boolean, student: boolean) => (tab === "insights" ? teaching : tab === "progress" ? student : true);
// --- end insight ---
// --- tools and AI help --- (items 6.07, 6.11, 6.12): each loads when its tab is first opened.
const ToolsTab = lazy(() => import("../tools/ToolsTab").then((m) => ({ default: m.ToolsTab })));
const AiTab = lazy(() => import("../ai/AiTab").then((m) => ({ default: m.AiTab })));
// --- end tools and AI help ---

interface Props {
  siteId: number;
  /** The tab named in the address (item 2.10), so each can be shared: #/sites/4/assignments. */
  tab: SiteTab;
  onTab: (tab: SiteTab) => void;
}

const TAB_LABEL: Record<SiteTab, string> = {
  content: "Content",
  assignments: "Assignments",
  quizzes: "Quizzes",
  gradebook: "Gradebook",
  announcements: "Announcements",
  discussion: "Discussion",
  classes: "Classes",
  groups: "Groups",
  practicals: "Practicals",
  logbook: "Logbook",
  insights: "Insights",
  progress: "My progress",
  tools: "Tools",
  ai: "AI help",
};

/**
 * One course site: content, assignments, gradebook and announcements. Teaching staff get the authoring forms.
 * Its name is the last breadcrumb (Home / My courses / the site), and each tab has an address of its own.
 */
export function SiteScreen({ siteId, tab, onTab }: Props) {
  const [data, setData] = useState<SiteContents | null>(null);
  const [error, setError] = useState<string | null>(null);
  useCrumb(data?.site.title);
  const [ai, setAi] = useAiStatus(siteId); // the AI help tab shows only where it may be used

  const load = useCallback(() => {
    get<SiteContents>(`/sites/${siteId}/contents/`)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err, "Could not open this course.")));
  }, [siteId]);

  useEffect(load, [load]);

  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!data) return <p className="loading">Opening course…</p>;
  const teaching = canTeach(data.site.my_role);

  async function togglePublished() {
    if (!data) return;
    try {
      await patch(`/sites/${siteId}/`, { is_published: !data.site.is_published });
      load();
    } catch (err) {
      setError(errorMessage(err, "Could not change the site."));
    }
  }

  return (
    <>
      <div className="page-head site-head">
        <div className="stacked">
          <h1>{data.site.title}</h1>
          <p className="muted">
            {data.site.code} · {data.site.members} members · coursework {data.site.coursework_weight}% of the final mark
          </p>
        </div>
        {teaching && (
          <button className="secondary" onClick={togglePublished}>
            {data.site.is_published ? "Unpublish" : "Publish to students"}
          </button>
        )}
      </div>
      {/* --- terms: a closed site says so (item 7.12) --- */}
      {data.site.closed_notice && <p className="notice">{data.site.closed_notice}</p>}
      {/* --- end terms --- */}
      <div className="tabs" role="tablist">
        {SITE_TABS.filter((t) => tabFor(t, teaching, data.site.my_role === "student") && (t !== "ai" || showsAiTab(ai))).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab active" : "tab"} onClick={() => onTab(t)}>
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>
      {tab === "content" && <ContentTab data={data} teaching={teaching} onChanged={load} />}
      <Suspense fallback={<p className="loading">Opening…</p>}>
        {tab === "assignments" && <AssignmentsTab siteId={siteId} teaching={teaching} />}
        {tab === "quizzes" && <QuizzesTab siteId={siteId} teaching={teaching} />}
        {tab === "gradebook" && <GradebookTab site={data.site} teaching={teaching} />}
      </Suspense>
      {tab === "announcements" && <AnnouncementsTab data={data} teaching={teaching} onChanged={load} />}
      {tab === "discussion" && <DiscussionTab siteId={siteId} teaching={teaching} />}
      {tab === "classes" && <ClassesTab siteId={siteId} teaching={teaching} />}
      {tab === "groups" && <GroupsTab siteId={siteId} teaching={teaching} />}
      <Suspense fallback={<p className="loading">Loading…</p>}>
        {tab === "practicals" && <PracticalsTab siteId={siteId} teaching={teaching} />}
        {tab === "logbook" && <LogbookTab siteId={siteId} teaching={teaching} />}
        {tab === "insights" && teaching && <InsightsTab siteId={siteId} />}
        {tab === "progress" && data.site.my_role === "student" && <MyProgress siteId={siteId} />}
        {tab === "tools" && <ToolsTab siteId={siteId} teaching={teaching} modules={data.modules} />}
        {tab === "ai" && ai && showsAiTab(ai) && <AiTab siteId={siteId} status={ai} modules={data.modules} onStatus={setAi} />}
      </Suspense>
    </>
  );
}

function AnnouncementsTab({ data, teaching, onChanged }: { data: SiteContents; teaching: boolean; onChanged: () => void }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function publish(e: FormEvent) {
    e.preventDefault();
    try {
      await post("/announcements/", { site: data.site.id, title, body });
      setTitle("");
      setBody("");
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Could not post the announcement."));
    }
  }

  return (
    <>
      {teaching && (
        <form className="stack sub-form" onSubmit={publish} style={{ borderTop: 0, marginTop: 0, paddingTop: 0 }}>
          <label>
            Title
            <input id="ann-title" value={title} onChange={(e) => setTitle(e.target.value)} required />
          </label>
          <label>
            Message
            <textarea id="ann-body" value={body} onChange={(e) => setBody(e.target.value)} required />
          </label>
          {error && <p className="error">{error}</p>}
          <div className="actions">
            <button type="submit">Post and notify students</button>
          </div>
        </form>
      )}
      {data.announcements.length === 0 && <p className="muted">No announcements.</p>}
      {data.announcements.map((a) => (
        <section className="module" key={a.id}>
          <h3>{a.title}</h3>
          <p className="muted small">
            {a.author_name ?? "Course team"} · {new Date(a.created_at).toLocaleString("en-GB")}
          </p>
          <p style={{ whiteSpace: "pre-wrap" }}>{a.body}</p>
        </section>
      ))}
    </>
  );
}
