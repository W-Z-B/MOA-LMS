from django.contrib import admin

from audit.services import record, snapshot
from iam.models import Role, RoleScope, TotpDevice


class AuditedAdmin(admin.ModelAdmin):
    """Changes made in the Django admin reach the chained audit log like every other change (ASVS 7.1.3,
    4.3.3): giving or taking a role, and removing an authenticator so that it is set up again."""

    added, changed, removed = "create", "update", "delete"

    def save_model(self, request, obj, form, change):
        before = snapshot(type(obj).objects.get(pk=obj.pk)) if change and obj.pk else None
        super().save_model(request, obj, form, change)
        record(
            request,
            self.changed if change else self.added,
            obj,
            before=before,
            after=snapshot(obj),
            reason="Django admin",
        )

    def delete_model(self, request, obj):
        before, pk = snapshot(obj), obj.pk
        super().delete_model(request, obj)
        record(request, self.removed, obj, before=before, entity_id=pk, reason="Django admin")

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request, obj)


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
