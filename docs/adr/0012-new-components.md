# ADR 0012: New components approved under the licence policy

**Status:** accepted on the recommended answer, 5 October 2026 (decision D10); GSA may revise.
**Date:** 5 October 2026.

## Context

Release 1 and 2 features need components the scaffold does not have: page addresses that can be shared, a
rich text editor with maths, documents shown in the page, packaged content, charts and push notices. Each
must meet the licence policy ([ADR 0002](0002-licence-policy.md)) and none may charge per user.

## Decision

These are approved in principle. Each is added, at an exact version, with the feature that needs it, and
passes the licence gates then:

| Component | Licence | For | Item |
|---|---|---|---|
| A router library (as the HRMS chooses for its frame) | MIT | Shareable page addresses, breadcrumbs | 2.10 |
| TipTap (rich text editor, core and the extensions used) | MIT | Pages, announcements, feedback | 2.12 |
| KaTeX | MIT | Maths in pages and questions | 2.12 |
| PDF.js | Apache-2.0 | Documents shown in the page | 2.14 |
| scorm-again | MIT | Playing SCORM 1.2 and 2004 packages (if D2 is taken) | 5.12 |
| h5p-standalone | MIT | Playing H5P exercises (if D2 is taken) | 5.13 |
| A chart library with a permissive licence | MIT or similar | Analytics and reports | 6.x |
| pywebpush and its helpers | MPL-2.0 (pywebpush) | Push notices to the installed app | 4.04 |
| The HRMS's test and quality tools | see [ADR 0009](0009-quality-tooling.md) | Quality gates | 0.20 |

pywebpush is a weak-copyleft package: it ships only as a named exception in `scripts/licence-policy.json`,
used unmodified, as ADR 0002 sets out.

## Consequences

- The licence gates in CI check each component, and its dependencies, when it is added.
- The H5P server library for PHP is GPL and is not used; only the standalone player is.
- A component not on this list needs its own decision record or an amendment to this one.
