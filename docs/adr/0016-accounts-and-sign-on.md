# ADR 0016: Accounts for students and lecturers, and when one sign-on comes

**Status:** proposed (decision D7, ecosystem open decisions 1 and 2); not yet taken. Items 0.12 and 1.22
wait for it.
**Date:** 5 October 2026.

## Context

The LMS creates person references from the SRMS and the HRMS but no accounts, so nobody can use it until
this is settled. GSA may already have a directory (for example Google or Microsoft accounts); building one
sign-on before knowing would risk building it twice.

## Recommended answer

1. Create accounts from the synced person records, with a one-time link to choose a password (as the HRMS
   does since its item 1.29); close the account when the record goes inactive (item 1.22).
2. One sign-on for the three systems in a later phase, once GSA says whether it has a directory.

## Consequences if taken

- The invitation and password-reset flows are ported from the HRMS (item 1.10).
- Each system keeps its own sign-in, under the same policy, until one sign-on is built.
