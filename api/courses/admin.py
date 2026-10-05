from django.contrib import admin

from courses.models import (
    Announcement,
    Completion,
    ContentItem,
    CourseSite,
    ItemCompletion,
    Membership,
    Module,
    SiteGroup,
    SiteTemplate,
    TakedownRequest,
)


@admin.register(CourseSite)
class CourseSiteAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "term_code", "campus_code", "source", "kind", "is_published")
    list_filter = ("source", "kind", "term_code", "campus_code", "is_published")
    search_fields = ("code", "title")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("site", "person", "role", "is_active")
    list_filter = ("role", "is_active")


@admin.register(SiteTemplate)
class SiteTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "is_default")


@admin.register(TakedownRequest)
class TakedownRequestAdmin(admin.ModelAdmin):
    list_display = ("item", "status", "created_at", "reviewed_at")
    list_filter = ("status",)


admin.site.register(Module)
admin.site.register(ContentItem)
admin.site.register(Announcement)
admin.site.register(Completion)
admin.site.register(SiteGroup)
admin.site.register(ItemCompletion)
