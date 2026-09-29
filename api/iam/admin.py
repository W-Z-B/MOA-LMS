from django.contrib import admin

from iam.models import Role, RoleScope, TotpDevice


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name")


@admin.register(RoleScope)
class RoleScopeAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "campus_code", "unit_code")
    list_filter = ("role", "campus_code")
    autocomplete_fields = ("user",)


@admin.register(TotpDevice)
class TotpDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "confirmed_at")
    exclude = ("secret",)
