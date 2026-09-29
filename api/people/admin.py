from django.contrib import admin

from people.models import PersonRef


@admin.register(PersonRef)
class PersonRefAdmin(admin.ModelAdmin):
    list_display = ("external_id", "kind", "last_name", "first_name", "campus_code", "is_active", "user")
    list_filter = ("kind", "campus_code", "is_active")
    search_fields = ("external_id", "first_name", "last_name")
