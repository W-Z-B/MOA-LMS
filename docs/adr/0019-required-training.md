# ADR 0019: The HRMS says which staff must take which training

**Status:** proposed (decision D13); not yet taken. Items 0.17 and 5.05 wait for it.
**Date:** 5 October 2026.

## Context

The LMS delivers staff-development courses and already sends completions to the HRMS. The HRMS knows each
post and lists required training by post as a gap of its own. One owner per fact is the ecosystem's first
rule.

## Recommended answer

The HRMS owns the requirement (who must take what, by post or unit, and how often it must be renewed). The
LMS reads it, enrols the people, delivers the course, reminds them before it is due or expires, and reports
each completion with its expiry date (items 5.05, 5.06).

## Consequences if taken

- The HRMS needs an integration endpoint for training requirements; the LMS a scope to read it.
- Renewal reminders come from the LMS, and the HRMS sees completions and expiries in the staff record.
