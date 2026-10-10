"""The permission table: every endpoint, every method, every role, tested including every refusal (item 1.16).

HOW TO DECLARE A NEW ENDPOINT
-----------------------------
Every route the URL resolver knows (Django admin aside) must have a line in TABLE, one per method:

    "GET /api/v1/terms/{pk}/": SITE_READERS,

The key is the method and the route as this module prints it: regex groups and converters become {name},
so "^terms/(?P<pk>[^/.]+)/$" reads "/api/v1/terms/{pk}/". The value is an access profile (below) naming the
roles that may pass; adjust one with + and - ("SITE_TEACHERS + AUDITOR", "SIGNED_IN - STUDENTS"), and add
HIDDEN ("SITE_TEACHERS + HIDDEN") where the code answers 404 rather than 403, so that a refusal does not
tell that a record exists. Run this module: an endpoint without a line fails test_every_route_is_declared
with the exact key to add, and a line that matches no route fails test_no_stale_declarations.

A {name} in the route is filled from the fixture world: by the name itself where it is specific ({site},
{code}, {token}, {person_id}, {position}), otherwise from the path segment before it ("assignments/{pk}"
is the world's assignment). A new resource needs a row in SEGMENT_OBJECTS and, if the world has none yet,
one object built in build_world(). A route that needs a query string gets one in QUERY; a write whose body
names its site or parent (a create, mostly) gets that body in BODY, so that the refusal is about the site.

What is checked, for each role:
- allowed: the request is not refused (no 401, 403 or 404) and does not fail (no 500). A 400 for the body
  this module sends (empty, or the BODY line) counts as allowed: the request got past the permission layer;
- refused: 401 or 403; under HIDDEN also 404, or a 400 saying that a site or record named in the body does
  not exist (courses.access.TaughtRecord). A 400 for anything else is not a refusal: give the write a BODY
  that is valid up to the permission check, or make the view settle the permission first (item 1.15);
- a list that answers 200 to a refused role passes only when the world's record for that list is not in it:
  the role may use the list but must not see the record. ROWS does the same for a list inside a record.

PERMISSION_TABLE_RECORD=<file> makes test_permission write what every role got instead of checking, one JSON
line per endpoint, to compare a new endpoint's behaviour with what it should be before declaring it.

The roles: anonymous; student (a member of the site and the owner of the student records in the world);
classmate (another student of the same site, who owns nothing); lecturer (teaches the site); elsewhere (a
lecturer who teaches only another site); course administrator; administrator; auditor; data protection
officer. Everyone who signs in has the authenticator flag in their session, as client_for sets it.

Every request runs in a transaction that is rolled back, so one role's write never changes what the next
role sees; the world is built once for the module.
"""

import hashlib
import json
import os
import re
import secrets
from datetime import date, timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import override_settings
from django.urls import URLPattern, URLResolver, get_resolver
from django.utils import timezone
from rest_framework.test import APIClient

from iam.sessions import LAST_ACTIVITY, SIGNED_IN_AT

ROLES = (
    "anonymous",
    "student",
    "classmate",
    "lecturer",
    "elsewhere",
    "course_admin",
    "administrator",
    "auditor",
    "dpo",
)


class Access:
    """The roles that may pass, and whether a refusal may answer 404 (HIDDEN)."""

    def __init__(self, roles=(), hidden=False):
        unknown = set(roles) - set(ROLES)
        assert not unknown, f"unknown roles {unknown}"
        self.roles = frozenset(roles)
        self.hidden = hidden

    def __add__(self, other):
        return Access(self.roles | other.roles, self.hidden or other.hidden)

    def __sub__(self, other):
        return Access(self.roles - other.roles, self.hidden and not other.hidden)

    def __repr__(self):
        named = [role for role in ROLES if role in self.roles]
        return f"Access({', '.join(named) or 'nobody'}{', hidden' if self.hidden else ''})"


# Single roles, to adjust a profile with + and -.
ANONYMOUS = Access({"anonymous"})
STUDENT = Access({"student"})
CLASSMATE = Access({"classmate"})
LECTURER = Access({"lecturer"})
ELSEWHERE = Access({"elsewhere"})
COURSE_ADMIN = Access({"course_admin"})
ADMINISTRATOR = Access({"administrator"})
AUDITOR = Access({"auditor"})
DPO = Access({"dpo"})
HIDDEN = Access(hidden=True)

# The profiles. "The site" is the world's site: the student, classmate and lecturer are its members.
NOBODY = Access()
PUBLIC = Access(ROLES)
SIGNED_IN = PUBLIC - ANONYMOUS
OWN = STUDENT  # a personal record (a session, a notification): the world's are the student's
STUDENTS = STUDENT + CLASSMATE  # the site's students
STAFF = LECTURER + ELSEWHERE  # members of staff with an HRMS record, whatever they teach
PEOPLE = STUDENTS + STAFF  # accounts linked to a person record
ADMINS = COURSE_ADMIN + ADMINISTRATOR  # iam.services.SITE_ADMIN_ROLES: they teach every site
SITE_TEACHERS = LECTURER + ADMINS  # courses.access.can_teach on the site
SITE_MEMBERS = STUDENTS + SITE_TEACHERS
SITE_READERS = SITE_MEMBERS + AUDITOR  # courses.access.site_role: the auditor reads (item 1.02)
TEACHER_READERS = SITE_TEACHERS + AUDITOR
OWNER = STUDENT + SITE_TEACHERS  # a student's own work, and the staff who teach them
PARTICIPANTS = STUDENT + LECTURER  # the world's conversation is between these two
OVERSEERS = ADMINS + AUDITOR  # course administrators, administrators and the auditor
AUDIT_LOG = ADMINISTRATOR + AUDITOR
PRIVACY_OFFICERS = ADMINISTRATOR + DPO
PRIVACY_READERS = PRIVACY_OFFICERS + AUDITOR
SERVICE_KEY = NOBODY  # service-to-service: an Api-Key, never a person's session

