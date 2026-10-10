from django.contrib import admin

from iam.admin_audit import AuditedAdmin
from iam.models import Role, RoleScope, TotpDevice

# Every admin is audited (iam.admin_audit, mixed in by iam.admin_site.LmsAdminSite.register); these name the
# actions as the web app does: giving or taking a role, and removing an authenticator so it is set up again.


@admin.register(Role)
class RoleAdmin(AuditedAdmin):
    list_display = ("code", "name")


@admin.register(RoleScope)
class RoleScopeAdmin(AuditedAdmin):
    list_display = ("user", "role", "campus_code", "unit_code")
    list_filter = ("role", "campus_code")
    autocomplete_fields = ("user",)
    added, changed, removed = "role_given", "role_changed", "role_taken"


@admin.register(TotpDevice)
class TotpDeviceAdmin(AuditedAdmin):
    list_display = ("user", "confirmed_at")
    exclude = ("secret",)
    removed = "authenticator_reset"
