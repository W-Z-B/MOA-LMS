from django.contrib import admin

from practicals.models import (
    CompetencyFramework,
    CompetencyResult,
    LogbookEntry,
    Observation,
    PracticalAssessor,
    PracticalTask,
)


@admin.register(PracticalTask)
class PracticalTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "site", "unit_type", "weight", "closes_at", "is_published")
    list_filter = ("unit_type", "is_published")


@admin.register(Observation)
class ObservationAdmin(admin.ModelAdmin):
    list_display = ("task", "student", "attempt", "assessor", "observed_at", "recorded_at", "is_released")
    list_filter = ("is_released",)


@admin.register(LogbookEntry)
class LogbookEntryAdmin(admin.ModelAdmin):
    list_display = ("student", "site", "work_date", "unit_type", "hours", "status")
    list_filter = ("status", "unit_type")


@admin.register(CompetencyResult)
class CompetencyResultAdmin(admin.ModelAdmin):
    list_display = ("student", "site", "unit", "status", "assessor", "decided_on")
    list_filter = ("status",)


admin.site.register(CompetencyFramework)
admin.site.register(PracticalAssessor)
