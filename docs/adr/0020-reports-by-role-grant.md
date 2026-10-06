# ADR 0020: Who reads the reports that leave a course

**Status:** proposed; built this way so that the reports (items 6.03, 6.04) can be used and shown. GSA to
confirm who holds each role.
**Date:** 6 October 2026.

## Context

Heads of department and the Registrar need the course reports (item 6.03); HR and the Ministry the staff
development report (item 6.04). The LMS had no role for either reader. A course site records its campus and
term, but not its department, and the SRMS's offering feed does not yet name the programmes an offering
belongs to. Every total that leaves a course hides groups smaller than five (item 6.06, gap G3).

## Decision

- Two system roles, granted like the others (iam.RoleScope) and needing an authenticator code:
  **Head of Department** (`head_of_department`), scoped by the grant's unit code (the HRMS unit), and
  **Registrar** (`registrar`), scoped by the grant's campus, or every campus when the grant names none.
- A head of department reads the course report for the sites on which a member of staff of the unit (by
  the HRMS record) teaches, and the staff development report for the unit's staff.
- Administrators, course administrators and the auditor read every row. HR's course administrators read
  the staff development report as course administrators; the Ministry reads through the auditor role.
- The programme is taken from the SRMS offering (`programme_codes` or `programme_code`) once the SRMS sends
  it; until then a site is reported under "Programme not known".
- The named list of who is overdue with required training stays with course administrators (Staff
  development, Required training); the reports give totals only.

## Consequences

- The SRMS's offerings endpoint should add the offering's programmes (SRMS work).
- A site taught by staff of two units appears in both heads' reports.
- Changing a person's roles signs them out, as for every role.