# Every endpoint and method. Read "SITE_TEACHERS + HIDDEN" as: the site's teaching staff may; everyone else
# is refused, and those who cannot open the site are answered 404 (or "does not exist" for an id in a body).
# The auditor reads everything (item 1.02), the library and insights included, read-only. A teaching-only read
# below that still leaves the auditor out is deliberate and explained in docs/security/asvs-l2.md (the
# auditor's reading).
TABLE: dict[str, Access] = {
    # --- the platform -------------------------------------------------------------------------------------
    "GET /api/health/": PUBLIC,
    "GET /api/metrics": NOBODY
    + HIDDEN,  # a scraper's token only (METRICS_TOKEN), never a session: 404 or 401
    "GET /api/schema/": SIGNED_IN,  # API_DOCS_PUBLIC is off in production
    "GET /api/docs/": SIGNED_IN,
    "GET /api/v1/": SIGNED_IN,  # the router's index of links
    "GET /api/v1/home/": SIGNED_IN,
    "GET /api/v1/to-do/": SIGNED_IN,
    "GET /api/v1/search/": SIGNED_IN,  # results scoped to what the person may open
    "GET /api/v1/reference/campuses/": SIGNED_IN,
    "GET /api/v1/integration/sites/": SERVICE_KEY,
    # --- signing in and the account -----------------------------------------------------------------------
    "POST /api/v1/auth/login/": PUBLIC,
    "POST /api/v1/auth/logout/": SIGNED_IN,
    "GET /api/v1/auth/me/": SIGNED_IN,
    "POST /api/v1/auth/mfa/enrol/": SIGNED_IN,
    "POST /api/v1/auth/mfa/verify/": SIGNED_IN,
    "GET /api/v1/auth/sessions/": OWN,
    "POST /api/v1/auth/sessions/end-others/": SIGNED_IN,
    "DELETE /api/v1/auth/sessions/{pk}/": OWN + HIDDEN,
    "GET /api/v1/auth/access-review/": OVERSEERS,
    "POST /api/v1/auth/access-review/sign-off/": ADMINS,
    "POST /api/v1/auth/password/forgot/": PUBLIC,
    "POST /api/v1/auth/password/check/": PUBLIC,
    "POST /api/v1/auth/password/set/": PUBLIC,  # the emailed link's token is the credential
    "POST /api/v1/auth/password/change/": SIGNED_IN,
    "GET /api/v1/auth/email/": SIGNED_IN,
    "POST /api/v1/auth/email/change/": SIGNED_IN,
    "POST /api/v1/auth/email/confirm/": PUBLIC,  # the emailed link's token is the credential
    "GET /api/v1/auth/accounts/uninvited/": ADMINISTRATOR,
    "POST /api/v1/auth/accounts/invite/": ADMINISTRATOR,
    "POST /api/v1/auth/accounts/invite/{person_id}/": ADMINISTRATOR,
    "GET /api/v1/notifications/": OWN,
    "GET /api/v1/notifications/preferences/": SIGNED_IN,
    "PUT /api/v1/notifications/preferences/": SIGNED_IN,
    "POST /api/v1/notifications/read-all/": SIGNED_IN,
    "POST /api/v1/notifications/{pk}/read/": OWN + HIDDEN,
    "GET /api/v1/calendar/": SIGNED_IN,
    "GET /api/v1/calendar/feed/": SIGNED_IN,
    "POST /api/v1/calendar/feed/": SIGNED_IN,
    "DELETE /api/v1/calendar/feed/": SIGNED_IN,
    "GET /api/v1/calendar/feed/{token}.ics": PUBLIC,  # the secret address is the credential
    "GET /api/v1/approvals/waiting/": SIGNED_IN,
    "GET /api/v1/approvals/colleagues/": STAFF + COURSE_ADMIN,
    "GET /api/v1/approvals/delegations/": STAFF,  # the world's stand-in: the lecturer names elsewhere
    "POST /api/v1/approvals/delegations/": STAFF + COURSE_ADMIN,
    "POST /api/v1/approvals/delegations/{pk}/end/": LECTURER + COURSE_ADMIN + HIDDEN,
    # --- course sites and their content -------------------------------------------------------------------
    "GET /api/v1/sites/": SITE_READERS,
    "POST /api/v1/sites/": ADMINS,
    "GET /api/v1/sites/{pk}/": SITE_READERS + HIDDEN,
    "PATCH /api/v1/sites/{pk}/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/sites/{pk}/apply-template/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/sites/{pk}/contents/": SITE_READERS + HIDDEN,
    "POST /api/v1/sites/{pk}/copy-from/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/sites/{pk}/dates/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/sites/{pk}/dates/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/sites/{pk}/members/": TEACHER_READERS + HIDDEN,
    "POST /api/v1/sites/{pk}/reorder-modules/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/sites/{pk}/shift-dates/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/sites/{pk}/storage/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/site-templates/": SIGNED_IN,
    "POST /api/v1/site-templates/": ADMINS,
    "GET /api/v1/site-templates/{pk}/": SIGNED_IN,
    "PATCH /api/v1/site-templates/{pk}/": ADMINS,
    "DELETE /api/v1/site-templates/{pk}/": ADMINS,
    "GET /api/v1/modules/": SITE_READERS,
    "POST /api/v1/modules/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/modules/{pk}/": SITE_READERS + HIDDEN,
    "PATCH /api/v1/modules/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/modules/{pk}/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/modules/{pk}/reorder-items/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/content/": SITE_READERS,
    "POST /api/v1/content/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/content/check-page/": SITE_TEACHERS + ELSEWHERE,  # anyone who teaches somewhere
    "GET /api/v1/content/{pk}/": SITE_READERS + HIDDEN,
    "PATCH /api/v1/content/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/content/{pk}/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/content/{pk}/complete/": STUDENTS + HIDDEN,
    "GET /api/v1/content/{pk}/download/": SITE_READERS + HIDDEN,
    "POST /api/v1/content/{pk}/duplicate/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/content/{pk}/move/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/content/{pk}/report/": SITE_MEMBERS + HIDDEN,  # not the auditor, who only reads
    "GET /api/v1/takedowns/": STUDENT + ADMINS,  # the world's request was made by the student
    "GET /api/v1/takedowns/{pk}/": STUDENT + ADMINS + HIDDEN,
    "POST /api/v1/takedowns/{pk}/review/": ADMINS,
    "GET /api/v1/announcements/": SITE_READERS,
    "POST /api/v1/announcements/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/announcements/{pk}/": SITE_READERS + HIDDEN,
    "PATCH /api/v1/announcements/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/announcements/{pk}/": SITE_TEACHERS + HIDDEN,
    # --- groups ---------------------------------------------------------------------------------------------
    "GET /api/v1/groups/": SITE_TEACHERS,
    "POST /api/v1/groups/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/groups/{pk}/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/groups/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/groups/{pk}/": SITE_TEACHERS + HIDDEN,
    "PUT /api/v1/groups/{pk}/sign-up/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/groups/{pk}/sign-up/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/groups/{pk}/join/": STUDENTS + HIDDEN,
    "POST /api/v1/groups/{pk}/leave/": STUDENTS + HIDDEN,
    "GET /api/v1/groupings/": SITE_TEACHERS,
    "POST /api/v1/groupings/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/groupings/{pk}/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/groupings/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/groupings/{pk}/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/sites/{pk}/allocate-groups/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/sites/{pk}/my-groups/": SITE_READERS + HIDDEN,
    # --- assignments, marking and the gradebook -------------------------------------------------------------
    "GET /api/v1/assignments/": SITE_READERS,
    "POST /api/v1/assignments/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/assignments/{pk}/": SITE_READERS + HIDDEN,
    "PATCH /api/v1/assignments/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/assignments/{pk}/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/assignments/{pk}/submit/": STUDENTS + HIDDEN,
    "GET /api/v1/assignments/{pk}/submissions/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/assignments/{pk}/release/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/assignments/{pk}/download-all/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/assignments/{pk}/marks-upload/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/assignments/{pk}/group-mark/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/assignments/{pk}/moderation-sample/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/submissions/{pk}/download/": OWNER + HIDDEN,
    "GET /api/v1/submissions/{pk}/history/": OWNER + HIDDEN,
    "GET /api/v1/submissions/{pk}/neighbours/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/submissions/{pk}/mark/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/submissions/{pk}/rubric-mark/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/submissions/{pk}/feedback-files/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/submissions/{pk}/second-mark/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/submissions/{pk}/agree/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/submission-files/{pk}/download/": OWNER + HIDDEN,
    "GET /api/v1/feedback-files/{pk}/": OWNER + HIDDEN,  # the student's once the mark is released
    "DELETE /api/v1/feedback-files/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/receipts/{code}/": OWNER + HIDDEN,
    "GET /api/v1/extensions/": SITE_TEACHERS,
    "POST /api/v1/extensions/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/extensions/{pk}/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/extensions/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/extensions/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/accommodations/": ADMINS,  # the reasons may be about health: never teaching staff
    "POST /api/v1/accommodations/": ADMINS,
    "GET /api/v1/accommodations/{pk}/": ADMINS,
    "PATCH /api/v1/accommodations/{pk}/": ADMINS,
    "DELETE /api/v1/accommodations/{pk}/": ADMINS,
    "GET /api/v1/rubrics/": SITE_TEACHERS,
    "POST /api/v1/rubrics/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/rubrics/{pk}/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/rubrics/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/rubrics/{pk}/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/rubrics/{pk}/copy/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/grade-categories/": SITE_READERS,
    "POST /api/v1/grade-categories/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/grade-categories/{pk}/": SITE_READERS + HIDDEN,
    "PATCH /api/v1/grade-categories/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/grade-categories/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/sites/{pk}/gradebook/": SITE_READERS + HIDDEN,  # a student sees their own row only
    "GET /api/v1/sites/{pk}/gradebook/export/": TEACHER_READERS + HIDDEN,
    "GET /api/v1/sites/{pk}/coursework/working/": SITE_READERS + HIDDEN,  # a student: their own only
    "POST /api/v1/sites/{pk}/coursework/send/": SITE_TEACHERS + HIDDEN,
    # --- quizzes ------------------------------------------------------------------------------------------
    "GET /api/v1/question-banks/": SITE_TEACHERS,
    "POST /api/v1/question-banks/": SITE_TEACHERS,
    "GET /api/v1/question-banks/{pk}/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/question-banks/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/question-banks/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/question-categories/": SITE_TEACHERS,
    "POST /api/v1/question-categories/": SITE_TEACHERS,
    "GET /api/v1/question-categories/{pk}/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/question-categories/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/question-categories/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/questions/": SITE_TEACHERS,
    "POST /api/v1/questions/": SITE_TEACHERS,
    "GET /api/v1/questions/export/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/questions/import/": SITE_TEACHERS,
    "GET /api/v1/questions/{pk}/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/questions/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/questions/{pk}/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/questions/{pk}/image/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/questions/{pk}/versions/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/question-versions/{pk}/image/": OWNER,  # the student has it in an attempt
    "GET /api/v1/quizzes/": SITE_READERS,
    "POST /api/v1/quizzes/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/quizzes/{pk}/": SITE_READERS + HIDDEN,
    "PATCH /api/v1/quizzes/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/quizzes/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/quizzes/{pk}/attempts/": SITE_READERS + HIDDEN,  # rows: see ROWS
    "GET /api/v1/quizzes/{pk}/marking-queue/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/quizzes/{pk}/release/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/quizzes/{pk}/start/": STUDENTS + HIDDEN,
    "GET /api/v1/quizzes/{pk}/statistics/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/quiz-slots/": SITE_TEACHERS,
    "POST /api/v1/quiz-slots/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/quiz-slots/{pk}/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/quiz-slots/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/quiz-slots/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/quiz-overrides/": SITE_TEACHERS,
    "POST /api/v1/quiz-overrides/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/quiz-overrides/{pk}/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/quiz-overrides/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/quiz-overrides/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/quiz-attempts/{pk}/": OWNER + HIDDEN,
    "GET /api/v1/quiz-attempts/{pk}/events/": SITE_TEACHERS + HIDDEN,
    "PUT /api/v1/quiz-attempts/{pk}/answers/{position}/": STUDENT + HIDDEN,  # only who started it
    "GET /api/v1/quiz-attempts/{pk}/answers/{position}/file/": OWNER + HIDDEN,
    "POST /api/v1/quiz-attempts/{pk}/answers/{position}/file/": STUDENT + HIDDEN,
    "POST /api/v1/quiz-attempts/{pk}/answers/{position}/mark/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/quiz-attempts/{pk}/next-page/": STUDENT + HIDDEN,
    "POST /api/v1/quiz-attempts/{pk}/release/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/quiz-attempts/{pk}/submit/": STUDENT + HIDDEN,
    # --- practical assessment -----------------------------------------------------------------------------
    "GET /api/v1/practical-assessors/": SITE_TEACHERS,
    "POST /api/v1/practical-assessors/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/practical-assessors/{pk}/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/practical-assessors/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/practical-assessors/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/practical-tasks/": SITE_READERS,
    "POST /api/v1/practical-tasks/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/practical-tasks/{pk}/": SITE_READERS + HIDDEN,
    "PATCH /api/v1/practical-tasks/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/practical-tasks/{pk}/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/practical-tasks/{pk}/observations/": LECTURER + HIDDEN,  # assessors: not administrators
    "POST /api/v1/practical-tasks/{pk}/release/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/practical-tasks/{pk}/students/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/practical-criteria/": SITE_TEACHERS,
    "POST /api/v1/practical-criteria/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/practical-criteria/{pk}/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/practical-criteria/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/practical-criteria/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/observations/": SITE_TEACHERS,  # the world's is not released to the student yet
    "GET /api/v1/observations/{pk}/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/observations/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/observations/{pk}/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/observations/{pk}/photos/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/observations/{pk}/release/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/observation-photos/{pk}/download/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/competency-frameworks/": SIGNED_IN,
    "POST /api/v1/competency-frameworks/import/": ADMINS,
    "GET /api/v1/competency-frameworks/{pk}/": SIGNED_IN,
    "GET /api/v1/site-frameworks/": SITE_READERS,
    "POST /api/v1/site-frameworks/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/site-frameworks/{pk}/": SITE_READERS + HIDDEN,
    "DELETE /api/v1/site-frameworks/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/competency-maps/": SITE_READERS,
    "POST /api/v1/competency-maps/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/competency-maps/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/competency-results/": OWNER,
    "POST /api/v1/competency-results/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/competency-results/{pk}/": OWNER + HIDDEN,
    "GET /api/v1/sites/{pk}/competency/": SITE_MEMBERS + HIDDEN,  # a student: their own row
    "GET /api/v1/logbook/": OWNER,
    "POST /api/v1/logbook/": STUDENTS + HIDDEN,
    "GET /api/v1/logbook/{pk}/": OWNER + HIDDEN,
    "PATCH /api/v1/logbook/{pk}/": STUDENT + HIDDEN,  # the student's own entry only
    "DELETE /api/v1/logbook/{pk}/": STUDENT + HIDDEN,
    "POST /api/v1/logbook/{pk}/photos/": STUDENT + HIDDEN,
    "POST /api/v1/logbook/{pk}/review/": LECTURER + HIDDEN,  # the supervising lecturer
    "GET /api/v1/logbook-photos/{pk}/download/": OWNER + HIDDEN,
    "GET /api/v1/sites/{pk}/logbook-totals/": SITE_MEMBERS + HIDDEN,  # a student: their own row
    "GET /api/v1/portfolio/": PEOPLE,  # one's own portfolio
    # --- forums and messages ------------------------------------------------------------------------------
    "GET /api/v1/forums/": SITE_READERS,
    "POST /api/v1/forums/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/forums/{pk}/": SITE_READERS + HIDDEN,
    "PATCH /api/v1/forums/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/forums/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/forums/{pk}/marks/": SITE_READERS + HIDDEN,  # a student: their own mark only
    "POST /api/v1/forums/{pk}/marks/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/forums/{pk}/release-marks/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/forums/{pk}/subscribe/": SITE_READERS + HIDDEN,  # one's own notices
    "POST /api/v1/forums/{pk}/unsubscribe/": SITE_READERS + HIDDEN,
    "GET /api/v1/forums/{pk}/threads/": SITE_READERS + HIDDEN,
    "POST /api/v1/forums/{pk}/threads/": SITE_MEMBERS + HIDDEN,
    "GET /api/v1/threads/{pk}/": SITE_READERS + HIDDEN,
    "POST /api/v1/threads/{pk}/lock/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/threads/{pk}/pin/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/threads/{pk}/replies/": SITE_MEMBERS + HIDDEN,
    "POST /api/v1/threads/{pk}/subscribe/": SITE_READERS + HIDDEN,
    "POST /api/v1/threads/{pk}/unsubscribe/": SITE_READERS + HIDDEN,
    "PATCH /api/v1/posts/{pk}/": STUDENT + HIDDEN,  # the world's post is the student's
    "POST /api/v1/posts/{pk}/remove/": OWNER + HIDDEN,
    "POST /api/v1/posts/{pk}/report/": SITE_MEMBERS + HIDDEN,  # not the auditor, who only reads
    "GET /api/v1/post-reports/": SITE_TEACHERS + CLASSMATE,  # the classmate made the world's report
    "GET /api/v1/post-reports/{pk}/": SITE_TEACHERS + CLASSMATE + HIDDEN,
    "POST /api/v1/post-reports/{pk}/review/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/conduct-statements/": SIGNED_IN,
    "POST /api/v1/conduct-statements/": ADMINS,
    "GET /api/v1/conduct-statements/current/": SIGNED_IN,
    "POST /api/v1/conduct-statements/current/accept/": SIGNED_IN,
    "PATCH /api/v1/conduct-statements/{pk}/": ADMINS,
    "POST /api/v1/conduct-statements/{pk}/publish/": ADMINS,
    "GET /api/v1/conversations/": PARTICIPANTS,
    "POST /api/v1/conversations/": SITE_MEMBERS + HIDDEN,
    "GET /api/v1/conversations/recipients/": SITE_READERS + HIDDEN,
    "GET /api/v1/conversations/{pk}/": PARTICIPANTS + HIDDEN,
    "POST /api/v1/conversations/{pk}/messages/": PARTICIPANTS + HIDDEN,
    "POST /api/v1/conversations/{pk}/read/": PARTICIPANTS + HIDDEN,
    # --- attendance -----------------------------------------------------------------------------------------
    "GET /api/v1/class-sessions/": SITE_READERS,
    "POST /api/v1/class-sessions/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/class-sessions/{pk}/": SITE_READERS + HIDDEN,
    "PATCH /api/v1/class-sessions/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/class-sessions/{pk}/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/class-sessions/{pk}/check-in/": STUDENTS + HIDDEN,
    "GET /api/v1/class-sessions/{pk}/check-in-code/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/class-sessions/{pk}/close-register/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/class-sessions/{pk}/register/": TEACHER_READERS + HIDDEN,
    "POST /api/v1/class-sessions/{pk}/register/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/attendance/sites/{pk}/totals/": SITE_READERS + HIDDEN,  # a student: their own
    "GET /api/v1/attendance/sites/{pk}/policy/": TEACHER_READERS + HIDDEN,
    "PUT /api/v1/attendance/sites/{pk}/policy/": ADMINS + HIDDEN,
    "POST /api/v1/attendance/sites/{pk}/send-to-srms/": SITE_TEACHERS + HIDDEN,
    # --- staff development and certificates ---------------------------------------------------------------
    "GET /api/v1/staff-development/catalogue/": STAFF + OVERSEERS,
    "GET /api/v1/staff-development/catalogue/{site}/": STAFF + OVERSEERS,
    "PUT /api/v1/staff-development/catalogue/{site}/entry/": ADMINS,
    "POST /api/v1/staff-development/catalogue/{site}/join/": STAFF,
    "GET /api/v1/staff-development/catalogue/{site}/progress/": PEOPLE + HIDDEN,  # one's own progress
    "POST /api/v1/staff-development/catalogue/{site}/record-completion/": ADMINS,
    "GET /api/v1/staff-development/requests/": TEACHER_READERS,  # the world's request is the lecturer's
    "GET /api/v1/staff-development/requests/{pk}/": TEACHER_READERS + HIDDEN,
    "POST /api/v1/staff-development/requests/{pk}/approve/": COURSE_ADMIN + HIDDEN,  # names no supervisor
    "POST /api/v1/staff-development/requests/{pk}/reject/": COURSE_ADMIN + HIDDEN,
    "POST /api/v1/staff-development/requests/{pk}/withdraw/": LECTURER + HIDDEN,  # who asked
    "GET /api/v1/staff-development/paths/": STAFF + OVERSEERS,
    "POST /api/v1/staff-development/paths/": ADMINS,
    "GET /api/v1/staff-development/paths/{pk}/": STAFF + OVERSEERS,
    "PATCH /api/v1/staff-development/paths/{pk}/": ADMINS,
    "POST /api/v1/staff-development/paths/{pk}/join/": STAFF,
    "GET /api/v1/staff-development/paths/{pk}/progress/": STAFF + HIDDEN,
    "GET /api/v1/staff-development/required/": OVERSEERS,
    "POST /api/v1/staff-development/required/": ADMINS,
    "GET /api/v1/staff-development/required/mine/": SIGNED_IN,
    "GET /api/v1/staff-development/required/overdue/": OVERSEERS,
    "GET /api/v1/staff-development/required/{pk}/": OVERSEERS,
    "PATCH /api/v1/staff-development/required/{pk}/": ADMINS,
    "POST /api/v1/staff-development/required/{pk}/assign/": ADMINS,
    "GET /api/v1/certificates/": STUDENT + OVERSEERS,  # the world's certificate is the student's
    "GET /api/v1/certificates/{pk}/": STUDENT + OVERSEERS + HIDDEN,
    "GET /api/v1/certificates/{pk}/download/": STUDENT + OVERSEERS + HIDDEN,
    "POST /api/v1/certificates/{pk}/withdraw/": COURSE_ADMIN,
    "GET /api/v1/certificate-templates/": OVERSEERS,
    "POST /api/v1/certificate-templates/": ADMINS,
    "GET /api/v1/certificate-templates/{pk}/": OVERSEERS,
    "POST /api/v1/certificate-templates/{pk}/new-version/": ADMINS,
    "POST /api/v1/certificates/check/": PUBLIC,  # anyone checks a certificate they were shown
    "GET /api/check-certificate/": PUBLIC,
    "POST /api/check-certificate/": PUBLIC,
    # --- records, privacy and operations ------------------------------------------------------------------
    "GET /api/v1/audit/": AUDIT_LOG,
    "GET /api/v1/audit/{pk}/": AUDIT_LOG,
    "GET /api/v1/audit/choices/": AUDIT_LOG,
    "GET /api/v1/audit/export/": AUDIT_LOG,
    "GET /api/v1/audit/chain/": AUDIT_LOG,
    "POST /api/v1/audit/chain/": AUDIT_LOG,  # checking the chain records the check; it changes nothing
    "GET /api/v1/integration-runs/": OVERSEERS,
    "GET /api/v1/integration-runs/{pk}/": OVERSEERS,
    # --- the term calendar and archived sites (item 7.12) ---------------------------------------------------
    "GET /api/v1/terms/": OVERSEERS,
    "POST /api/v1/terms/": ADMINS,
    "GET /api/v1/terms/missing/": OVERSEERS,
    "GET /api/v1/terms/{pk}/": OVERSEERS,
    "PATCH /api/v1/terms/{pk}/": ADMINS,
    "DELETE /api/v1/terms/{pk}/": ADMINS,
    "GET /api/v1/terms/{pk}/sites/": OVERSEERS,
    "GET /api/v1/site-archives/{pk}/download/": OVERSEERS,
    "GET /api/v1/privacy/notice/": SIGNED_IN,
    "POST /api/v1/privacy/notice/acknowledge/": SIGNED_IN,
    "GET /api/v1/privacy/my-record/": SIGNED_IN,
    "GET /api/v1/privacy/my-record/download/": SIGNED_IN,
    "GET /api/v1/privacy/people/{pk}/record/": PRIVACY_OFFICERS,
    "GET /api/v1/privacy/notices/": PRIVACY_READERS,
    "POST /api/v1/privacy/notices/": PRIVACY_OFFICERS,
    "PATCH /api/v1/privacy/notices/{pk}/": PRIVACY_OFFICERS,
    "POST /api/v1/privacy/notices/{pk}/publish/": PRIVACY_OFFICERS,
    "GET /api/v1/privacy/corrections/": STUDENT + OVERSEERS + DPO,  # the world's request is the student's
    "POST /api/v1/privacy/corrections/": SIGNED_IN,  # about one's own record
    "POST /api/v1/privacy/corrections/{pk}/decide/": ADMINS,
    "GET /api/v1/privacy/retention-rules/": PRIVACY_READERS,
    "PATCH /api/v1/privacy/retention-rules/{pk}/": PRIVACY_OFFICERS,
    "POST /api/v1/privacy/retention-rules/{pk}/confirm/": PRIVACY_OFFICERS,
    "POST /api/v1/privacy/retention-rules/{pk}/find/": PRIVACY_OFFICERS,
    "GET /api/v1/privacy/disposal-runs/": PRIVACY_READERS,
    "GET /api/v1/privacy/disposal-runs/{pk}/": PRIVACY_READERS,
    "POST /api/v1/privacy/disposal-runs/{pk}/approve/": PRIVACY_OFFICERS,
    "POST /api/v1/privacy/disposal-runs/{pk}/cancel/": PRIVACY_OFFICERS,
    "POST /api/v1/privacy/disposal-runs/{pk}/keep/": PRIVACY_OFFICERS,
    "GET /api/v1/privacy/breaches/": PRIVACY_READERS,
    "POST /api/v1/privacy/breaches/": PRIVACY_OFFICERS,
    "GET /api/v1/privacy/breaches/{pk}/": PRIVACY_READERS,
    "PATCH /api/v1/privacy/breaches/{pk}/": PRIVACY_OFFICERS,
    "POST /api/v1/privacy/breaches/{pk}/close/": PRIVACY_OFFICERS,
    # --- push notices and offline modules (items 4.04, 4.05) ----------------------------------------------
    "GET /api/v1/notifications/push/": SIGNED_IN,
    "POST /api/v1/notifications/push/subscribe/": SIGNED_IN,  # one's own devices (409 while push is off)
    "POST /api/v1/notifications/push/unsubscribe/": SIGNED_IN,
    "GET /api/v1/offline/modules/{pk}/": SITE_READERS + HIDDEN,
    # --- lecture video and captions (items 4.06, 4.07) ----------------------------------------------------
    "POST /api/v1/videos/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/videos/{item}/": SITE_READERS + HIDDEN,
    "GET /api/v1/videos/{item}/play/{quality}/": SITE_READERS + HIDDEN,
    "GET /api/v1/videos/{item}/poster/": SITE_READERS + HIDDEN,
    "POST /api/v1/videos/{item}/convert/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/videos/{item}/transcribe/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/videos/{item}/captions/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/videos/{item}/captions/{language}/": SITE_READERS + HIDDEN,
    "DELETE /api/v1/videos/{item}/captions/{language}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/videos/{item}/captions/{language}/cues/": SITE_READERS + HIDDEN,
    "PUT /api/v1/videos/{item}/captions/{language}/cues/": SITE_TEACHERS + HIDDEN,
    # --- packaged content: SCORM and H5P, the statement store (items 5.12, 5.13, 6.09) -------------------
    "GET /api/v1/packages/": SITE_READERS,
    "POST /api/v1/packages/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/packages/{pk}/": SITE_READERS + HIDDEN,
    "PATCH /api/v1/packages/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/packages/{pk}/attempts/": SITE_READERS + HIDDEN,  # rows: see ROWS
    "POST /api/v1/packages/{pk}/launch/": SITE_MEMBERS + HIDDEN,  # teaching staff in preview; not the auditor
    "POST /api/v1/package-attempts/{pk}/commit/": OWN + HIDDEN,  # as the learner whose attempt it is
    "GET /api/v1/xapi/statements/": STAFF + ADMINS,  # the statements of the courses one teaches
    "POST /api/v1/xapi/statements/": SIGNED_IN,  # only into one's own attempt, named by its registration
    # The player's files, by a signed address valid for a few hours: the address is the credential.
    "GET /api/play/{token}/": PUBLIC,
    "GET /api/play/{token}/{entry}": PUBLIC,
    # --- the shared content library (item 5.14) -----------------------------------------------------------
    # For anyone who teaches, and the course administrators; the auditor reads it (item 1.02); not students
    # or the DPO.
    "GET /api/v1/library/items/": STAFF + ADMINS + AUDITOR,
    "POST /api/v1/library/items/": STAFF + ADMINS,  # to the whole School's shelf: anyone who teaches
    "GET /api/v1/library/items/{pk}/": STAFF + ADMINS + AUDITOR,
    "PATCH /api/v1/library/items/{pk}/": ADMINS,  # the world's was added by the course administrator
    "DELETE /api/v1/library/items/{pk}/": ADMINS,
    "GET /api/v1/library/items/{pk}/download/": STAFF + ADMINS + AUDITOR,
    "POST /api/v1/library/items/{pk}/use/": SITE_TEACHERS + HIDDEN,  # into a module of a course one teaches
    "POST /api/v1/library/items/share/": SITE_TEACHERS + HIDDEN,  # an item of a course one teaches
    "GET /api/v1/library/banks/": STAFF + ADMINS + AUDITOR,
    "POST /api/v1/library/banks/share/": SITE_TEACHERS + HIDDEN,  # a bank of a course one teaches
    # --- course interchange (item 6.08) -------------------------------------------------------------------
    "GET /api/v1/sites/{pk}/export-cartridge/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/sites/{pk}/import-content/": SITE_TEACHERS + HIDDEN,
    # --- Open Badges (item 5.10) ----------------------------------------------------------------------------
    "GET /api/v1/certificates/{pk}/badge/": STUDENT + OVERSEERS + HIDDEN,  # as the certificate itself
    "POST /api/v1/certificates/check-badge/": PUBLIC,  # anyone checks a badge they were shown
    "GET /api/badges/issuer.json": PUBLIC,
    "GET /api/badges/jwks.json": PUBLIC,
    # --- help requests (item 7.17) ------------------------------------------------------------------------
    "GET /api/v1/help-requests/": OWN + ADMINS,  # the world's request is the student's
    "POST /api/v1/help-requests/": SIGNED_IN,
    "GET /api/v1/help-requests/{pk}/": OWN + ADMINS + HIDDEN,
    "POST /api/v1/help-requests/{pk}/answer/": ADMINS,
    # --- insights: analytics, progress, outcomes, alerts, reports (items 3.11, 6.01 to 6.06) ---------------
    "GET /api/v1/sites/{pk}/insights/": TEACHER_READERS + HIDDEN,  # the auditor reads (item 1.02)
    "GET /api/v1/sites/{pk}/progress/": TEACHER_READERS + HIDDEN,
    "GET /api/v1/sites/{pk}/progress/{person_id}/": TEACHER_READERS + HIDDEN,
    "GET /api/v1/sites/{pk}/my-progress/": STUDENTS + HIDDEN,  # from released marks, their own only
    "GET /api/v1/sites/{pk}/outcomes/": TEACHER_READERS + HIDDEN,
    "POST /api/v1/sites/{pk}/outcomes/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/sites/{pk}/outcomes/{outcome_id}/links/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/sites/{pk}/outcome-standings/": TEACHER_READERS + HIDDEN,
    "GET /api/v1/sites/{pk}/outcome-evidence/": TEACHER_READERS + HIDDEN,
    "PATCH /api/v1/outcomes/{outcome_id}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/outcomes/{outcome_id}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/outcome-links/{link_id}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/sites/{pk}/alerts/": SITE_TEACHERS + HIDDEN,  # never a student, nor the auditor (asvs-l2.md)
    "POST /api/v1/alerts/{alert_id}/acknowledge/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/alerts/{alert_id}/act/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/alerts/{alert_id}/dismiss/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/alert-rules/": STAFF + ADMINS + AUDITOR,  # anyone who teaches somewhere, and the auditor
    "PATCH /api/v1/alert-rules/{rule_id}/": ADMINS,
    # The reports also answer a registrar and a head of department within their grants (insights.reports);
    # those two roles are not among this table's nine.
    "GET /api/v1/reports/courses/": OVERSEERS,
    "GET /api/v1/reports/courses/export/": OVERSEERS,
    "GET /api/v1/reports/staff-development/": OVERSEERS,
    "GET /api/v1/reports/staff-development/export/": OVERSEERS,
    # --- outside tools, LTI 1.3 (item 6.07) ---------------------------------------------------------------
    "GET /api/v1/lti/platform/": ADMINS,
    "GET /api/v1/tools/": STAFF + ADMINS,  # active tools, for anyone who teaches somewhere
    "POST /api/v1/tools/": ADMINS,
    "GET /api/v1/tools/{pk}/": STAFF + ADMINS + HIDDEN,
    "PATCH /api/v1/tools/{pk}/": ADMINS,
    "DELETE /api/v1/tools/{pk}/": ADMINS,  # refused while placed (409), as the world's is
    "POST /api/v1/tool-placements/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/tool-placements/{pk}/": SITE_TEACHERS + HIDDEN,
    "PATCH /api/v1/tool-line-items/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/sites/{pk}/tools/": SITE_READERS + HIDDEN,
    # Opening a tool needs a person record (the tool is told who it is): administrators have none here.
    "GET /api/lti/launch/{item_id}/": STUDENTS + LECTURER,
    "GET /api/lti/choose/": LECTURER + HIDDEN,
    # What a tool calls. Its credentials are in the message itself (the launch begun by the LMS, a JWT the
    # tool signed, a client assertion): open to anyone, refused unless those check out (lti/tests.py).
    "GET /api/lti/jwks/": PUBLIC,
    "GET /api/lti/auth/": PUBLIC,
    "POST /api/lti/auth/": PUBLIC,
    "POST /api/lti/deep-links/": PUBLIC,
    "POST /api/lti/token/": PUBLIC,
    # The tool's services take only the bearer token from /api/lti/token/: a person's session is ignored.
    "GET /api/lti/sites/{site_id}/line-items/": SERVICE_KEY,
    "POST /api/lti/sites/{site_id}/line-items/": SERVICE_KEY,
    "GET /api/lti/sites/{site_id}/line-items/{line_item_id}/": SERVICE_KEY,
    "PUT /api/lti/sites/{site_id}/line-items/{line_item_id}/": SERVICE_KEY,
    "DELETE /api/lti/sites/{site_id}/line-items/{line_item_id}/": SERVICE_KEY,
    "POST /api/lti/sites/{site_id}/line-items/{line_item_id}/scores/": SERVICE_KEY,
    "GET /api/lti/sites/{site_id}/line-items/{line_item_id}/results/": SERVICE_KEY,
    "GET /api/lti/sites/{site_id}/members/": SERVICE_KEY,
    # --- AI help (item 7.18; switched on for this module) -------------------------------------------------
    "GET /api/v1/sites/{pk}/ai/": SITE_READERS + HIDDEN,
    "PATCH /api/v1/sites/{pk}/ai/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/sites/{pk}/ai/drafts/questions/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/sites/{pk}/ai/drafts/rubric/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/sites/{pk}/ai/drafts/alt-text/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/sites/{pk}/ai/ask/": SITE_READERS + HIDDEN,  # the study helper
    "POST /api/v1/ai/drafts/{pk}/saved/": LECTURER + HIDDEN,  # whoever asked for the draft
    # --- similarity, peer review, paper quizzes and open short courses (3.20, 3.24, 4.13, 5.07) ----------
    "GET /api/v1/submissions/{pk}/similarity/": SITE_TEACHERS + HIDDEN,  # never the student
    "POST /api/v1/submissions/{pk}/similarity/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/assignments/{pk}/similarity/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/assignments/{pk}/peer-review/": SITE_MEMBERS + HIDDEN,  # staff overview, or own reviews
    "PUT /api/v1/assignments/{pk}/peer-review/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/assignments/{pk}/peer-review/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/assignments/{pk}/peer-review/allocate/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/assignments/{pk}/peer-review/release/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/assignments/{pk}/peer-review/apply/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/peer-reviews/{pk}/": CLASSMATE + HIDDEN,  # the reviewer only: the world's is the classmate
    "POST /api/v1/peer-reviews/{pk}/": CLASSMATE + HIDDEN,
    "GET /api/v1/peer-reviews/{pk}/files/{file_id}/": CLASSMATE + HIDDEN,
    "POST /api/v1/peer-reviews/{pk}/moderate/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/submissions/{pk}/peer-mark/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/quizzes/{pk}/papers/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/quizzes/{pk}/papers/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/quiz-papers/{pk}/": SITE_TEACHERS + HIDDEN,
    "DELETE /api/v1/quiz-papers/{pk}/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/quiz-papers/{pk}/pdf/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/quiz-papers/{pk}/grid/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/quiz-papers/{pk}/grid/": SITE_TEACHERS + HIDDEN,
    "POST /api/v1/quiz-papers/{pk}/upload/": SITE_TEACHERS + HIDDEN,
    "GET /api/v1/open-courses/": PUBLIC,  # the public catalogue, when OPEN_COURSES_ENABLED is on
    "POST /api/v1/open-courses/register/": PUBLIC,
    "GET /api/v1/open-courses/confirm/": PUBLIC,
    "POST /api/v1/open-courses/confirm/": PUBLIC,
    "POST /api/v1/open-courses/{pk}/join/": PEOPLE,  # a person record is needed to join
}

