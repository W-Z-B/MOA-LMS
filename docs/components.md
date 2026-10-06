# Component specification

What is built today, by app. Feature numbers are those of the GSA LMS Gold Standard Feature Audit; item
numbers those of the Implementation Checklist. The interface is described in full at `/api/docs`.

| Component | App or package | Features | Key entities | Interfaces | Notes |
|---|---|---|---|---|---|
| Course sites and class lists | `api/courses`, `api/integration` | 1 | CourseSite, Membership | `/api/v1/sites/`, `/sites/{id}/contents/`, `/sites/{id}/members/` | One site per SRMS offering, or created locally by a course administrator (academic or staff development); site roles student, lecturer, teaching assistant; dropped students deactivated, never deleted |
| Content | `api/courses` | 3 | Module, ContentItem | `/api/v1/modules/`, `/content/`, `/content/{id}/download/` | Pages, files and links; published or draft; students see published only; downloads authenticated and audited |
| Content screens | `web/src/features/content`, `web/src/features/course-admin` | 2, 3, 4, 7, 8 | (uses Content) | `#/sites/{id}` (Content tab), `#/sites/{id}/pages/{item}` and `/edit`, `#/sites/{id}/setup`, `#/admin` | Items 2.12 to 2.20: modules and items arranged by dragging or with Move up and Move down, copied, moved between modules; release conditions with the server's sentence for them; students mark items complete and see their progress per module. The page editor (TipTap) with headings, lists, tables, links, the course's pictures with required alternative text, maths stored as TeX and drawn with KaTeX, and code; the accessibility check runs as the lecturer writes. PDFs shown in the page with PDF.js when asked, photographs inline. Course setup: a template for an empty course, copying an earlier course with its dates moved, the date manager, storage use. Admin: course templates, takedown requests, storage allowances. The editor, KaTeX and PDF.js load only where used ([ADR 0012](adr/0012-new-components.md)) |
| Lecture video and captions | `api/video`, `web/src/features/media` | 6 | Video, Rendition, CaptionTrack | `/api/v1/videos/` (put up once), `/videos/{item}/`, `/play/{low,standard,audio}/` (Range), `/poster/`, `/captions/`, `/captions/{lang}/` (WebVTT), `/captions/{lang}/cues/`, `/transcribe/`, `/convert/`; `#/sites/{id}/videos/{item}/captions` | Items 4.06 and 4.07 ([ADR 0015](adr/0015-video-and-captions.md)): a content item of kind video, put up once and prepared by the job worker with FFmpeg (an LGPL build in the API image, run as a separate program) into a low (240p), a standard (480p by default) and a sound-only copy (64 kbit/s) and a poster frame; the student chooses the quality, each with its size; every copy counts against the site's storage allowance. Captions put up as WebVTT or written and corrected cue by cue; speech recognition with whisper.cpp on GSA's own server when `VIDEO_TRANSCRIBE_COMMAND` is set (off by default) |
| Offline reading and data-light mode | `api/video/offline.py`, `web/src/features/media`, `web/public/sw.js` | 6, 27, 28 | (uses Content) | `/api/v1/offline/modules/{id}/`; `#/downloads` (Downloaded, under Me) | Items 4.03 and 4.05 ([ADR 0011](adr/0011-phone-delivery.md)): a module kept to read offline, with the space shown first, in a cache that belongs to the signed-in person and is removed at sign-out or when someone else signs in; data-light mode per device (pictures and video only when asked for, sizes shown), from the connection hints until the person chooses |
| Push notices | `api/notifications`, `web/src/features/media` | 21, 27 | PushSubscription | `/api/v1/notifications/push/`, `/push/subscribe/`, `/push/unsubscribe/`; command `vapid_keys` | Item 4.04: Web Push with VAPID (pywebpush, a named exception under ADR 0002), off until the keys are set; per device and per kind (released marks, course announcements, reminders before a due date); sent by the job worker with only the title and the page it opens; only known push services accepted; gone or failing subscriptions removed; turned off for the device at sign-out |
| Announcements | `api/courses`, `api/notifications` | 21 | Announcement, Notification | `/api/v1/announcements/`, `/notifications/` | Each announcement notifies the site's students, as a kind of notification of its own (by email or push as each chooses) |
| Assignments and submissions | `api/assessments` | 9 | Assignment, Submission | `/api/v1/assignments/`, `/assignments/{id}/submit/`, `/submissions/{id}/download/` | Weights, opening and due dates, late flag, closed when late work is not allowed; text or one file; a marked submission cannot be replaced |
| Marking and gradebook | `api/assessments` | 17, 18 | Mark | `/api/v1/submissions/{id}/mark/`, `/sites/{id}/gradebook/` | Feedback and release control; students see their own released marks only; weighted coursework percentage (rule below) |
| Quizzes | `api/quizzes`, `web/src/features/quizzes` | 10 | QuestionBank, QuestionCategory, Question, QuestionVersion, Quiz, QuizSlot, QuizOverride, Attempt, AttemptAnswer | `/api/v1/question-banks/`, `/questions/` (with `import/`, `export/`), `/quizzes/`, `/quiz-slots/`, `/quiz-overrides/`, `/quiz-attempts/`; the site tab `#/sites/{id}/quizzes` | Built in, as [ADR 0005](adr/0005-quizzes-built-in.md) decides: course and department banks with categories, tags and versions; ten question types; Moodle XML, GIFT and QTI import with a report of what was skipped; fixed or random questions; time limits from the server, per-student extra time; answers saved as given through the offline queue; essays and files marked by a person; release by review options; statistics. Question text is cleaned on the server for display (courses.richtext). The screens load when the tab is first opened |
| Ecosystem integration | `api/integration` | 1, 18, 38 | ServiceClient, CampusRef | `/api/v1/integration/sites/` (Api-Key), `/reference/campuses/`; commands `sync_ecosystem`, `create_service_client` | Pulls sites and class lists from the SRMS nightly; pushes coursework to the SRMS and completions to the HRMS |
| Completions | `api/courses` | 20, 38 | Completion | via `sync_ecosystem --push-training` | Recorded today only by the demonstration data; automatic completion is item 5.03 |
| Sign-in and roles | `api/iam` | 41 | Role, RoleScope, TotpDevice, LoginAttempt | `/api/v1/auth/*` | Session sign-in; authenticator code for administrators and course administrators; lockout |
| Audit | `api/audit` | 41 | AuditLog | (none; read in the Django admin) | Insert-only, protected by a database trigger |
| Home, To do and search | `api/core` | 29 | (reads the above) | `/api/v1/home/`, `/to-do/`, `/search/?q=` | A Home for each role (items 2.07 to 2.09): a student's work due, overdue, new feedback and progress; teaching staff's work to mark, sites with nothing new for the coming week and students not seen in 14 days; site figures for course administrators and administrators. To do gathers what waits for the person, oldest first, marked overdue. Search finds only what the person may open, and people for staff only |
| Web app | `web/` | 27, 29 | (uses the above) | consumes `/api/v1` | The HRMS's frame in the crest's colours with the LMS's amber accent (ADR 0010): Home by role, To do, search (Ctrl K), breadcrumbs, shareable addresses (a dependency-free hash router, as the HRMS's), four tabs and sheets on a phone; My courses, the course site, notifications; assignments, the marking screen (after Canvas SpeedGrader), rubrics, the gradebook with the working of each total, accommodations and notification settings (`web/src/features/assignments`, `marking`, `rubrics`, `gradebook`, `accommodations`, `notifications`); an offline queue for writes that are safe to send again (item 4.02); installable; every journey checked at 360px |
| Practicals in the field (web) | `web/src/features/practicals` | 15, 19, 30 | (uses `api/practicals`) | `#/sites/{id}/practicals`, `/practicals/{task}/observe/{student}`, `/practicals/competency`, `/practicals/portfolio`, `#/sites/{id}/logbook` | Items 3.12 to 3.15 and 5.15 on a phone in the field: big toggles and strong contrast, camera photos, the place only when asked for. Observations and logbook entries go through the offline queue with one Idempotency-Key for every try; their photos wait in IndexedDB until the record has gone, then ask for its answer again under the same key and are sent once. The task and class list are kept on the phone for marking without signal and removed on sign-out |

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

Rubrics, practical and competency assessment, forums and
messages, calendar, attendance ([ADR 0008](adr/0008-attendance-in-the-lms.md)), certificates,
packaged content, analytics and the rest of the checklist's phases 2 to 7.
