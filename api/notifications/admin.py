from django.contrib import admin

from notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "recipient", "kind", "title", "read_at", "emailed")
    list_filter = ("kind", "emailed")
    search_fields = ("title", "recipient__username")