# The world record each {pk} names, by the path segment before it.
SEGMENT_OBJECTS = {
    "packages": "package",
    "package-attempts": "package_attempt",
    "items": "library_item",
    "help-requests": "help_request",
    "tools": "tool",
    "tool-placements": "placement",
    "tool-line-items": "line_item",
    "drafts": "exchange",
    "alert-rules": "alert_rule",
    "accommodations": "accommodation",
    "announcements": "announcement",
    "assignments": "assignment",
    "audit": "audit_row",
    "breaches": "breach",
    "catalogue": "sd_site",
    "certificate-templates": "certificate_template",
    "certificates": "certificate",
    "class-sessions": "class_session",
    "competency-frameworks": "framework",
    "competency-maps": "competency_map",
    "competency-results": "competency_result",
    "conduct-statements": "conduct_statement",
    "content": "item",
    "conversations": "conversation",
    "corrections": "correction",
    "delegations": "delegation",
    "disposal-runs": "disposal_run",
    "extensions": "extension",
    "feedback-files": "feedback_file",
    "forums": "forum",
    "grade-categories": "grade_category",
    "groupings": "grouping",
    "groups": "group",
    "integration-runs": "integration_run",
    "logbook": "logbook_entry",
    "logbook-photos": "logbook_photo",
    "modules": "module",
    "notices": "notice",
    "notifications": "notification",
    "observation-photos": "observation_photo",
    "observations": "observation",
    "paths": "path",
    "people": "student_person",
    "post-reports": "post_report",
    "posts": "post",
    "practical-assessors": "assessor",
    "practical-criteria": "criterion",
    "practical-tasks": "task",
    "question-banks": "bank",
    "question-categories": "question_category",
    "question-versions": "question_version",
    "questions": "question",
    "quiz-attempts": "attempt",
    "quiz-overrides": "quiz_override",
    "quiz-slots": "quiz_slot",
    "quizzes": "quiz",
    "receipts": "receipt",
    "requests": "enrolment_request",
    "required": "required_training",
    "retention-rules": "retention_rule",
    "rubrics": "rubric",
    "sessions": "user_session",
    "site-frameworks": "site_framework",
    "site-templates": "site_template",
    "sites": "site",
    "submission-files": "submission_file",
    "submissions": "submission",
    "takedowns": "takedown",
    "terms": "term",
    "site-archives": "site_archive",
    "peer-reviews": "peer_review",
    "quiz-papers": "quiz_paper",
    "open-courses": "open_site",
    "threads": "thread",
}
# A {name} that says what it is, whatever segment precedes it.
NAMED_OBJECTS = {
    "play:token": "play_token",  # a {name} after a given segment, before the name alone
    "entry": "play_entry",
    "item": "video_item",
    "site": "sd_site",
    "code": "receipt",
    "token": "feed_token",
    "person_id": "student_person",
    "outcome_id": "outcome",
    "link_id": "outcome_link",
    "alert_id": "alert",
    "rule_id": "alert_rule",
    "item_id": "placed_item",
    "site_id": "site",
    "line_item_id": "line_item",
    "file_id": "submission_file",
}


