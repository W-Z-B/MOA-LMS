from django.contrib import admin

from courses.models import Announcement, Completion, ContentItem, CourseSite, Membership, Module


@admin.register(CourseSite)
class CourseSiteAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "term_code", "campus_code", "source", "kind", "is_published")
    list_filter = ("source", "kind", "term_code", "campus_code", "is_published")
    search_fields = ("code", "title")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("site", "person", "role", "is_active")
    list_filter = ("role", "is_active")


admin.site.register(Module)
admin.site.register(ContentItem)
admin.site.register(Announcement)
admin.site.register(Completion)
