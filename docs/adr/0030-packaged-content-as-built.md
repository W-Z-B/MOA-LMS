# ADR 0030: Packaged content, the statement store, the content library, course interchange and digital badges, as built

**Status:** proposed; built this way on 6 October 2026, GSA to confirm. Follows [ADR 0014](0014-packaged-content.md)
(decision D2, accepted on the recommended answer) and [ADR 0012](0012-new-components.md).
**Items:** 5.10, 5.12, 5.13, 5.14, 6.08, 6.09.

## Context

D2 settled that SCORM 1.2 and 2004 play with scorm-again and H5P with h5p-standalone, both MIT. A package is
someone else's web application: its scripts must never run with a learner's session on the LMS's own origin.
GSA has no second domain for content yet (D9, hosting), so the isolation has to work on one origin.

## Decision

**Packages (5.12, 5.13).** A package is a content item of kind `package`: the zip is the item's file (so the
storage allowance, licence, release conditions, course copy and takedown all apply), and a `ContentPackage`
says what it is and how it counts. Before it is kept it is checked (`api/packages/archive.py`): a zip of at
most `UPLOAD_LIMIT_PACKAGE_MB`, at most `PACKAGE_MAX_ENTRIES` files and `PACKAGE_MAX_UNPACKED_MB` unpacked, no
entry compressed more than 100 times over, no name leaving the package (`..`, `/`, drive letters,
backslashes, control characters), no links, no encrypted entries, no programs, every entry's size and
checksum true, and a manifest (`imsmanifest.xml` or `h5p.json`) that is well formed and declares no DTD or
entities. It is never unpacked onto the disk: each file is read from the zip when asked for, by exact name.

**The player.** The web app opens a package in a frame with `sandbox` (no `allow-same-origin`), at
`/api/play/<signed token>/<entry>`. Every response from there carries `Content-Security-Policy: sandbox …`
too, may load only the LMS's own files, may be framed only by the LMS, and sends no Referer. The page
therefore has an origin of its own: it cannot read the LMS's pages, cookies or storage or call its API. The
token, signed by the LMS and lasting `PACKAGE_PLAY_HOURS`, names one attempt; it is the only key to the files.

- SCORM: the LMS puts scorm-again's cross-frame client at the top of each page of the package, as the page's
  `window.API` and `window.API_1484_11`. Calls go by `postMessage` to the web app, which answers only its own
  player frame, runs scorm-again's run-time (`Scorm12API` / `Scorm2004API`) and commits the CMI data as the
  learner, with the CSRF token, to `/api/v1/package-attempts/<id>/commit/`. The run-time's end-of-session
  beacon cannot carry the token, so every commit is a synchronous request from the web app (the page closing
  is the package's frame, never the web app).
- H5P: the LMS serves a small page that runs h5p-standalone inside the sandbox, drawn in the page itself
  (a frame inside the sandbox would have yet another origin). H5P's xAPI statements go to the web app the
  same way and on to the statement store. Sandboxed pages may not use the browser's storage; the LMS gives
  them a store in memory, which H5P needs.
- H5P exercises are **not authored in the LMS**: lecturers use the free H5P editor or the Lumi desktop app
  (AGPL, not shipped with the LMS) and put the `.h5p` file up. The H5P server library for PHP (GPL) is not used.

**Results.** CMI data is kept per learner, attempt and part. A part is complete at "completed" or
"passed"; the attempt when every part is; the item is then complete for release conditions and progress
(`ItemCompletion`, how `package`). Teaching staff try a package in preview attempts that never count. A
package with a weight counts in coursework and the gradebook by the learner's best scored attempt (a
completed attempt with no score counts as full marks, as Moodle's "learning objects" method does). **Scores
come from the learner's browser** and a determined student could forge one; the upload form says a weighted
package suits practice and low-stakes work.

**Statement store (6.09).** The LMS keeps xAPI statements about its own packages only: H5P results, and the
results it writes itself when a SCORM attempt is completed, passed, failed or scored. A statement is accepted
only for the sender's own attempt (its `context.registration`) and only about that package's activities; the
actor is always the learner's account at the LMS's address, never what the statement says. Teaching staff
read the statements of their courses by activity, learner, attempt or date. It is **not a general LRS**: no
voiding, no state or profile APIs, no outside clients. A general LRS (cmi5, outside tools, a warehouse) would
need its own decision.

**Content library (5.14).** Library items (pages, files, links, packages) sit on a department's shelf (an HRMS
unit code) or the whole School's, each with its licence and source, and open educational resources with their
publisher (FAO, CABI and the like) under an open licence. Teaching staff browse and copy an item into a module
they teach, as a draft. Department shelves are managed as department question banks are; a course's question
bank is shared by copying it to a department bank, with its licence.

**Interchange (6.08).** A course exports as an IMS Common Cartridge 1.3 (modules, pages, files, links,
packages, assignments as web pages, quiz questions as QTI 1.2 where the type allows; licences in the resource
metadata; a README of what was left out). Cartridges and Moodle course backups (`.mbz`, gzipped tar or zip)
import as drafts with a report of what came in and what did not; Moodle questions go through the Moodle XML
importer. People, marks, submissions, forums and logs are never imported. The same archive and XML defences
as packages apply, and a tar backup is read as a stream refusing links and devices.

**Digital badges (5.10).** Each certificate is also an Open Badges 3.0 `OpenBadgeCredential` signed as a
VC-JWT with an Ed25519 key (`alg` EdDSA): the payload is the credential with the registered claims `iss`,
`jti`, `nbf`, `iat` and `exp`; the holder is named by a salted identity hash. The key is made per
installation and kept encrypted with `FIELD_ENCRYPTION_KEY`; the issuer profile and a JWKS are public at
`/api/badges/issuer.json` and `/api/badges/jwks.json`; `manage.py rotate_badge_key` rotates it and retired keys
stay published. The public check page and API verify a presented credential and answer a withdrawn
certificate as withdrawn. Issuing waits for `OPEN_BADGES_ENABLED` (off): the issuer's address comes from
`PUBLIC_URL` and is written into every credential, so GSA's permanent address must be settled first.

## Consequences

- No package can act as the learner on the LMS; what it can do is report results, which are trusted only as
  far as a browser can be.
- Packages with frames of their own inside them, or that need the browser's lasting storage, may not run
  fully; the LMS gives them storage in memory. Opening content from a second domain would lift this, if GSA
  provides one (D9).
- OB 3.0 asks verifiers to support RS256; EdDSA is newer in the wallets GSA's staff may use. Should a wallet
  refuse EdDSA, an RS256 key can be added beside it.
- New settings: `UPLOAD_LIMIT_PACKAGE_MB` (above 50 needs Caddy's `request_body` raised), `PACKAGE_MAX_ENTRIES`,
  `PACKAGE_MAX_UNPACKED_MB`, `PACKAGE_PLAY_HOURS`, `OPEN_BADGES_ENABLED` (docs/SETUP.md).