class Literal:
    """A value sent as it is, not looked up in the world."""

    def __init__(self, value):
        self.value = value


# Query strings for the routes that need one; {name} is a world record.
QUERY: dict[str, str] = {
    "GET /api/lti/choose/": "?tool={tool}&module={module}",
    "GET /api/v1/questions/export/": "?bank={bank}",
    "GET /api/v1/conversations/recipients/": "?site={site}",
    "GET /api/v1/search/": "?q=soil",
    "GET /api/v1/sites/{pk}/coursework/working/": "?person={student_person}",  # for teaching staff
    "POST /api/v1/approvals/delegations/{pk}/end/": "?person={lecturer_person}",  # for course administrators
}

# Writes send an empty body unless named here: field -> world record, a list of them, or Literal(value).
# A write that names its site or parent in the body is refused for that site: the body names the world's.
BODY: dict[str, dict] = {
    "POST /api/v1/question-banks/": {"site": "site", "name": Literal("Field questions")},
    "POST /api/v1/question-categories/": {"bank": "bank", "name": Literal("Roots")},
    "POST /api/v1/questions/": {
        "bank": "bank",
        "category": "question_category",
        "qtype": Literal("essay"),
        "name": Literal("Roots"),
        "text": Literal("Describe a root."),
    },
    "POST /api/v1/questions/import/": {
        "bank": "bank",
        "format": Literal("gift"),
        "content": Literal("Q {=A}"),
    },
    "POST /api/v1/quizzes/": {"site": "site", "title": Literal("Roots quiz")},
    "POST /api/v1/quiz-slots/": {"quiz": "quiz", "question": "question"},
    "POST /api/v1/quiz-overrides/": {"quiz": "quiz", "student": "classmate_person"},
    "POST /api/v1/conversations/": {
        "site": "site",
        "subject": Literal("Field trip"),
        "body": Literal("When?"),
    },
    "POST /api/v1/approvals/delegations/": {
        "delegate": "elsewhere_person",
        "starts": Literal(str(date.today() + timedelta(days=30))),
        "ends": Literal(str(date.today() + timedelta(days=31))),
    },
    "POST /api/v1/assignments/": {"site": "site"},
    "POST /api/v1/grade-categories/": {"site": "site"},
    "POST /api/v1/extensions/": {"assignment": "assignment", "student": "student_person"},
    "POST /api/v1/accommodations/": {"person": "student_person"},
    "POST /api/v1/practical-assessors/": {"site": "site"},
    "POST /api/v1/practical-tasks/": {"site": "site"},
    "POST /api/v1/practical-criteria/": {"task": "task"},
    "POST /api/v1/site-frameworks/": {"site": "site", "framework": "framework"},
    "POST /api/v1/competency-maps/": {"site": "site", "assignment": "assignment"},
    "POST /api/v1/competency-results/": {"site": "site", "student": "student_person"},
    "POST /api/v1/logbook/": {"site": "site"},
    "POST /api/v1/groupings/": {"site": "site"},
    "POST /api/v1/rubrics/": {"site": "site"},
    "POST /api/v1/rubrics/{pk}/copy/": {"site": "site"},
    "POST /api/v1/sites/{pk}/copy-from/": {"source": "site"},
    "POST /api/v1/modules/": {"site": "site"},
    "POST /api/v1/content/": {"module": "module"},
    "POST /api/v1/content/{pk}/move/": {"module": "module"},
    "POST /api/v1/announcements/": {"site": "site"},
    "POST /api/v1/groups/": {"site": "site"},
    "POST /api/v1/forums/": {"site": "site"},
    "POST /api/v1/class-sessions/": {"site": "site"},
    "POST /api/v1/staff-development/paths/": {
        "code": Literal("field-skills"),
        "title": Literal("Field skills"),
        "sites": ["sd_site"],
    },
    "POST /api/v1/staff-development/required/": {"site": "sd_site"},
    "POST /api/v1/tool-placements/": {"module": "module", "tool": "tool", "title": Literal("Soil game")},
    "POST /api/v1/videos/": {
        "module": "module",
        "title": Literal("Lecture 2"),
        "licence": Literal("gsa_own"),
    },
    "POST /api/v1/packages/": {"module": "module", "licence": Literal("gsa_own")},
    "POST /api/v1/library/items/{pk}/use/": {"module": "module"},
    "POST /api/v1/library/items/share/": {"item": "item"},
    "POST /api/v1/library/banks/share/": {"bank": "bank"},
}

