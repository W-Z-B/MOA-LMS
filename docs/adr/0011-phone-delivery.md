# ADR 0011: Phones use the installable web app, with push notices and offline work

**Status:** accepted on the recommended answer, 5 October 2026 (features 27 and 28, following HRMS
ADR 0005); GSA may revise.
**Date:** 5 October 2026.

## Context

Most students reach the LMS by phone. Hinterland connectivity has improved (236 of 253 communities online by
July 2025), but data costs money and the farm plots have no signal. The Moodle app works offline for almost
everything; Canvas is read-only offline; Kolibri works with no internet at all. Store apps for Android and
iPhone would need developer accounts in GSA's name, yearly fees, store review and a second code base.
Push notices to an installed web app work on Android browsers and, since iOS 16.4, on iPhones when the app
is added to the home screen. The LMS already has a manifest and a service worker that caches the shell; the
service worker refers to an offline queue that does not exist (item 4.02).

## Decision

1. Phones use the installable web app. No store apps in the current scope.
2. Every screen is checked at 360 pixels wide, in the browser journeys on every pull request (item 4.01).
3. **Offline work:** the HRMS's offline queue is ported. Submissions, quiz answers, field marks and forum
   posts made without signal are sent when it returns, with the time the person acted, checked against the
   server's clock so the due-date rule stays fair (item 4.02).
4. **Offline reading:** a module can be downloaded, with the space it will take shown first (item 4.03).
   What is downloaded and what is waiting to be sent are shown plainly.
5. **Push notices** for released marks, announcements and due dates, with keys held as server secrets
   (item 4.04).
6. A data-light mode loads images and video only when asked for (item 4.05).

## Consequences

- One code base serves desktop and phone.
- Push needs pywebpush (MPL-2.0), a named exception under ADR 0002 when it is added
  ([ADR 0012](0012-new-components.md)).
- Personal data cached on a phone is limited to the person's own courses and work, and cleared on sign-out.
- If GSA later wants store apps, the web app can be wrapped without a rewrite; that would be a new decision.
