# ADR 0014: Packaged content: SCORM and H5P players

**Status:** proposed (decision D2); not yet taken. The items it holds up (0.07, 5.12, 5.13) wait for it.
**Date:** 5 October 2026.

## Context

Donor and Ministry courses often arrive as SCORM packages. H5P is the cheapest way for lecturers to make
interactive exercises. cmi5 and xAPI are SCORM's successors. The H5P server library for PHP is GPL and
cannot be used ([ADR 0002](0002-licence-policy.md)).

## Recommended answer

1. Play SCORM 1.2 and 2004 with the scorm-again player (MIT) in Release 2, tracking completion and score
   into the gradebook (item 5.12).
2. Play H5P with h5p-standalone (MIT) in Release 2 (item 5.13).
3. cmi5 only when content in that format arrives; prefer it when GSA commissions new packages (item 6.09).

## Consequences if taken

- Both players are already approved in principle ([ADR 0012](0012-new-components.md)).
- Packages are stored and served by the LMS like other course files, under the same access rules.