# Writes sent as a form, not JSON (what a tool sends; an upload), so that they reach their own checks.
FORM = {
    "POST /api/lti/deep-links/",
    "POST /api/lti/token/",
    "POST /api/v1/videos/",
    "POST /api/v1/packages/",
    "POST /api/v1/sites/{pk}/import-content/",
}

# Lists inside a record that show some of their rows only to some roles: the world record that must not be
# listed to a role outside the Access, although that role may open the list.
ROWS: dict[str, tuple[str, Access]] = {
    "GET /api/v1/quizzes/{pk}/attempts/": ("attempt", OWNER),
    "GET /api/v1/packages/{pk}/attempts/": ("package_attempt", OWNER),
}

# A list whose rows name the world record by another field than "id".
LIST_FIELD = {"GET /api/v1/staff-development/catalogue/": "site"}

# Plain Django views (not the REST framework's) declare no methods the resolver can read: list them here.
PLAIN_VIEW_METHODS = {
    "/api/play/{token}/": ("get",),
    "/api/play/{token}/{entry}": ("get",),
    "/api/badges/issuer.json": ("get",),
    "/api/badges/jwks.json": ("get",),
    "/api/health/": ("get",),
    "/api/metrics": ("get",),
    "/api/check-certificate/": ("get", "post"),
}

DENIED = {401, 403}


