"""The single permission layer every endpoint passes through."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from iam.services import has_role, requires_mfa

MFA_SESSION_KEY = "mfa_verified"


class RolePermission(BasePermission):
    """Checks authentication, MFA for privileged roles, and the view's read_roles / write_roles.

    A view that leaves both role tuples as None allows any authenticated user. Each refusal carries a code
    as well as a sentence (core.exceptions): not_authenticated, mfa_required or permission_denied.
    """

    message = "Sign in to continue."
    code = "not_authenticated"

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            self.message, self.code = "Sign in to continue.", "not_authenticated"
            return False
        if requires_mfa(user) and not request.session.get(MFA_SESSION_KEY, False):
            self.message = "An authenticator code is required for your role."
            self.code = "mfa_required"
            return False
        self.message = "You do not hold a role that permits this action."
        self.code = "permission_denied"
        roles = getattr(view, "read_roles" if request.method in SAFE_METHODS else "write_roles", None)
        if roles is None:
            return True
        return has_role(user, *roles)


class DocsPermission(BasePermission):
    """The API documentation: open to anyone when API_DOCS_PUBLIC is on, otherwise signed-in people only."""

    message = "Sign in to the web app first, then open the API documentation."

    def has_permission(self, request, view) -> bool:
        from django.conf import settings

        return settings.API_DOCS_PUBLIC or bool(request.user and request.user.is_authenticated)


def role_required(*codes: str) -> type[RolePermission]:
    """RolePermission for a function view: any of the given roles, for reading and writing alike."""

    class HasRole(RolePermission):
        def has_permission(self, request, view) -> bool:
            if not super().has_permission(request, view):
                return False
            self.message = "You do not hold a role that permits this action."
            self.code = "permission_denied"
            return has_role(request.user, *codes)

    HasRole.__name__ = f"HasRole_{'_'.join(codes)}"
    return HasRole
