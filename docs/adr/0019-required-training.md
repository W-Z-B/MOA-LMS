# ADR 0019: The HRMS says which staff must take which training

**Status:** proposed (decision D13); built on the recommended answer and switched off
(`HRMS_TRAINING_REQUIREMENTS_SYNC`); accepted when GSA confirms. Items 0.17 and 5.05 wait for that answer
(information request, question 37).
**Date:** 5 October 2026; built 6 October 2026.

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

## As built

- **The HRMS** (its item 5.24, branch `feature/integration-lms-endpoints`) lists the requirements in force at
  `GET /api/v1/integration/training-requirements/` under a new scope, `training:read`: the HRMS's number, the
  LMS course code, the title, the post, unit and campus (null applies to everyone; the post is compared without
  regard to case), the days to complete it and how often it is renewed. The whole list is sent each time; one
  no longer listed has been retired. Its staff directory also names each person's supervisor
  (`supervisor_employee_no`), to whom the LMS sends requests to join a staff-development course.
- **The LMS** reads the list each night at 06:00 UTC, before the daily required-training run at 06:30
  (`integration.tasks.sync_training_requirements`, or `manage.py sync_ecosystem --training-requirements`),
  in `integration.hrms.sync_training_requirements`. Each requirement is kept as a `RequiredTraining` row with
  `source` hrms and the HRMS's number (`hrms_id`) on the staff-development course with that code. A code the
  LMS has no staff-development course for is noted against the run (`unmatched_course`) with the HRMS's title,
  so a course administrator can make the course; the run carries on. A requirement no longer listed stops
  being in force. Each change is audited, and each run recorded under Admin, **Integration runs** (kind
  `requirement_sync`); a refused key (HTTP 401 or 403, the scope not given) is a failed run.
- **Course administrators** keep their own requirements beside those of the HRMS (`source` lms), which the
  read never touches. While the setting is on, those from the HRMS are read-only in the LMS: a change is
  refused with the code `kept_in_hrms`, and the required-training screen shows where each one is kept.
- **Switched off** (`HRMS_TRAINING_REQUIREMENTS_SYNC=0`) until GSA confirms the decision and the HRMS gives the
  LMS's key the `training:read` scope. Until then course administrators keep every requirement in the LMS, as
  before.