def readable(route: str) -> str:
    """'api/v1/^assignments/(?P<pk>[^/.]+)/$' -> '/api/v1/assignments/{pk}/'."""
    route = route.replace("^", "").replace("$", "")
    while (start := route.find("(?P<")) >= 0:  # a named group, which may hold groups of its own
        name = route[start + 4 : route.index(">", start)]
        depth, end = 0, start
        for end in range(start, len(route)):
            depth += {"(": 1, ")": -1}.get(route[end], 0) if route[end - 1] != "\\" else 0
            if depth == 0:
                break
        route = f"{route[:start]}{{{name}}}{route[end + 1 :]}"
    route = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", route)
    return "/" + route.replace("\\.", ".")


def _methods(pattern: URLPattern, key: str) -> list[str]:
    callback = pattern.callback
    cls = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
    if cls is None:
        return list(PLAIN_VIEW_METHODS.get(key, ("?",)))
    allowed = {m for m in cls.http_method_names if m not in ("options", "head")}
    actions = getattr(callback, "actions", None)
    if actions:  # a router's route: the actions it maps that the view set does not switch off
        return sorted(m for m in actions if m in allowed)
    return sorted(m for m in allowed if hasattr(cls, m))


def discover() -> dict[str, list[str]]:
    """Every route of the API with its methods, in the order the resolver tries them."""
    found: dict[str, list[str]] = {}

    def walk(resolver, prefix):
        for entry in resolver.url_patterns:
            route = prefix + str(entry.pattern)
            if isinstance(entry, URLResolver):
                if route.startswith("admin/"):
                    continue  # Django admin: locked separately (iam.admin_site)
                walk(entry, route)
            elif "(?P<format>" not in route and "<drf_format_suffix:format>" not in route:
                key = readable(route)
                found.setdefault(key, _methods(entry, key))  # the first match wins, as in resolution

    walk(get_resolver(), "")
    return found


ROUTES = discover()
PAIRS = [f"{method.upper()} {route}" for route, methods in ROUTES.items() for method in methods]


# --- the world --------------------------------------------------------------------------------------------


def _user(username, *roles):
    from iam.models import Role, RoleScope

    user = get_user_model().objects.create_user(username=username)  # no password: hashing one is slow
    for code in roles:
        RoleScope.objects.create(user=user, role=Role.objects.get(code=code))
    return user


def _person(kind, external_id, first, last, *roles):
    from people.models import PersonRef

    return PersonRef.objects.create(
        kind=kind,
        external_id=external_id,
        first_name=first,
        last_name=last,
        campus_code="MRP",
        user=_user(external_id, *roles),
    )


