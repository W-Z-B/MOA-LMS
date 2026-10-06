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

## As added: the editor, maths and PDF viewer (items 2.12 to 2.14, 5 October 2026)

Added at exact versions with the content screens, and only what they use:

| Package | Version | Licence | What for |
|---|---|---|---|
| `@tiptap/core`, `@tiptap/pm`, `@tiptap/starter-kit`, `@tiptap/extension-table`, `@tiptap/extension-image` | 3.31.4 | MIT | The page editor. TipTap's React layer is not used: a small wrapper drives the core |
| `katex` | 0.19.0 | MIT | Maths, stored in pages as TeX (`data-math`) and drawn with `trust: false` |
| `pdfjs-dist` | 6.4.299 | Apache-2.0 | PDFs shown in the page, without WebAssembly |

Everything they bring with them is MIT: the TipTap extensions in the starter kit, the ProseMirror packages,
`orderedmap`, `rope-sequence`, `w3c-keyname`, `linkifyjs` and `commander` (KaTeX's command line, never
loaded by the app). `pdfjs-dist` lists `@napi-rs/canvas` (MIT) as an optional dependency for Node.js; it is
never part of the web bundle. `node scripts/check_npm_licences.mjs` passes with no new exception.

Nothing they add needs the Content-Security-Policy changed: TipTap's base styles are in the app's own
stylesheet instead of the style element it would inject, tables are written without width styles, KaTeX
draws into the page through the CSS object model rather than an HTML string, its fonts are served by the app as files (never inlined as data: addresses, which `font-src` refuses),
and PDF.js runs its worker from the app's own files with WebAssembly turned off.

### Page weight

The shell budget stays at 160 KB compressed. The editor and KaTeX are loaded only on the screens that use
them, so a student's pages carry neither unless a page has a formula, and the PDF viewer only when someone
asks to see a PDF in the page. The page-weight check (`web/scripts/check-bundle-size.mjs`) used to add up
every script in the build, which would have counted these parts against every page. It now counts what
every page loads (index.html and what it names) against the 160 KB budget, and lists each part loaded on
demand against a budget of 400 KB of its own.

| Measured with `npm run check:bundle` | Before | After |
|---|---|---|
| Shell, every page | 88.9 KB | 94.8 KB |
| Page editor (TipTap and ProseMirror) | | 134.5 KB, editing pages only |
| KaTeX (script and stylesheet; fonts as a formula needs them) | | 78.7 KB, pages with maths |
| PDF viewer, and its worker | | 125.2 KB and 366.9 KB, when a PDF is shown in the page |

A student opening a page with maths loads about 175 KB of code, inside the 500 KB the gold standard allows
a common page. The PDF viewer with its worker is over 500 KB on its own, once: that is why it is never
loaded unasked. "Download" is always beside it, and the service worker keeps the viewer after its first use.

## As added: the package players (items 5.12, 5.13, 6 October 2026)

| Package | Version | Licence | What for |
|---|---|---|---|
| `scorm-again` | 3.4.5 | MIT | The SCORM 1.2 and 2004 run-time in the web app (loaded only when a package is opened), and its cross-frame client inside the sandboxed player |
| `h5p-standalone` | 3.8.2 | MIT | Playing H5P files inside the sandboxed player |

Neither brings any dependency. h5p-standalone's distribution includes the Open Sans and Inter fonts (SIL Open
Font Licence 1.1, a permissive font licence) for H5P's own styles. Both are copied at build time from their
npm packages into `/players/` (`web/vite.config.ts`), beside the LMS's two small frame scripts in
`web/public/players/`; the sandboxed pages load them from there, so nothing comes from a CDN. Caddy lets
sandboxed frames read `/players/*` (they are public code). `node scripts/check_npm_licences.mjs` passes with no
new exception. How they are used is in [ADR 0030](0030-packaged-content-as-built.md).

| Measured with `npm run check:bundle` | |
|---|---|
| Shell, every page | 131.4 KB (unchanged) |
| scorm-again run-time, SCORM 2004 / 1.2 | 77.1 KB / 19.2 KB, when a package of that version is opened |
| h5p-standalone (frame bundle and main) | 46.0 KB and 7.4 KB, inside the H5P player only |
