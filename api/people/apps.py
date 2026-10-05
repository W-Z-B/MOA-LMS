from django.apps import AppConfig


class PeopleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "people"

    def ready(self):
        from people import signals  # noqa: F401 - closes the account of a person who goes inactive