def build_world() -> dict:
    """One record of every kind the routes name, on the site or around it."""
    from django.core.management import call_command

    from approvals.models import Delegation
    from assessments.models import (
        Accommodation,
        Assignment,
        Extension,
        FeedbackFile,
        GradeCategory,
        Mark,
        Submission,
        SubmissionAttempt,
        SubmissionFile,
    )
    from attendance.models import AttendancePolicy, ClassSession
    from audit.models import AuditLog
    from calendars.models import CalendarFeed
    from certificates.checking import new_code
    from certificates.models import Certificate, CertificateTemplate
    from courses.models import (
        Announcement,
        Completion,
        ContentItem,
        CourseSite,
        Grouping,
        GroupSignUp,
        Membership,
        Module,
        SiteGroup,
        SiteTemplate,
        TakedownRequest,
    )
    from forums.models import ConductAcceptance, ConductStatement, Forum, Post, PostReport, Thread
    from iam.models import UserSession
    from integration.models import IntegrationRun
    from messaging.models import Conversation, Message, Participant
    from notifications.models import Notification
    from practicals.models import (
        AssignmentCompetencyMap,
        CompetencyResult,
        LogbookEntry,
        LogbookPhoto,
        Observation,
        ObservationPhoto,
        PerformanceCriterion,
        PracticalAssessor,
        PracticalCriterion,
        PracticalTask,
        SiteFramework,
    )
    from practicals.serializers import FrameworkImportSerializer
    from privacy.models import Breach, CorrectionRequest, DisposalRun, PrivacyNotice, RetentionRule
    from quizzes.models import (
        Attempt,
        AttemptAnswer,
        Question,
        QuestionBank,
        QuestionCategory,
        QuestionVersion,
        Quiz,
        QuizOverride,
        QuizSlot,
    )
    from quizzes.schemas import validate_question
    from rubrics.models import Rubric, RubricCriterion, RubricLevel
    from staffdev.models import CatalogueEntry, EnrolmentRequest, LearningPath, PathStep, RequiredTraining

    call_command("seed", "--country", "GY", verbosity=0)
    now = timezone.now()
    today = timezone.localdate()

    student = _person("student", "26MRP0001", "Ravi", "Singh", "student")
    classmate = _person("student", "26MRP0002", "Devi", "Ramnarine", "student")
    lecturer = _person("staff", "E0001", "Asha", "Persaud", "lecturer")
    elsewhere = _person("staff", "E0002", "Kofi", "Adams", "lecturer")
    users = {
        "student": student.user,
        "classmate": classmate.user,
        "lecturer": lecturer.user,
        "elsewhere": elsewhere.user,
        "course_admin": _user("course.admin", "course_admin"),
        "administrator": _user("administrator", "administrator"),
        "auditor": _user("auditor", "auditor"),
        "dpo": _user("dpo", "dpo"),
    }

    site = CourseSite.objects.create(
        code="AGR101-2026-27-S1-MRP",
        title="AGR101 Introduction to Crop Science",
        term_code="2026-27-S1",
        campus_code="MRP",
        source="srms",
        is_published=True,
    )
    other_site = CourseSite.objects.create(
        code="AGR202-2026-27-S1-ESQ", title="AGR202 Soils", term_code="2026-27-S1", is_published=True
    )
    Membership.objects.create(site=site, person=lecturer, role="lecturer")
    Membership.objects.create(site=site, person=student, role="student")
    Membership.objects.create(site=site, person=classmate, role="student")
    Membership.objects.create(site=other_site, person=elsewhere, role="lecturer")

    # Course content.
    module = Module.objects.create(site=site, title="Week 1")
    item = ContentItem.objects.create(
        module=module, title="Notes", kind="file", file=ContentFile(b"%PDF-1.4 notes", name="notes.pdf")
    )
    takedown = TakedownRequest.objects.create(item=item, reason="Copyright", reported_by=student.user)
    announcement = Announcement.objects.create(site=site, title="Welcome", body="Hello", author=lecturer)
    group = SiteGroup.objects.create(site=site, name="Group A")
    GroupSignUp.objects.create(group=group)  # open: students join and leave it themselves
    group.members.add(Membership.objects.get(site=site, person=student))
    grouping = Grouping.objects.create(site=site, name="Field teams")
    site_template = SiteTemplate.objects.create(name="Weekly")

    # Coursework.
    rubric = Rubric.objects.create(title="Report rubric", site=site)
    rubric_criterion = RubricCriterion.objects.create(rubric=rubric, title="Method")
    RubricLevel.objects.create(criterion=rubric_criterion, description="Clear", points=5)
    category = GradeCategory.objects.create(site=site, name="Coursework", weight=40)
    assignment = Assignment.objects.create(
        site=site, title="Soil report", due_at=now + timedelta(days=7), max_mark=50, is_published=True
    )
    submission = Submission.objects.create(
        assignment=assignment,
        student=student,
        text="My report",
        file=ContentFile(b"%PDF-1.4 report", name="report.pdf"),
        original_name="report.pdf",
        submitted_at=now,
    )
    attempt_in = SubmissionAttempt.objects.create(
        submission=submission,
        number=1,
        submitted_by=student,
        submitted_at=now,
        receipt="R-PERM-0001",
        content_hash="0" * 64,
    )
    submission_file = SubmissionFile.objects.create(
        attempt=attempt_in,
        file=ContentFile(b"%PDF-1.4 report", name="report.pdf"),
        original_name="report.pdf",
        sha256="1" * 64,
    )
    Mark.objects.create(submission=submission, mark=40, is_released=True)
    feedback_file = FeedbackFile.objects.create(
        submission=submission,
        file=ContentFile(b"%PDF-1.4 feedback", name="feedback.pdf"),
        original_name="feedback.pdf",
        kind="annotated",
    )
    extension = Extension.objects.create(
        assignment=assignment, student=student, due_at=now + timedelta(days=9), reason="Illness"
    )
    accommodation = Accommodation.objects.create(person=student)

    # Quizzes.
    bank = QuestionBank.objects.create(name="AGR101 questions", site=site)
    question_category = QuestionCategory.objects.create(bank=bank, name="Soils")
    question = Question.objects.create(bank=bank, category=question_category, qtype="file", name="Upload")
    question_version = QuestionVersion.objects.create(
        question=question,
        text="Upload your soil map.",
        data=validate_question("file", "Upload your soil map.", {}),
        image=ContentFile(b"GIF89a", name="q.gif"),
    )
    quiz = Quiz.objects.create(site=site, title="Soils quiz", is_published=True)
    quiz_slot = QuizSlot.objects.create(quiz=quiz, position=1, question=question)
    quiz_override = QuizOverride.objects.create(quiz=quiz, student=student)
    attempt = Attempt.objects.create(quiz=quiz, student=student, started_at=now)
    AttemptAnswer.objects.create(
        attempt=attempt,
        position=1,
        version=question_version,
        max_mark=1,
        file=ContentFile(b"%PDF-1.4 map", name="map.pdf"),
    )

    # Practicals.
    assessor = PracticalAssessor.objects.create(
        site=site, person=_person("staff", "E0100", "Mark", "Bovell"), note="Farm manager"
    )
    task = PracticalTask.objects.create(
        site=site, title="Prepare a bed", unit_type="crop_plot", is_published=True
    )
    criterion = PracticalCriterion.objects.create(task=task, position=1, text="Bed formed")
    observation = Observation.objects.create(
        task=task, student=student, attempt=1, assessor=lecturer, observed_at=now
    )
    observation_photo = ObservationPhoto.objects.create(
        observation=observation, file=ContentFile(b"\xff\xd8\xff\xe0photo", name="plot.jpg")
    )
    framework_data = FrameworkImportSerializer(
        data={
            "code": "AGR-CROP-L2",
            "title": "Crop Production Level 2",
            "units": [
                {
                    "code": "U1",
                    "title": "Prepare land",
                    "elements": [
                        {"code": "E1.1", "title": "Beds", "criteria": [{"code": "PC1.1.1", "text": "Beds"}]}
                    ],
                }
            ],
        }
    )
    framework_data.is_valid(raise_exception=True)
    framework = framework_data.save()
    site_framework = SiteFramework.objects.create(site=site, framework=framework)
    competency_map = AssignmentCompetencyMap.objects.create(
        site=site, assignment_id=assignment.id, performance_criterion=PerformanceCriterion.objects.get()
    )
    competency_result = CompetencyResult.objects.create(
        site=site, student=student, unit=framework.units.get(), assessor=lecturer, decided_on=today
    )
    logbook_entry = LogbookEntry.objects.create(
        site=site,
        student=student,
        work_date=today,
        unit_type="crop_plot",
        task="Weeding",
        hours=2,
        client_recorded_at=now,
    )
    logbook_photo = LogbookPhoto.objects.create(
        entry=logbook_entry, file=ContentFile(b"\xff\xd8\xff\xe0photo", name="weeds.jpg")
    )

    # Talk.
    conduct_statement = ConductStatement.objects.order_by("version").first()
    ConductStatement.objects.filter(pk=conduct_statement.pk, published_at=None).update(published_at=now)
    for user in users.values():
        ConductAcceptance.objects.create(statement=conduct_statement, user=user)
    forum = Forum.objects.create(site=site, title="General", forum_type="graded", weight=1, max_mark=10)
    thread = Thread.objects.create(forum=forum, title="Hello", author=student.user)
    post = Post.objects.create(thread=thread, body="Hello all", author=student.user)
    post_report = PostReport.objects.create(post=post, reason="Rude", reported_by=classmate.user)
    conversation = Conversation.objects.create(site=site, subject="Report", started_by=student.user)
    Participant.objects.create(conversation=conversation, user=student.user)
    Participant.objects.create(conversation=conversation, user=lecturer.user)
    Message.objects.create(conversation=conversation, body="A question", sender=student.user)

    # Attendance and calendar.
    class_session = ClassSession.objects.create(
        site=site, title="Lecture 1", starts_at=now, ends_at=now + timedelta(hours=1)
    )
    AttendancePolicy.objects.create(site=site)
    feed_token = secrets.token_urlsafe(32)
    CalendarFeed.objects.create(
        user=student.user, token=feed_token, token_hash=hashlib.sha256(feed_token.encode()).hexdigest()
    )

    # Staff development and certificates.
    sd_site = CourseSite.objects.create(
        code="SD-301", title="Farm safety", kind="staff_development", is_published=True, campus_code="MRP"
    )
    Module.objects.create(site=sd_site, title="Week 1")
    CatalogueEntry.objects.create(site=sd_site, self_enrol="approval", summary="About farm safety")
    enrolment_request = EnrolmentRequest.objects.create(site=sd_site, person=lecturer, waiting_since=now)
    path = LearningPath.objects.create(code="new-staff", title="New staff", is_published=True)
    PathStep.objects.create(path=path, site=sd_site, position=1)
    required_training = RequiredTraining.objects.create(site=sd_site)
    certificate_template = CertificateTemplate.objects.filter(code="completion").first() or (
        CertificateTemplate.objects.create(code="completion", name="Completion", body="{{full_name}}")
    )
    completion = Completion.objects.create(site=site, person=student, completed_on=today)
    certificate = Certificate.objects.create(
        reference="GSA/2026/0001",
        completion=completion,
        site=site,
        person=student,
        template=certificate_template,
        issued_on=today,
        completed_on=today,
        values={},
        file=ContentFile(b"%PDF-1.4 certificate", name="certificate.pdf"),
        sha256="2" * 64,
        check_code=new_code(),
    )
    delegation = Delegation.objects.create(
        delegator=lecturer, delegate=elsewhere, starts=today, ends=today + timedelta(days=7)
    )

    # Records, privacy and operations.
    notification = Notification.objects.create(recipient=student.user, title="Marks released")
    audit_row = AuditLog.objects.create(action="update", entity="assessments.Assignment", entity_id="1")
    notice = PrivacyNotice.objects.order_by("version").first()
    PrivacyNotice.objects.create(
        version=notice.version + 1, title=notice.title, body=notice.body, published_at=now
    )
    correction = CorrectionRequest.objects.create(
        person=student, subject="personal", wrong="Sing", should_be="Singh", due_by=today + timedelta(days=30)
    )
    retention_rule = RetentionRule.objects.order_by("id").first()
    disposal_run = DisposalRun.objects.create(rule=retention_rule)
    breach = Breach.objects.create(
        reference="BR-2026-01", discovered_at=now, summary="Lost laptop", data_affected="Names"
    )
    integration_run = IntegrationRun.objects.create(kind="marks_push")
    # The term calendar (item 7.12): a term no site uses, and a closed, archived site of its own, so that the
    # world's site stays open to every write.
    from terms.models import SiteArchive, Term

    term = Term.objects.create(
        code="2099-T1",
        name="Far term",
        starts_on=date(2099, 1, 5),
        ends_on=date(2099, 4, 1),
        closes_on=date(2099, 4, 20),
    )
    old_site = CourseSite.objects.create(
        code="OLD100-2019-S1", title="An archived course", term_code="2019-S1"
    )
    site_archive = SiteArchive.objects.create(
        site=old_site,
        term_code="2019-S1",
        file=ContentFile(b"zip", name="old.zip"),
        size=3,
        sha256="0" * 64,
        records=0,
        files=0,
    )
    # Help, insights, outside tools and AI help (items 7.17, 3.11, 6.05, 6.07, 7.18).
    from assist.models import Exchange
    from helpdesk.models import HelpRequest
    from insights.alerts import DEFAULTS
    from insights.models import Alert, AlertRule, Outcome, OutcomeLink
    from lti import services as lti_services
    from lti.models import LineItem, Tool

    help_request = HelpRequest.objects.create(asked_by=student.user, subject="Upload", message="It fails")
    outcome = Outcome.objects.create(source=Outcome.Source.LOCAL, site=site, code="LO1", text="Soils")
    outcome_link = OutcomeLink.objects.create(site=site, outcome=outcome, assignment=assignment)
    alert = Alert.objects.create(
        site=site, student=student, kind=next(iter(DEFAULTS)), summary="Nothing handed in", raised_at=now
    )
    for kind, (threshold, window) in DEFAULTS.items():
        AlertRule.objects.get_or_create(kind=kind, defaults={"threshold": threshold, "window_days": window})
    tool = Tool.objects.create(
        name="Soil quiz tool",
        oidc_login_url="https://tool.example/login",
        launch_url="https://tool.example/launch",
        deep_linking_url="https://tool.example/choose",
        jwks_url="https://tool.example/jwks",
        class_list=True,
    )
    placement = lti_services.place(module, tool, "Soil texture practice", user=lecturer.user)
    ContentItem.objects.filter(pk=placement.item_id).update(is_published=True)  # students may open it
    line_item = LineItem.objects.create(
        site=site, tool=tool, placement=placement, label="Soil texture practice", score_maximum=20
    )
    exchange = Exchange.objects.create(
        site=site, user=lecturer.user, kind=Exchange.Kind.QUESTIONS, source=item, output={"questions": []}
    )

    # A lecture video, ready, with a low copy, a poster and English captions (item 4.06).
    from video.models import CaptionTrack, Rendition, Video

    video_item = ContentItem.objects.create(module=module, title="Lecture 1", kind="video", is_published=True)
    video = Video.objects.create(
        item=video_item,
        status=Video.Status.READY,
        poster=ContentFile(b"\xff\xd8\xff\xe0poster", name="poster.jpg"),
    )
    Rendition.objects.create(
        video=video, quality=Rendition.Quality.LOW, file=ContentFile(b"\x00\x00\x00 ftyp", name="low.mp4")
    )
    CaptionTrack.objects.create(video=video, language="en", text="WEBVTT\n\n00:00.000 --> 00:01.000\nSoil\n")

    # Packaged content (items 5.12 to 5.14, 6.09): an H5P exercise with the student's attempt, and an item on
    # the whole School's shelf of the library, put there by the course administrator.
    import io
    import zipfile

    from library.models import LibraryItem
    from packages import play
    from packages.models import ContentPackage, PackageAttempt

    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.writestr("h5p.json", '{"title": "Soil texture", "mainLibrary": "H5P.MultiChoice"}')
        archive.writestr("content/content.json", '{"question": "Which is loam?"}')
    package_item = ContentItem.objects.create(
        module=module,
        title="Soil texture",
        kind="package",
        is_published=True,
        file=ContentFile(zipped.getvalue(), name="soil.h5p"),
    )
    package = ContentPackage.objects.create(
        item=package_item, standard="h5p", scos=[{"id": "h5p", "title": "Soil texture", "href": ""}]
    )
    package_attempt = PackageAttempt.objects.create(package=package, person=student, user=student.user)
    library_item = LibraryItem.objects.create(
        kind="file",
        title="Integrated pest management",
        file=ContentFile(b"%PDF-1.4 guide", name="guide.pdf"),
        original_name="guide.pdf",
        licence="gsa_own",
        created_by=users["course_admin"],
    )

    world = {
        "package": package.id,
        "package_attempt": package_attempt.id,
        "play_token": play.token_for(package_attempt),
        "play_entry": "content/content.json",
        "library_item": library_item.id,
        "video_item": video_item.id,
        "language": "en",
        "quality": "low",
        "help_request": help_request.id,
        "outcome": outcome.id,
        "outcome_link": outcome_link.id,
        "alert": alert.id,
        "alert_rule": AlertRule.objects.order_by("id").first().id,
        "tool": tool.id,
        "placement": placement.id,
        "placed_item": placement.item_id,
        "line_item": line_item.id,
        "exchange": exchange.id,
        "site": site.id,
        "module": module.id,
        "item": item.id,
        "takedown": takedown.id,
        "announcement": announcement.id,
        "group": group.id,
        "grouping": grouping.id,
        "site_template": site_template.id,
        "rubric": rubric.id,
        "grade_category": category.id,
        "assignment": assignment.id,
        "submission": submission.id,
        "receipt": attempt_in.receipt,
        "submission_file": submission_file.id,
        "feedback_file": feedback_file.id,
        "extension": extension.id,
        "accommodation": accommodation.id,
        "bank": bank.id,
        "question_category": question_category.id,
        "question": question.id,
        "question_version": question_version.id,
        "quiz": quiz.id,
        "quiz_slot": quiz_slot.id,
        "quiz_override": quiz_override.id,
        "attempt": attempt.id,
        "assessor": assessor.id,
        "task": task.id,
        "criterion": criterion.id,
        "observation": observation.id,
        "observation_photo": observation_photo.id,
        "framework": framework.id,
        "site_framework": site_framework.id,
        "competency_map": competency_map.id,
        "competency_result": competency_result.id,
        "logbook_entry": logbook_entry.id,
        "logbook_photo": logbook_photo.id,
        "conduct_statement": conduct_statement.id,
        "forum": forum.id,
        "thread": thread.id,
        "post": post.id,
        "post_report": post_report.id,
        "conversation": conversation.id,
        "class_session": class_session.id,
        "feed_token": feed_token,
        "sd_site": sd_site.id,
        "enrolment_request": enrolment_request.id,
        "path": path.id,
        "required_training": required_training.id,
        "certificate_template": certificate_template.id,
        "certificate": certificate.id,
        "delegation": delegation.id,
        "notification": notification.id,
        "audit_row": audit_row.id,
        "notice": notice.id,
        "correction": correction.id,
        "retention_rule": retention_rule.id,
        "disposal_run": disposal_run.id,
        "breach": breach.id,
        "integration_run": integration_run.id,
        "term": term.id,
        "site_archive": site_archive.id,
        "student_person": student.id,
        "classmate_person": classmate.id,
        "elsewhere_person": elsewhere.id,
        "lecturer_person": lecturer.id,
        "position": 1,
    }

    # Similarity, peer review, paper quizzes and open short courses (items 3.20, 3.24, 4.13, 5.07). The
    # classmate reviews the student's work; the paper has one empty version; the open course has places.
    from opencourses.models import OpenRegistration  # noqa: F401 - the app's tables are in the world
    from paperquizzes.models import PaperQuiz, PaperVersion
    from peerreview.models import PeerReview, PeerReviewSetup
    from staffdev.models import CatalogueEntry as OpenEntry

    peer_setup = PeerReviewSetup.objects.create(
        assignment=assignment, reviews_due_at=now + timedelta(days=14), allocated_at=now
    )
    peer_review = PeerReview.objects.create(
        setup=peer_setup, reviewer=classmate, submission=submission, position=1
    )
    quiz_paper = PaperQuiz.objects.create(quiz=quiz, title="Paper test", sat_on=today)
    PaperVersion.objects.create(paper=quiz_paper, label="A", items=[])
    open_site = CourseSite.objects.create(
        code="OPEN-POULTRY", title="Backyard poultry", kind=CourseSite.Kind.OPEN, is_published=True
    )
    OpenEntry.objects.create(site=open_site, summary="A small flock.")
    world.update({"peer_review": peer_review.id, "quiz_paper": quiz_paper.id, "open_site": open_site.id})

    # Sessions last: a change of roles or teaching signs a person out.
    sessions = {}
    for role, user in users.items():
        client = APIClient()
        client.force_login(user)
        session = client.session
        session["mfa_verified"] = True
        # Active "in the future": the idle check never ends it and never stops to write the session list.
        session[SIGNED_IN_AT], session[LAST_ACTIVITY] = now.timestamp(), now.timestamp() + 3600
        session.save()
        sessions[role] = session.session_key
        UserSession.objects.get_or_create(
            user=user, session_key=session.session_key, defaults={"last_seen_at": now}
        )
    world["user_session"] = UserSession.objects.get(user=users["student"]).id
    world["sessions"] = sessions
    return world


