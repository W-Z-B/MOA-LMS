"""The single permission layer every personnel endpoint passes through."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from iam.services import has_role, requires_mfa

MFA_SESSION_KEY = "mfa_verified"


class RolePermission(BasePermission):
    """Checks authentication, MFA for privileged roles, and the view's read_roles / write_roles.

    A view that leaves both role tuples as None allows any authenticated user.
    """

    message = "You do not hold a role that permits this action."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if requires_mfa(user) and not request.session.get(MFA_SESSION_KEY, False):
            self.message = "Multi-factor verification is required for your role."
            return False
        roles = getattr(view, "read_roles" if request.method in SAFE_METHODS else "write_roles", None)
        if roles is None:
            return True
        return has_role(user, *roles)
