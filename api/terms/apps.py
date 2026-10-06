from django.apps import AppConfig


class TermsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "terms"
    verbose_name = "Terms"

    def ready(self):
        # Every record that belongs to a course site is refused a change once its term has closed (item 7.12).
        from terms import guard

        guard.connect()
