from django.contrib import admin

from integration.models import ServiceClient


@admin.register(ServiceClient)
class ServiceClientAdmin(admin.ModelAdmin):
    list_display = ("name", "key_prefix", "scopes", "is_active", "last_used_at")
    readonly_fields = ("key_prefix", "key_hash", "created_at", "last_used_at")

    def has_add_permission(self, request):
        return False  # keys are issued with the create_service_client command so they are shown once
