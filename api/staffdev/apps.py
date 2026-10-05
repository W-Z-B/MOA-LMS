from django.apps import AppConfig


class StaffdevConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "staffdev"
    verbose_name = "Staff development"

    def ready(self):
        from staffdev import signals  # noqa: F401 - checks completion as items, quizzes and marks are done
