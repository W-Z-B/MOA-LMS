# Component specification

What is built today, by app. Feature numbers are those of the GSA LMS Gold Standard Feature Audit; item
numbers those of the Implementation Checklist. The interface is described in full at `/api/docs`.

| Component | App or package | Features | Key entities | Interfaces | Notes |
|---|---|---|---|---|---|
| Course sites and class lists | `api/courses`, `api/integration` | 1 | CourseSite, Membership | `/api/v1/sites/`, `/sites/{id}/contents/`, `/sites/{id}/members/` | One site per SRMS offering, or created locally by a course administrator (academic or staff development); site roles student, lecturer, teaching assistant; dropped students deactivated, never deleted |
| Content | `api/courses` | 3 | Module, ContentItem | `/api/v1/modules/`, `/content/`, `/content/{id}/download/` | Pages, files and links; published or draft; students see published only; downloads authenticated and audited |
| Announcements | `api/courses`, `api/notifications` | 21 | Announcement, Notification | `/api/v1/announcements/`, `/notifications/` | Each announcement notifies the site's students |
| Assignments and submissions | `api/assessments` | 9 | Assignment, Submission | `/api/v1/assignments/`, `/assignments/{id}/submit/`, `/submissions/{id}/download/` | Weights, opening and due dates, late flag, closed when late work is not allowed; text or one file; a marked submission cannot be replaced |
| Marking and gradebook | `api/assessments` | 17, 18 | Mark | `/api/v1/submissions/{id}/mark/`, `/sites/{id}/gradebook/` | Feedback and release control; students see their own released marks only; weighted coursework percentage (rule below) |
| Ecosystem integration | `api/integration` | 1, 18, 38 | ServiceClient, CampusRef | `/api/v1/integration/sites/` (Api-Key), `/reference/campuses/`; commands `sync_ecosystem`, `create_service_client` | Pulls sites and class lists from the SRMS nightly; pushes coursework to the SRMS and completions to the HRMS |
| Completions | `api/courses` | 20, 38 | Completion | via `sync_ecosystem --push-training` | Recorded today only by the demonstration data; automatic completion is item 5.03 |
| Sign-in and roles | `api/iam` | 41 | Role, RoleScope, TotpDevice, LoginAttempt | `/api/v1/auth/*` | Session sign-in; authenticator code for administrators and course administrators; lockout |
| Audit | `api/audit` | 41 | AuditLog | (none; read in the Django admin) | Insert-only, protected by a database trigger |
| Home, To do and search | `api/core` | 29 | (reads the above) | `/api/v1/home/`, `/to-do/`, `/search/?q=` | A Home for each role (items 2.07 to 2.09): a student's work due, overdue, new feedback and progress; teaching staff's work to mark, sites with nothing new for the coming week and students not seen in 14 days; site figures for course administrators and administrators. To do gathers what waits for the person, oldest first, marked overdue. Search finds only what the person may open, and people for staff only |
| Web app | `web/` | 27, 29 | (uses the above) | consumes `/api/v1` | The HRMS's frame in the crest's colours with the LMS's amber accent (ADR 0010): Home by role, To do, search (Ctrl K), breadcrumbs, shareable addresses (a dependency-free hash router, as the HRMS's), four tabs and sheets on a phone; My courses, the course site, notifications; assignments, the marking screen (after Canvas SpeedGrader), rubrics, the gradebook with the working of each total, accommodations and notification settings (`web/src/features/assignments`, `marking`, `rubrics`, `gradebook`, `accommodations`, `notifications`); an offline queue for writes that are safe to send again (item 4.02); installable; every journey checked at 360px |

## Coursework rule

A marked assignment counts with its mark (capped at the maximum). An overdue assignment with no submission
counts as zero. A submitted but unmarked assignment is pending and does not count. The total is weighted by
each assignment's weight and sent to the SRMS as a percentage with two decimal places. Students see the total
from released marks only. While an assignment is marked anonymously and its marks are not released, teaching
staff's totals (the working, the gradebook, the export and the push to the SRMS) count it as pending ("pending
(anonymous marking)"), so a total never reveals an anonymous mark. The rule is
`assessments.services.coursework_percent`.

## Cross-cutting rules

- Every table carries `created_at`, `updated_at`, `created_by`, `updated_by`.
- Every change to content, assignments, submissions and marks, and every download, writes an audit row in
  the same transaction.
- Access to anything inside a site is decided by membership of that site (`courses/access.py`); system roles
  (administrator, course administrator, auditor) see across sites.
- Every endpoint is described in the OpenAPI schema; CI fails if one is not.
- Refusals the API writes itself have the shape `{code, detail}`; the framework's own refusals follow once
  item 1.14 ports the HRMS's error handler.
- Time zone `America/Guyana`; dates shown `dd/mm/yyyy`.
- No component may be added unless its licence meets [ADR 0002](adr/0002-licence-policy.md).

## Not built yet

Quizzes ([ADR 0005](adr/0005-quizzes-built-in.md)), rubrics, practical and competency assessment, forums and
messages, calendar, attendance ([ADR 0008](adr/0008-attendance-in-the-lms.md)), certificates,
packaged content, analytics and the rest of the checklist's phases 2 to 7.
