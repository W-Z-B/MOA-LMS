from django.contrib import admin

from assessments.models import Assignment, Mark, Submission


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "site", "due_at", "max_mark", "weight", "is_published")
    list_filter = ("is_published",)


admin.site.register(Submission)
admin.site.register(Mark)
