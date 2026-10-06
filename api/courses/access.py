"""Who may do what on a course site. Membership decides; system roles only widen access."""

from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from courses.models import CourseSite, Membership
from iam.models import Role
from iam.services import SITE_ADMIN_ROLES, has_role

ADMIN = "admin"
TEACHING = (ADMIN, Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT)


def person_of(user):
    return getattr(user, "person", None)


def is_learner(user) -> bool:
    """A self-registered learner on open short courses (item 5.07): open sites only, never academic ones,
    whatever memberships or roles the account may be given by mistake."""
    person = person_of(user)
    return (person is not None and person.kind == "learner") or (
        has_role(user, Role.LEARNER) and not has_role(user, *SITE_ADMIN_ROLES, Role.AUDITOR, Role.LECTURER)
    )


def site_role(user, site: CourseSite) -> str | None:
    """'admin', a membership role, 'auditor' (read-only), or None when the user has no access."""
    if is_learner(user) and site.kind != CourseSite.Kind.OPEN:
        return None
    if has_role(user, *SITE_ADMIN_ROLES):
        return ADMIN
    person = person_of(user)
    if person is not None:
        membership = Membership.objects.filter(site=site, person=person, is_active=True).first()
        if membership is not None:
            if membership.role == Membership.SiteRole.STUDENT and not site.is_published:
                return None
            return membership.role
    if has_role(user, Role.AUDITOR):
        return "auditor"
    return None


def can_teach(user, site: CourseSite) -> bool:
    return site_role(user, site) in TEACHING


def visible_sites(user):
    """Sites the user may open: all for admins and auditors, otherwise their memberships."""
    qs = CourseSite.objects.all()
    if has_role(user, *SITE_ADMIN_ROLES, Role.AUDITOR):
        return qs
    person = person_of(user)
    if person is None:
        return qs.none()
    mine = Q(memberships__person=person, memberships__is_active=True)
    teaching = mine & Q(memberships__role__in=[Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT])
    learning = mine & Q(memberships__role=Membership.SiteRole.STUDENT, is_published=True)
    # An archived site (item 7.12) leaves members' lists; course administrators and the auditor keep it.
    if is_learner(user):
        return qs.filter(learning, kind=CourseSite.Kind.OPEN).filter(archive__isnull=True).distinct()
    return qs.filter(teaching | learning).filter(archive__isnull=True).distinct()


def taught_sites(user):
    """Sites the user teaches on (can_teach): all for course administrators, otherwise their teaching."""
    qs = CourseSite.objects.all()
    if has_role(user, *SITE_ADMIN_ROLES):
        return qs
    person = person_of(user)
    if person is None:
        return qs.none()
    return qs.filter(
        memberships__person=person,
        memberships__is_active=True,
        memberships__role__in=[Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT],
    ).distinct()


@extend_schema_field(OpenApiTypes.INT)
class TaughtRecord(serializers.PrimaryKeyRelatedField):
    """A course site, or a record on one, named by id in a write, which only its teaching staff may make.

    Checked before any other validation, in this order: an id on a site the caller cannot open reads as
    "does not exist", exactly as an id that is not there at all, so a refusal never tells that a site or
    its records exist; then a site the caller can open but does not teach on is refused outright.
    """

    def __init__(self, model, site_path: str | None = None, **kwargs):
        self.model = model
        self.site_path = site_path  # how to reach the site from the record; None when it is the site
        super().__init__(**kwargs)

    def get_queryset(self):
        request = self.context.get("request")
        if request is None:
            return self.model.objects.none()
        sites = visible_sites(request.user)
        if self.site_path is None:
            return sites
        return self.model.objects.filter(**{f"{self.site_path}__in": sites})

    def to_internal_value(self, data):
        record = super().to_internal_value(data)
        site = record
        for step in (self.site_path or "").split("__"):
            site = getattr(site, step) if step else site
        if not can_teach(self.context["request"].user, site):
            raise PermissionDenied("Only the site's teaching staff can do this.")
        return record
