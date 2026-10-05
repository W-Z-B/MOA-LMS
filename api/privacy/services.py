"""The privacy notice in force, and a person's own copy of what the LMS holds about them (item 1.18).

A student's copy holds their memberships, their submissions (what and when, not the work itself, which they
download from the course), released marks with feedback, completions, notifications and sign-ins. A member
of staff's copy holds their memberships and what they did in the LMS (teaching actions from the audit log).
"""

from django.utils import timezone

from privacy.models import CorrectionRequest, NoticeAcknowledgement, PrivacyNotice

SIGN_INS_SHOWN = 200
ACTIONS_SHOWN = 1000


def current_notice() -> PrivacyNotice | None:
    """The newest published version, or None before GSA publishes one."""
    return PrivacyNotice.objects.filter(published_at__isnull=False).order_by("-version").first()


def notice_due(user) -> int | None:
    """The version this person has still to read, or None."""
    notice = current_notice()
    if notice is None or not getattr(user, "is_authenticated", False) or getattr(user, "pk", None) is None:
        return None
    if NoticeAcknowledgement.objects.filter(notice=notice, user=user).exists():
        return None
    return notice.version


def _name(user) -> str | None:
    return (user.get_full_name() or user.get_username()) if user else None


def _account(user) -> dict:
    from audit.models import AuditLog
    from iam.models import RoleScope

    return {
        "username": user.get_username(),
        "name": _name(user),
        "email": user.email,
        "roles": [
            {
                "role": grant.role.name,
                "campus": grant.campus_code or "All campuses",
                "given": grant.created_at,
            }
            for grant in RoleScope.objects.filter(user=user).select_related("role")
        ],
        "last_sign_in": user.last_login,
        "sign_ins": [
            {
                "at": row.at,
                "what": "Signed in" if row.action == "login" else "Signed out",
                "from": row.source_ip,
            }
            for row in AuditLog.objects.filter(
                entity="auth.user", entity_id=user.pk, action__in=["login", "logout"]
            ).order_by("-id")[:SIGN_INS_SHOWN]
        ],
        "privacy_notices_read": [
            {"version": a.notice.version, "title": a.notice.title, "read_at": a.at}
            for a in NoticeAcknowledgement.objects.filter(user=user).select_related("notice")
        ],
        "notifications": [
            {"sent_at": n.created_at, "title": n.title, "read_at": n.read_at, "emailed": n.emailed}
            for n in user.notifications.order_by("-created_at")
        ],
    }


def _memberships(person) -> list[dict]:
    return [
        {
            "site": m.site.code,
            "title": m.site.title,
            "term": m.site.term_code,
            "role": m.get_role_display(),
            "active": m.is_active,
            "since": m.created_at,
        }
        for m in person.memberships.select_related("site").order_by("site__code")
    ]


def _student_work(person) -> dict:
    from assessments.models import Submission

    submissions = (
        Submission.objects.filter(student=person)
        .select_related("assignment", "assignment__site", "mark", "mark__marked_by")
        .order_by("-submitted_at")
    )
    work, marks = [], []
    for s in submissions:
        work.append(
            {
                "site": s.assignment.site.code,
                "assignment": s.assignment.title,
                "submitted_at": s.submitted_at,
                "late": s.is_late,
                "file": s.file.name.rsplit("/", 1)[-1] if s.file else None,
                "text_length": len(s.text),
            }
        )
        mark = getattr(s, "mark", None)
        if mark is not None and mark.is_released:  # an unreleased mark is not yet the student's to see
            marks.append(
                {
                    "site": s.assignment.site.code,
                    "assignment": s.assignment.title,
                    "mark": str(mark.mark),
                    "out_of": str(s.assignment.max_mark),
                    "feedback": mark.feedback,
                    "marked_by": mark.marked_by.full_name if mark.marked_by else None,
                }
            )
    return {"submissions": work, "released_marks": marks}


def _teaching_actions(user) -> list[dict]:
    from audit import words
    from audit.models import AuditLog

    rows = (
        AuditLog.objects.filter(actor=user)
        .exclude(action__in=words.ACCOUNT_EVENTS)
        .order_by("-id")[:ACTIONS_SHOWN]
    )
    return [
        {
            "at": row.at,
            "action": words.action_name(row.action),
            "record": words.record_name(row.entity),
            "record_id": row.entity_id,
            "reason": row.reason,
        }
        for row in rows
    ]


def _person_record(person) -> dict:
    data = {
        "kind": person.get_kind_display(),
        "number": person.external_id,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "email": person.email,
        "campus": person.campus_code,
        "active": person.is_active,
        "memberships": _memberships(person),
        "completions": [
            {"site": c.site.code, "title": c.site.title, "completed_on": c.completed_on}
            for c in person.completions.select_related("site").order_by("-completed_on")
        ],
        "correction_requests": [
            {
                "about": c.get_subject_display(),
                "wrong": c.wrong,
                "should_be": c.should_be,
                "state": c.get_state_display(),
                "asked_on": c.created_at,
                "answer": c.decision_note,
            }
            for c in CorrectionRequest.objects.filter(person=person)
        ],
    }
    if person.kind == person.Kind.STUDENT:
        data.update(_student_work(person))
    return data


def record_of(user) -> dict:
    """Everything the LMS holds about this person, for their own copy."""
    person = getattr(user, "person", None)
    about = "What the GSA LMS holds about you. If anything is wrong, ask for a correction from My data."
    return _record(user, person, about)


def record_of_person(person) -> dict:
    """The same copy for a person who asked for it on paper, account included when they have one."""
    user = person.user if person.user_id else None
    return _record(user, person, "What the GSA LMS holds about this person, produced for their request.")


def _record(user, person, about: str) -> dict:
    staff = person is not None and person.kind == person.Kind.STAFF
    return {
        "produced_at": timezone.now(),
        "about": about,
        "account": _account(user) if user is not None else None,
        "person": _person_record(person) if person is not None else None,
        "teaching_actions": _teaching_actions(user) if staff and user is not None else None,
    }
