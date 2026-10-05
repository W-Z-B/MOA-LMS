from django.apps import AppConfig


class IntegrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integration"

    def ready(self):
        from integration import schema  # noqa: F401 - registers the documentation extension
