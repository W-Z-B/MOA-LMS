"""The Django admin, held to the same sign-in rules as the web app.

The stock admin has its own password form, which skips the failed-login lockout and the authenticator
step. Here the admin has no form of its own: people sign in through the web app (lockout, then the
authenticator code) and the admin accepts that session only once a code has verified it. Every table is
behind the admin, so a staff account whose roles would not otherwise ask for a code still needs one here.
"""

from django.contrib import admin
from django.http import HttpResponseRedirect

from iam.permissions import MFA_SESSION_KEY


class LmsAdminSite(admin.AdminSite):
    site_header = "GSA LMS administration"
    site_title = "GSA LMS administration"
    index_title = "Records"

    def has_permission(self, request) -> bool:
        if not super().has_permission(request):
            return False
        return bool(request.session.get(MFA_SESSION_KEY, False))

    def login(self, request, extra_context=None):
        """No password form of its own: people sign in through the web app, then open the admin."""
        return HttpResponseRedirect("/")
