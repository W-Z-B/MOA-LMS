# ADR 0002: Licence policy, amended to match what ships

**Status:** proposed. Implemented by the pull request that adds the licence gates (checklist item 0.20);
merging it accepts this decision. Same terms as HRMS ADR 0002 (1 October 2026).
**Date:** 5 October 2026. **Amends:** the licence policy in ADR 0001.

## Context

ADR 0001 allows only MIT, BSD, Apache 2.0, PostgreSQL or PSF licensed components in the shipped product.
The first scan of what the LMS image installs (`scripts/check_licences.py`, 5 October 2026) found the same
four packages outside that list as the HRMS did, all present since the first build:

| Package | Licence | Why it is there |
|---|---|---|
| psycopg, psycopg-binary | LGPL-3.0-only | The PostgreSQL driver. Django supports only psycopg 2 and 3, and both are LGPL. |
| psycopg-pool | LGPL-3.0-only | Connection pool from the same project, required by Procrastinate. |
| pyphen | GPL-2.0+, LGPL-2.1+ or MPL-1.1, at the user's choice | Hyphenation for WeasyPrint (PDF output, planned for certificates). |

The web bundle ships only React, React DOM and Scheduler (MIT). Build and test tools include MPL-2.0
packages (lightningcss inside Vite, axe-core for the accessibility checks) that never reach the product.
The operating-system packages in the base images include LGPL system libraries (glibc, Pango, Cairo).

The policy as written cannot be met without replacing the database driver, which is not possible on Django.
The aim behind it (no licence fees, nothing that obliges GSA to publish its own code, nothing
source-available) is still right.

## Decision

1. **Permissive licences** may be shipped freely: MIT, MIT-0, MIT-CMU, BSD-2-Clause, BSD-3-Clause,
   Apache-2.0, ISC, PSF-2.0, Python-2.0, PostgreSQL, Zlib, 0BSD, Unlicense, CC0-1.0, HPND, BlueOak-1.0.0.
2. **Weak copyleft (LGPL, MPL)** may be shipped only as a **named exception**: the library is used
   unmodified, installed as its own package, and listed with its reason in `scripts/licence-policy.json`.
   The exceptions today are psycopg, psycopg-binary and psycopg-pool (LGPL-3.0) and pyphen, taken under
   MPL-1.1.
3. **Strong copyleft (GPL, AGPL), SSPL, BUSL and other source-available licences** are not shipped. This is
   why Moodle (GPL), Canvas and Open edX (AGPL) are references, not components ([ADR 0004](0004-build-path.md)).
4. **Development and test tools** that never ship may use any OSI-approved licence. The web gate lists
   the non-permissive ones so they stay visible.
5. **Operating-system packages** in base images are system libraries outside this policy. They are
   listed in the software bill of materials with each release (checklist item 7.20).
6. **Programs run beside the product, not linked into it,** are named in the decision that needs them. The
   video converter FFmpeg (LGPL) is one, if decision D3 is taken ([ADR 0015](0015-video-and-captions.md)).
7. **Enforcement:** CI runs both licence gates on every pull request (`scripts/check_licences.py` for
   Python, `scripts/check_npm_licences.mjs` for the web), each after its own tests. Adding an exception is
   a pull request that edits `licence-policy.json` with a reason, reviewed like code.

## Consequences

- No change to cost: every component is free of licence fees.
- GSA's own code carries no obligation to be published. LGPL and MPL obligations apply to the libraries
  themselves: each release includes a third-party notices file that names every shipped package, its
  licence, and where the source of the LGPL and MPL packages is obtained (item 7.20). GSA's legal
  adviser should confirm this reading before go-live.
- A future component with a weak-copyleft licence needs its own named exception when it is added. The
  push-notice library pywebpush (MPL-2.0) is the one already foreseen ([ADR 0012](0012-new-components.md)).

## Note on the exceptions added for push notices and lecture video, 6 October 2026 (items 4.04, 4.06)

Added as named exceptions in `scripts/licence-policy.json`, each used unmodified as its own package, on the
recommended answers to decisions D10 ([ADR 0012](0012-new-components.md)) and D3
([ADR 0015](0015-video-and-captions.md)):

| Package or program | Licence | Why it is there |
|---|---|---|
| pywebpush | MPL-2.0 | Push notices to the installed app (item 4.04): encrypts each notice for the one browser that subscribed. |
| py-vapid | MPL-2.0 | Part of pywebpush: signs each notice with GSA's VAPID key. |
| certifi | MPL-2.0 | The certificate authorities that requests (through pywebpush) trusts to reach the browsers' push services. |
| FFmpeg (a program, not a library) | LGPL-2.1-or-later | Lecture video (items 4.06, 4.07): the low, standard and sound-only copies and the poster frame. Built in `api/Dockerfile` from Debian's source with LGPL parts only and OpenH264 (BSD-2-Clause); run by the job worker as a separate process, never linked into the product (point 6). |

Everything else pywebpush brings is permissive (aiohttp, requests, urllib3, http-ece and their own
dependencies: Apache-2.0, MIT, BSD-3-Clause or PSF-2.0). whisper.cpp, the optional speech recognition for
captions, is MIT and is not in the image; it is listed under "programs" so every program the product runs is
named. `scripts/check_licences.py` now also asks FFmpeg, where it is installed, what licence it is under and
how it was built, and fails if it was configured with GPL, non-free or version-3 parts.
