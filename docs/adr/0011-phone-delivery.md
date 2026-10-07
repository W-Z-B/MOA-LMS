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

## Note on point 3, 5 October 2026 (item 4.02)

How "checked against the server's clock" works for work sent later from the offline queue: the server's
time alone decides whether work is late, as the Moodle app does, because a device's clock can be set back.
The device's time is kept beside it (`client_submitted_at` on the submission, refused when more than ten
minutes ahead of the server) and shown to teaching staff in the list of submissions, so a lecturer who
accepts that the work was done in time excuses the lateness with an extension. Quiz answers already keep
the device's time in the same way, and practical observations and logbook entries refuse a device time more
than seven days old or ten minutes ahead.

## Note on shared phones, 6 October 2026 (items 4.02, 3.15)

Phones on campus and on the farm are shared. Every write kept on a device (the offline queue, and the
photographs of a field observation or logbook entry) records the account that made it, and is listed and
sent only while that account is signed in. What one person left waiting is never sent under someone
else's session; it stays on the device until its owner signs in again. A write with no owner, or made with
no one signed in, is not kept.

## Note on offline reading, data-light mode and push, 6 October 2026 (items 4.03 to 4.05)

- **Offline reading (point 4).** "Keep to read offline" on a module asks the server what it needs
  (`GET /api/v1/offline/modules/{id}/`: its pages, documents, the pictures its pages show, and each video in
  the low copy with its poster frame and captions) and shows the space it will take, what cannot be kept
  (links) and the space the device has left, before anything is fetched. The files go into a cache that
  belongs to the signed-in person (`gsa-lms-offline-<account id>`); the service worker answers from it only
  when the network cannot be reached and only while that person is signed in. Fetching them records no
  progress (`offline=1`). Downloaded, under Me, lists what is kept with its size and removes it.
- **Shared phones.** As for writes kept on a device: signing out removes everything the person kept; when
  a different person signs in, whatever an earlier person left is removed before anything is shown. A session
  that simply ends keeps the person's modules until they sign in again. Signing out also turns push off for
  that device, so one person's notices never appear on a phone someone else is using.
- **Data-light mode (point 6)** is a setting of the device, under Me (Downloaded), because it is about the
  line the device is on. Until the person chooses, the browser's connection hints decide where it gives them
  ("save data" or a 2G or 3G line: on; Wi-Fi or a cable: off), and otherwise it is on for a phone and off for
  a computer. Pictures on pages and photographs wait behind a button with their size; video starts on the low
  copy and fetches nothing, not even the poster frame, until Play; large downloads say their size.
- **Push notices (point 5)** are Web Push with VAPID (pywebpush, a named exception under ADR 0002), off until
  `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` are set (`python manage.py vapid_keys` makes a pair). A person
  turns push on per device, and per kind of notification in the notification settings; released marks,
  course announcements and reminders before a due date are kinds of their own. The job worker sends each
  notice once it is committed. A notice carries only its title and the page it opens; its text stays behind
  sign-in. A subscription may name only a known push service (`PUSH_SERVICE_HOSTS`), so the server never sends
  a request to an address someone chose, and one the service reports gone, or that fails five times in a
  row, is removed.