@pytest.fixture(scope="module")
def media_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("permission-table-files")


@pytest.fixture(autouse=True)
def _media_root(settings, media_dir, monkeypatch):
    """One place for the module's files, which every request leaves in place.

    The world's files are written before any test's own settings apply. A removal deletes its file at once,
    which no rollback brings back, so files are not deleted here: the next role must find them.
    """
    from django.core.files.storage import FileSystemStorage

    settings.MEDIA_ROOT = media_dir
    monkeypatch.setattr(FileSystemStorage, "delete", lambda storage, name: None)


@pytest.fixture(autouse=True)
def _ai_on(settings):
    """AI help switched on (it is off by default), so that switching it for a site reaches the permission
    check. The model's address answers nothing at once: a request that gets that far is answered 503."""
    settings.AI_ENABLED, settings.AI_MODEL, settings.AI_TIMEOUT_SECONDS = True, "permission-table", 1
    settings.AI_OLLAMA_URL = "http://127.0.0.1:9"
    settings.OPEN_BADGES_ENABLED = True  # off by default: on, a certificate's badge reaches its own checks
    settings.OPEN_COURSES_ENABLED = True  # off by default: on, the open-course pages reach their own checks


@pytest.fixture(scope="module")
def world(django_db_setup, django_db_blocker, media_dir):
    from core import crypto

    if "postgresql" not in settings.DATABASES["default"]["ENGINE"]:
        pytest.skip("database tests need PostgreSQL")
    keys = {"MEDIA_ROOT": media_dir, "FIELD_ENCRYPTION_KEY": "test-only-key"}
    with django_db_blocker.unblock(), override_settings(**keys):
        crypto._fernet.cache_clear()
        atomic = transaction.atomic()
        atomic.__enter__()
        try:
            yield build_world()
        finally:
            transaction.set_rollback(True)
            atomic.__exit__(None, None, None)


# --- requests ----------------------------------------------------------------------------------------------


def path_for(route: str, world: dict) -> str:
    def fill(match):
        name = match.group(1)
        before = route[: match.start()].rstrip("/").rsplit("/", 1)[-1]
        key = (
            NAMED_OBJECTS.get(f"{before}:{name}")
            or NAMED_OBJECTS.get(name)
            or SEGMENT_OBJECTS.get(before)
            or name
        )
        if key not in world:
            raise AssertionError(
                f"{route}: no world record for {{{name}}} after '{before}' (SEGMENT_OBJECTS)"
            )
        return str(world[key])

    return re.sub(r"\{(\w+)\}", fill, route)


def body_for(key: str, world: dict) -> dict:
    def resolve(value):
        if isinstance(value, Literal):
            return value.value
        return [world[v] for v in value] if isinstance(value, list) else world[value]

    return {field: resolve(value) for field, value in BODY.get(key, {}).items()}


def call(world: dict, role: str, method: str, path: str, body: dict, form: bool = False):
    client = APIClient(raise_request_exception=False)
    if role != "anonymous":
        client.cookies[settings.SESSION_COOKIE_NAME] = world["sessions"][role]
    with transaction.atomic():
        sent = "multipart" if form else "json"
        response = getattr(client, method.lower())(path, body if method != "GET" else None, format=sent)
        if response.streaming:
            # Read a download to its end, which closes it the test client's way. Closing it directly would
            # signal the end of the request and close the database connection, and the world with it.
            for _chunk in response.streaming_content:
                pass
        transaction.set_rollback(True)
    return response


def _json(response):
    if response.streaming:
        return None
    try:
        return json.loads(response.content)
    except (ValueError, UnicodeDecodeError):
        return None


def listed_ids(response, field: str = "id") -> set | None:
    """The ids in a list answer, or None when the answer is not a list."""
    data = _json(response)
    rows = data.get("results") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return None
    return {row.get(field) for row in rows if isinstance(row, dict)}


def unknown_parent(response, body: dict) -> bool:
    """A 400 that says a record named in the body does not exist: how a write names a site the caller
    cannot open (courses.access.TaughtRecord), which reads exactly as a record that is not there."""
    data = _json(response)
    if response.status_code != 400 or not isinstance(data, dict):
        return False
    return any("does not exist" in str(data.get(field, "")) for field in body)


def verdict(key: str, access: Access, role: str, response, record_id, body: dict) -> str | None:
    """None when the answer matches the declaration, otherwise what went wrong."""
    status = response.status_code
    if status == 500:
        return f"{role}: failed with 500"
    if role in access.roles:
        if status in DENIED or status == 404 or unknown_parent(response, body):
            return f"{role}: refused with {status} but the table allows it"
        return None  # 2xx, or a refusal for what was sent (400, 405, 409, 415) or by a service behind (502)
    if status in DENIED or (access.hidden and (status == 404 or unknown_parent(response, body))):
        return None
    if status == 404 or unknown_parent(response, body):
        return f"{role}: {status} for a record it cannot see; declare HIDDEN if the code hides it on purpose"
    if 200 <= status < 300 and key.startswith("GET ") and record_id is not None:
        ids = listed_ids(response, LIST_FIELD.get(key, "id"))
        if ids is not None and record_id not in ids:
            return None  # may use the list, does not see the record
    return f"{role}: answered {status} but the table refuses it"


RECORD = os.environ.get("PERMISSION_TABLE_RECORD")  # a file to write what each role got, to review by hand


@pytest.mark.django_db
@pytest.mark.parametrize("key", PAIRS)
def test_permission(world, key):
    """Every role against one endpoint and method; the failure names each role that does not match."""
    method, route = key.split(" ", 1)
    cache.clear()  # throttles count per user; this module makes many requests
    path = path_for(route, world) + QUERY.get(key, "").format(**world)
    body = body_for(key, world)
    segment = route.rstrip("/").rsplit("/", 1)[-1]
    record_id = world.get(SEGMENT_OBJECTS.get(segment, "")) if "{" not in route else None
    results = {role: call(world, role, method, path, body, key in FORM) for role in ROLES}
    if RECORD:
        seen = {}
        for role, response in results.items():
            ids = listed_ids(response, LIST_FIELD.get(key, "id")) if response.status_code == 200 else None
            mark = "" if ids is None or record_id is None else "+" if record_id in ids else "-"
            hidden = "?" if unknown_parent(response, body) else ""
            seen[role] = f"{response.status_code}{mark}{hidden}"
        with open(RECORD, "a", encoding="utf-8") as out:
            out.write(json.dumps({"key": key, "seen": seen}) + "\n")
        return
    access = TABLE.get(key)
    assert access is not None, f"no declaration for {key!r}: add it to TABLE"
    problems = [p for role in ROLES if (p := verdict(key, access, role, results[role], record_id, body))]
    if key in ROWS:
        name, sees = ROWS[key]
        for role, response in results.items():
            if (
                role not in sees.roles
                and response.status_code == 200
                and world[name] in (listed_ids(response) or ())
            ):
                problems.append(f"{role}: is shown the {name} in the list")
    assert not problems, f"{key} ({path}) declared {access}:\n  " + "\n  ".join(problems)


def test_every_route_is_declared():
    missing = [key for key in PAIRS if key not in TABLE]
    assert not missing, "endpoints with no line in TABLE:\n  " + "\n  ".join(f'"{k}": ...,' for k in missing)


def test_no_stale_declarations():
    stale = sorted(set(TABLE) - set(PAIRS))
    assert not stale, "lines in TABLE that match no route:\n  " + "\n  ".join(stale)


def test_every_plain_view_declares_its_methods():
    unknown = [route for route, methods in ROUTES.items() if "?" in methods]
    assert not unknown, f"plain Django views without methods in PLAIN_VIEW_METHODS: {unknown}"
