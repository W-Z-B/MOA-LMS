from django.contrib import admin

from assessments.models import Assignment, Mark, Submission


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "site", "due_at", "max_mark", "weight", "is_published")
    list_filter = ("is_published",)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Marks and handed-in work change only in the web app, where release, locking once the SRMS has the
    result and the reasons for a change are enforced (ASVS 4.3.3): the admin shows them, nothing more."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Submission, ReadOnlyAdmin)
admin.site.register(Mark, ReadOnlyAdmin)
