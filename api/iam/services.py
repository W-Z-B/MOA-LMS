"""Role look-ups used by permissions and scoping."""

from iam.models import Role, RoleScope

BROAD_READ_ROLES = frozenset({Role.ADMINISTRATOR, Role.COURSE_ADMIN, Role.AUDITOR})
SITE_ADMIN_ROLES = (Role.ADMINISTRATOR, Role.COURSE_ADMIN)


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


def requires_mfa(user) -> bool:
    return bool(role_codes(user) & Role.MFA_REQUIRED) or getattr(user, "is_superuser", False)


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
