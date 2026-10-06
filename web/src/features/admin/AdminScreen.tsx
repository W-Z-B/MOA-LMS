import { lazy, Suspense, type ReactNode } from "react";
import { ADMIN_ROLES, hasAnyRole, type Me } from "../../api/types";
import { AUDIT_READERS, CORRECTION_READERS, OVERSEERS, PRIVACY_READERS } from "../../api/types-staff";
import { useCrumb } from "../../app/frame";
import { CourseAdminLinks } from "../course-admin/CourseAdminLinks";
import { AccessReview } from "./AccessReview";
import { Accounts } from "./Accounts";
import { AuditLog } from "./AuditLog";
import { IntegrationRuns } from "./IntegrationRuns";
import { Corrections, Notices } from "./Privacy";
import { Breaches, Retention } from "./Retention";
import { COURSE_REPORT_READERS, RULE_KEEPERS, STAFF_REPORT_READERS } from "../../api/types-insights";

// --- insight --- (items 6.03 to 6.06): reports and the early-alert rules, loaded when opened.
const ReportsSection = lazy(() => import("../insights/ReportsSection"));
const AlertRulesSection = lazy(() => import("../insights/AlertRulesSection"));
const later = (screen: ReactNode) => <Suspense fallback={<p className="loading">Opening…</p>}>{screen}</Suspense>;
const REPORT_READERS = [...new Set([...COURSE_REPORT_READERS, ...STAFF_REPORT_READERS])];
// --- end insight ---

interface Props {
  me: Me;
  path: string;
  onNavigate: (to: string) => void;
}

interface Part {
  key: string;
  label: string;
  desc: string;
  roles: readonly string[];
  render: (me: Me) => ReactNode;
}

/**
 * The console's sections, each only for the roles the server lets read it (items 1.17 to 1.23): nobody else
 * sees a link to it, or anything at its address.
 */
const SECTIONS: readonly Part[] = [
  { key: "accounts", label: "People to invite", desc: "Open accounts by campus or term and send the invitations", roles: ["administrator"], render: () => <Accounts /> },
  { key: "integration", label: "Integration runs", desc: "What each exchange with the HRMS and the SRMS did, and what failed", roles: OVERSEERS, render: () => <IntegrationRuns /> },
  { key: "audit", label: "Audit log", desc: "Every change, with filters, a spreadsheet export and the chain check", roles: AUDIT_READERS, render: () => <AuditLog /> },
  { key: "access-review", label: "Access review", desc: "Who holds a role and who teaches which site, signed off each term", roles: OVERSEERS, render: (me) => <AccessReview me={me} /> },
  { key: "notices", label: "Privacy notice", desc: "Versions of the notice: drafts and publishing", roles: PRIVACY_READERS, render: (me) => <Notices me={me} /> },
  { key: "corrections", label: "Correction requests", desc: "Requests to correct a record, answered within the time limit", roles: CORRECTION_READERS, render: (me) => <Corrections me={me} /> },
  { key: "retention", label: "Retention and disposal", desc: "How long records are kept; disposal approved by a second person", roles: PRIVACY_READERS, render: (me) => <Retention me={me} /> },
  { key: "breaches", label: "Breach register", desc: "Personal data breaches and what was done about them", roles: PRIVACY_READERS, render: (me) => <Breaches me={me} /> },
  // --- insight ---
  { key: "reports", label: "Reports", desc: "Courses by campus and programme, and staff development by unit, with spreadsheet exports", roles: REPORT_READERS, render: (me) => later(<ReportsSection me={me} />) },
  { key: "alert-rules", label: "Early-alert rules", desc: "The thresholds of the rules that pick out students who may need help", roles: RULE_KEEPERS, render: () => later(<AlertRulesSection />) },
  // --- end insight ---
];

/** Admin (features 35 to 38's console): an overview of the sections the person may open, and each section. */
export function AdminScreen({ me, path, onNavigate }: Props) {
  const mine = SECTIONS.filter((part) => hasAnyRole(me, part.roles));
  const key = path.split("?")[0].replace(/^\/admin\/?/, "");
  const open = mine.find((part) => part.key === key);
  useCrumb(open?.label);

  if (key && !open)
    return (
      <>
        <h1>Admin</h1>
        <p className="muted">There is nothing here for you.</p>
      </>
    );
  if (open)
    return (
      <>
        <div className="page-head">
          <div className="stacked">
            <h1>{open.label}</h1>
            <p className="muted lead">{open.desc}.</p>
          </div>
        </div>
        {open.render(me)}
      </>
    );
  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>Admin</h1>
          <p className="muted lead">Running the LMS: accounts, the audit log, links with the HRMS and the SRMS, privacy, and course administration.</p>
        </div>
      </div>
      {mine.length > 0 && (
        <nav className="shortcuts" aria-label="Admin sections">
          {mine.map((part) => (
            <a
              key={part.key}
              href={`#/admin/${part.key}`}
              onClick={(e) => {
                e.preventDefault();
                onNavigate(`/admin/${part.key}`);
              }}
            >
              <span className="shortcut-title">{part.label}</span>
              <span className="shortcut-sub">{part.desc}</span>
            </a>
          ))}
        </nav>
      )}
      {/* --- course administration links --- */}
      {hasAnyRole(me, ADMIN_ROLES) && <CourseAdminLinks onNavigate={onNavigate} />}
    </>
  );
}
