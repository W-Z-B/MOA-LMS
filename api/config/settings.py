"""
GSA LMS settings. Every environment-specific value comes from the environment (.env in Compose).
No secrets are stored in this file.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    return str(env(name, "1" if default else "0")).lower() in {"1", "true", "yes"}


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in {"localhost", "127.0.0.1", "api"}]

# Key for application-layer encryption of sensitive identifiers.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", "")

INSTALLED_APPS = [
    # The admin, with sign-in only through the web app (lockout and authenticator): iam/admin_site.py
    "iam.admin_apps.LmsAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "procrastinate.contrib.django",
    # shared with the GSA ecosystem skeleton
    "core",
    "audit",
    "iam",
    "notifications",
    "integration",
    # domain modules
    "people",
    "courses",
    "assessments",
    "privacy",
    "quizzes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "iam.middleware.SessionActivityMiddleware",  # idle and absolute time-outs; the session list
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL in every real environment. SQLite is used only when DB_HOST is unset,
# so that `manage.py check` and unit tests can run without a database server.
if env("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": env("DB_HOST"),
            "PORT": env("DB_PORT", "5432"),
            "NAME": env("DB_NAME", "lms"),
            "USER": env("DB_USER", "lms"),
            "PASSWORD": env("DB_PASSWORD", ""),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "600/minute"},
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
}

# The OpenAPI schema and Swagger UI: public in development, signed-in people only elsewhere.
API_DOCS_PUBLIC = env_bool("API_DOCS_PUBLIC", DEBUG)

SPECTACULAR_SETTINGS = {
    "TITLE": "GSA LMS API",
    "DESCRIPTION": "Learning Management System, Guyana School of Agriculture",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {"QuizReviewEnum": "quizzes.models.Quiz.Review"},
}

CORS_ALLOWED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in {"localhost", "127.0.0.1", "api"}]
CORS_ALLOW_CREDENTIALS = True

# Email: SMTP when configured, otherwise printed to the log (development).
if env("SMTP_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("SMTP_HOST")
    EMAIL_PORT = int(env("SMTP_PORT", "587"))
    EMAIL_HOST_USER = env("SMTP_USER", "")
    EMAIL_HOST_PASSWORD = env("SMTP_PASSWORD", "")
    EMAIL_USE_TLS = True
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("SMTP_FROM", "lms@localhost")

LANGUAGE_CODE = "en-gb"
TIME_ZONE = env("TZ", "America/Guyana")
USE_I18N = True
USE_TZ = True
DATE_FORMAT = "d/m/Y"
SHORT_DATE_FORMAT = "d/m/Y"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "files/"
MEDIA_ROOT = Path(env("FILES_ROOT", "/srv/files")) if env("DB_HOST") else BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Security hardening applied whenever DEBUG is off.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 8 * 60 * 60  # working day: the absolute limit, enforced by iam.middleware
SESSION_IDLE_MINUTES = int(env("SESSION_IDLE_MINUTES", "30"))

# Upload limits in megabytes, checked with the file's type in core.uploads. Caddy refuses any request body
# over 60 MB before it reaches the application.
UPLOAD_LIMIT_CONTENT_MB = int(env("UPLOAD_LIMIT_CONTENT_MB", "50"))
UPLOAD_LIMIT_SUBMISSION_MB = int(env("UPLOAD_LIMIT_SUBMISSION_MB", "20"))

# Account lockout: this many consecutive failed logins inside the window locks the account for the window.
LOGIN_MAX_FAILURES = int(env("LOGIN_MAX_FAILURES", "5"))
LOGIN_LOCKOUT_MINUTES = int(env("LOGIN_LOCKOUT_MINUTES", "15"))
# Failed sign-ins from one network address, across all accounts, before that address waits out the window.
LOGIN_MAX_FAILURES_PER_ADDRESS = int(env("LOGIN_MAX_FAILURES_PER_ADDRESS", "20"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# Browser origins that include a port (development) or an extra host name.
PUBLIC_ORIGINS = [o for o in (env("PUBLIC_ORIGINS", "") or "").split(",") if o]
CSRF_TRUSTED_ORIGINS += PUBLIC_ORIGINS
CORS_ALLOWED_ORIGINS += PUBLIC_ORIGINS

# GSA ecosystem: sibling systems reached over the integration API with scoped service keys.
HRMS_API_URL = env("HRMS_API_URL", "")
HRMS_API_KEY = env("HRMS_API_KEY", "")
SRMS_API_URL = env("SRMS_API_URL", "")
SRMS_API_KEY = env("SRMS_API_KEY", "")
INTEGRATION_TIMEOUT_SECONDS = int(env("INTEGRATION_TIMEOUT_SECONDS", "15"))

# Privacy (items 1.18, 1.19): days within which a correction request is to be answered.
PRIVACY_RESPONSE_DAYS = int(env("PRIVACY_RESPONSE_DAYS", "30"))
