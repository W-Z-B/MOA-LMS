from django.apps import AppConfig


class IamConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "iam"

    def ready(self):
        from iam import sessions  # noqa: F401 - connects the sign-in, sign-out and role-change receivers
