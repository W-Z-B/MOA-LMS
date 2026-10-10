from django.apps import AppConfig


class SimilarityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "similarity"

    def ready(self) -> None:
        from similarity import signals  # noqa: F401 - registers the check after each hand-in
