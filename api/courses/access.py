"""Who may do what on a course site. Membership decides; system roles only widen access."""

from django.db.models import Q

from courses.models import CourseSite, Membership
from iam.models import Role
from iam.services import SITE_ADMIN_ROLES, has_role

ADMIN = "admin"
TEACHING = (ADMIN, Membership.SiteRole.LECTURER, Membership.SiteRole.ASSISTANT)


def person_of(user):
    return getattr(user, "person", None)


def site_role(user, site: CourseSite) -> str | None:
    """'admin', a membership role, 'auditor' (read-only), or None when the user has no access."""
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
    return qs.filter(teaching | learning).distinct()
