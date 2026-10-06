# ADR 0010: Navigation by role: a Home for each role, search for everything, and To do

**Status:** accepted on the recommended answer, 5 October 2026 (feature 29, item 2.07, following HRMS
ADR 0010); GSA may revise.
**Date:** 5 October 2026.

## Context

The LMS today opens on a list of the person's courses, with a side menu of two entries (My courses, and
Admin as a placeholder) and roles shown as system codes. Canvas's To do list and Moodle 5's course overview
show each person what is due, what is new and what needs marking. The HRMS tried three ways to navigate on
the same pages and roles (a grouped sidebar, section menus with sub-tabs, and a Home for each role with a
command bar) and chose the third (HRMS ADR 0010, pull request 37). The three GSA systems share one frame, so
a person who uses two of them finds their way the same in both.

## Decision

1. **Home for each role.** Students, lecturers, heads of department, course administrators and
   administrators each get their own Home with shortcuts to the pages that role uses, figures for the
   sites they belong to, and the work waiting for them:
   - a student: what is due this week, what is overdue, new feedback, progress in each course (item 2.08);
   - a lecturer: work waiting to be marked, sites without content for the coming week, students not seen
     lately (item 2.09).
2. **Search for everything.** The bar in the header, or Ctrl K, finds courses, pages, people and actions.
   Each person finds only what they may open.
3. **To do** in the header, with its count.
4. **A breadcrumb** on every page but Home, and page addresses that can be shared (a router, item 2.10).
5. **Phones** get four tabs at the bottom (Home, To do, Search, Me), sheets in place of drop-downs, and
   touch targets of 44px or more.
6. **Roles as people say them** ("Lecturer, Crop Science"), never system codes.
7. **The crest's colours**, as in the HRMS, with the LMS's own accent (amber in the ecosystem document);
   the current brown accent (#8A4B12) is replaced (item 2.07). Every pairing of text and ground meets
   WCAG AA. Fonts are served from the app itself, as the HRMS does.

## Consequences

- The frame and its components are ported from the HRMS (`core/home.py`, `web/src/app`), adapted for course
  sites in place of campuses and units.
- Pages not on a role's Home are found by search; the browser journeys open pages that way.
- A router library is needed ([ADR 0012](0012-new-components.md)).
