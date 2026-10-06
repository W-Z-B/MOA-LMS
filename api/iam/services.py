"""Role look-ups used by permissions and scoping, and the limits on failed sign-ins."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from iam.models import LoginAttempt, Role, RoleScope

BROAD_READ_ROLES = frozenset({Role.ADMINISTRATOR, Role.COURSE_ADMIN, Role.AUDITOR})
SITE_ADMIN_ROLES = (Role.ADMINISTRATOR, Role.COURSE_ADMIN)
# Site roles that can mark and release marks (courses.access.TEACHING, without the system administrators).
TEACHING_SITE_ROLES = ("lecturer", "assistant")


def role_codes(user) -> set[str]:
    if not getattr(user, "is_authenticated", False) or getattr(user, "is_service", False):
        return set()
    cached = getattr(user, "_role_codes", None)
    if cached is None:
        cached = set(RoleScope.objects.filter(user=user).values_list("role__code", flat=True))
        user._role_codes = cached
    return cached


def has_role(user, *codes: str) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    return bool(role_codes(user) & set(codes))


def campus_codes(user) -> set[str]:
    return set(
        RoleScope.objects.filter(user=user).exclude(campus_code="").values_list("campus_code", flat=True)
    )


def teaches(user) -> bool:
    """Whether the person teaches on any course site, whatever their system roles say.

    Teaching staff release marks that become results (decision D14), so they need an authenticator code
    even when their account was given no lecturer role.
    """
    if not getattr(user, "is_authenticated", False) or getattr(user, "is_service", False):
        return False
    cached = getattr(user, "_teaches", None)
    if cached is None:
        person = getattr(user, "person", None)
        cached = person is not None and person.memberships.filter(
            is_active=True, role__in=TEACHING_SITE_ROLES
        ).exists()
        user._teaches = cached
    return cached


def requires_mfa(user) -> bool:
    return (
        bool(role_codes(user) & Role.MFA_REQUIRED) or getattr(user, "is_superuser", False) or teaches(user)
    )


def scope_queryset(user, queryset, campus_field: str = "campus_code"):
    if getattr(user, "is_superuser", False) or role_codes(user) & BROAD_READ_ROLES:
        return queryset
    codes = campus_codes(user)
    if not codes:
        return queryset.none()
    return queryset.filter(**{f"{campus_field}__in": codes})


def person_payload(user) -> dict:
    """Link from the signed-in user to their person record (staff from the HRMS, students from the SRMS)."""
    person = getattr(user, "person", None)
    return {
        "person_id": person.id if person else None,
        "person_kind": person.kind if person else None,
        "external_id": person.external_id if person else None,
    }


def account_locked(username: str) -> bool:
    """True when the account has reached the failure limit inside the lockout window."""
    window_start = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    recent = LoginAttempt.objects.filter(username=username, at__gte=window_start).order_by("-at")
    failures = 0
    for attempt in recent[: settings.LOGIN_MAX_FAILURES]:
        if attempt.success:
            break
        failures += 1
    return failures >= settings.LOGIN_MAX_FAILURES


def address_blocked(address: str | None) -> bool:
    """True when one address has failed too often inside the window, whatever the accounts tried.

    The account lockout stops guessing one person's password; this stops one password being tried
    against many accounts. Only failures count, so a campus signing in through one network address is
    not held up by its own successful sign-ins.
    """
    if address is None:
        return False
    window_start = timezone.now() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    failures = LoginAttempt.objects.filter(source_ip=address, success=False, at__gte=window_start).count()
    return failures >= settings.LOGIN_MAX_FAILURES_PER_ADDRESS
