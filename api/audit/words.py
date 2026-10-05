"""Audit entries said in words, for the audit viewer and for a person's own record (items 1.17, 1.18).

The log stores codes (an action, a record's app_label.modelname); people read what was done and to what.
"""

from audit.services import MASK

HIDDEN = "(hidden)"
RECORDS = {
    "auth.user": "Account",
    "people.personref": "Person",
    "courses.coursesite": "Course site",
    "courses.membership": "Course membership",
    "courses.module": "Course module",
    "courses.contentitem": "Course material",
    "courses.announcement": "Announcement",
    "courses.completion": "Completion",
    "assessments.assignment": "Assignment",
    "assessments.submission": "Submission",
    "assessments.mark": "Mark",
    "iam.accessreview": "Access review",
    "audit.auditlog": "Audit log",
    "audit.auditcheck": "Audit check",
    "integration.serviceclient": "Service key",
    "privacy.privacynotice": "Privacy notice",
    "privacy.correctionrequest": "Correction request",
    "privacy.retentionrule": "Retention rule",
    "privacy.disposalrun": "Disposal run",
    "privacy.breach": "Data breach",
    "integration.integrationrun": "Integration run",
}
ACTIONS = {
    "create": "Added",
    "update": "Changed",
    "delete": "Removed",
    "download": "Downloaded",
    "submit": "Submitted",
    "mark": "Marked",
    "login": "Signed in",
    "logout": "Signed out",
    "mfa_verified": "Authenticator code accepted",
    "mfa_failed": "Authenticator code refused",
    "access_review_signed": "Access review signed off",
    "audit_exported": "Audit log exported",
    "audit_checked": "Audit log checked",
    "notice_drafted": "Privacy notice drafted",
    "notice_edited": "Privacy notice edited",
    "notice_published": "Privacy notice published",
    "notice_acknowledged": "Privacy notice read",
    "record_viewed": "Own record viewed",
    "record_downloaded": "Own record downloaded",
    "record_produced": "Record produced for a request",
    "correction_requested": "Correction asked for",
    "correction_corrected": "Corrected as asked",
    "correction_declined": "Correction not made",
    "retention_changed": "Retention period changed",
    "retention_confirmed": "Retention period confirmed",
    "disposal_proposed": "Disposal proposed",
    "disposal_kept": "Kept from disposal",
    "disposal_approved": "Disposal approved",
    "disposal_cancelled": "Disposal cancelled",
    "disposed": "Destroyed under the retention schedule",
    "purged": "Old logs removed",
    "breach_closed": "Breach closed",
    "account_invited": "Invited to choose a password",
    "account_closed": "Account closed",
    "password_link_sent": "Password link sent",
    "password_set": "Password chosen through a link",
    "password_changed": "Password changed",
    "password_change_failed": "Password change refused",
}
# Account events: in the audit viewer and in the sign-ins of a person's record, not among their actions.
ACCOUNT_EVENTS = (
    "login",
    "logout",
    "mfa_verified",
    "mfa_failed",
    "password_link_sent",
    "password_set",
    "password_changed",
    "password_change_failed",
    "notice_acknowledged",
    "record_viewed",
    "record_downloaded",
)
FIELD_LABELS = {"external_id": "Employee or student number", "is_late": "Late", "is_released": "Released"}
# Bookkeeping fields that change with every save and say nothing about the record.
QUIET = {"id", "created_at", "updated_at", "created_by", "updated_by"}


def actor_name(row) -> str:
    """Who did it: a person, a linked system, someone not signed in, or the system."""
    if row.actor is not None:
        return row.actor.get_full_name() or row.actor.get_username()
    if row.action.startswith("integration:"):
        return "A linked system"
    return "Someone not signed in" if row.source_ip else "System"


def action_name(code: str) -> str:
    """What was done, in words: integration:sites.read reads as "Integration: sites.read"."""
    if code in ACTIONS:
        return ACTIONS[code]
    return ": ".join(part.replace("_", " ") for part in code.split(":")).capitalize()


def record_name(entity: str) -> str:
    return RECORDS.get(entity, entity)


def field_label(name: str) -> str:
    return FIELD_LABELS.get(name, name.replace("_", " ").capitalize())


def shown(value):
    """Masked values never leave as their fingerprint: the reader learns only that they are set."""
    if isinstance(value, str) and value.startswith(MASK):
        return HIDDEN
    return value


def changes(before: dict | None, after: dict | None) -> list[dict]:
    if not before or not after:
        return []
    return [
        {"field": field_label(name), "before": shown(before.get(name)), "after": shown(after.get(name))}
        for name in after
        if name not in QUIET and before.get(name) != after.get(name)
    ]
