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
    "practicals",
    "approvals",
    "staffdev",
    "certificates",
    "forums",
    "messaging",
    "attendance",
    "calendars",
    "rubrics",
    "terms",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "iam.middleware.SessionActivityMiddleware",  # idle and absolute time-outs; the session list
    "terms.guard.ClosedSiteMiddleware",  # closed course sites refuse changes (item 7.12)
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
    # Choice sets that appear under the same field name in several places get one stable name each.
    "ENUM_NAME_OVERRIDES": {
        "SiteKindEnum": "courses.models.CourseSite.Kind",
        "ContentKindEnum": "courses.models.ContentItem.Kind",
        "QuizReviewEnum": "quizzes.models.Quiz.Review",
        "RubricKindEnum": "rubrics.models.Rubric.Kind",
        "NotificationKindEnum": "notifications.models.Notification.Kind",
    },
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

# `manage.py check --deploy` runs in CI and must pass with no warnings. These three are deliberate:
SILENCED_SYSTEM_CHECKS = [
    # W008 SECURE_SSL_REDIRECT: Caddy redirects HTTP to HTTPS in every deployment; a redirect here
    # would also break the container health checks, which call gunicorn directly over HTTP.
    "security.W008",
    # W005 and W021 (HSTS subdomains and preload): GSA's domain and its other services are not known
    # yet. Caddy sends a one-year HSTS header for this host; widen it once the domain is confirmed.
    "security.W005",
    "security.W021",
]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 8 * 60 * 60  # working day: the absolute limit, enforced by iam.middleware
SESSION_IDLE_MINUTES = int(env("SESSION_IDLE_MINUTES", "30"))

# Upload limits in megabytes, checked with the file's type in core.uploads. Caddy refuses any request body
# over 60 MB before it reaches the application.
UPLOAD_LIMIT_CONTENT_MB = int(env("UPLOAD_LIMIT_CONTENT_MB", "50"))
UPLOAD_LIMIT_SUBMISSION_MB = int(env("UPLOAD_LIMIT_SUBMISSION_MB", "20"))
UPLOAD_LIMIT_EVIDENCE_MB = int(env("UPLOAD_LIMIT_EVIDENCE_MB", "15"))  # practical photographs and scans
# Storage allowance for each course site's files, in megabytes (item 2.20). A course administrator can set
# a different allowance on one site. Teaching staff are warned at 80% and refused at 100%.
SITE_STORAGE_ALLOWANCE_MB = int(env("SITE_STORAGE_ALLOWANCE_MB", "2048"))

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

# Accounts (item 1.22): opened from the synced person records; the person chooses a password through a
# one-use emailed link. Links point at the web app, PUBLIC_URL (the first public origin when unset).
PUBLIC_URL = (env("PUBLIC_URL") or (PUBLIC_ORIGINS or [f"https://{ALLOWED_HOSTS[0]}"])[0]).rstrip("/")
INVITATION_DAYS = int(env("INVITATION_DAYS", "7"))
PASSWORD_RESET_MINUTES = int(env("PASSWORD_RESET_MINUTES", "60"))
# Django's own limit is set to the longest; each kind of link checks its own, stricter, limit.
PASSWORD_RESET_TIMEOUT = max(INVITATION_DAYS * 24 * 3600, PASSWORD_RESET_MINUTES * 60)
PASSWORD_RESETS_PER_ADDRESS = int(env("PASSWORD_RESETS_PER_ADDRESS", "5"))
PASSWORD_RESETS_PER_ACCOUNT = 3
# A new sign-in email address is used only once the link sent to it is followed within this time (item 1.10).
EMAIL_CHANGE_HOURS = int(env("EMAIL_CHANGE_HOURS", "48"))

# Integration runs (item 1.23): a call that cannot reach the sibling system is tried this many times,
# waiting INTEGRATION_RETRY_SECONDS, then twice that, between tries.
INTEGRATION_ATTEMPTS = int(env("INTEGRATION_ATTEMPTS", "3"))
INTEGRATION_RETRY_SECONDS = float(env("INTEGRATION_RETRY_SECONDS", "5"))

# Approvals (ported from the HRMS approvals engine): a decision waits DECISION_DAYS working days (set with
# To do below) before a reminder, and ESCALATE_AFTER_DAYS more before it goes on to the next person up.
ESCALATE_AFTER_DAYS = int(env("ESCALATE_AFTER_DAYS", "2"))

# Staff development (Phase 5). A completion that expires is open for renewal this many days before it does.
RENEWAL_WINDOW_DAYS = int(env("RENEWAL_WINDOW_DAYS", "60"))
# Days before a required course is due on which a reminder goes.
REQUIRED_TRAINING_REMIND_DAYS = int(env("REQUIRED_TRAINING_REMIND_DAYS", "7"))

# Certificates (items 5.08 to 5.11): the heading, the reference prefix, where they are checked, and how many
# wrong codes one address, or one reference, may try within LOGIN_LOCKOUT_MINUTES.
CERTIFICATE_ORGANISATION = env("CERTIFICATE_ORGANISATION", "Guyana School of Agriculture")
CERTIFICATE_REFERENCE_PREFIX = env("CERTIFICATE_REFERENCE_PREFIX", "GSA/LMS")
CERTIFICATE_CHECK_URL = env("CERTIFICATE_CHECK_URL", f"{PUBLIC_URL}/api/check-certificate/")
CERTIFICATE_CHECK_FAILURES = int(env("CERTIFICATE_CHECK_FAILURES", "10"))
# Conversation (items 4.08 to 4.11). Authors may change or remove their own forum post for this long.
FORUM_EDIT_MINUTES = int(env("FORUM_EDIT_MINUTES", "30"))
# Private messages between students: off unless GSA asks for them (feature 23, gap G13).
MESSAGING_STUDENT_TO_STUDENT = env_bool("MESSAGING_STUDENT_TO_STUDENT", False)

# Attendance (item 4.15, decision D6): how long a check-in code shown in the room is valid, and when a
# student checking in after the start counts as late.
ATTENDANCE_CODE_SECONDS = int(env("ATTENDANCE_CODE_SECONDS", "60"))
ATTENDANCE_LATE_AFTER_MINUTES = int(env("ATTENDANCE_LATE_AFTER_MINUTES", "10"))

# To do (items 2.07 to 2.09): days after which work to mark, and a decision, are marked overdue.
MARKING_DAYS = int(env("MARKING_DAYS", "14"))
DECISION_DAYS = int(env("DECISION_DAYS", "7"))

# Term life-cycle (item 7.12). Sites take work until the end of their term's close date and this many days
# after it, unless the term sets its own grace; then they are read-only for appeals. They are archived when
# the retention schedule's period for course sites has passed (privacy rule "course-sites"; this is the
# default until that rule exists). TERMS_FROM_SRMS takes the calendar from the SRMS's integration API, which
# the SRMS does not offer yet: off until GSA and the SRMS agree it; course administrators enter terms.
# TERM_CLOSE_AFTER_DAYS: for a term from the SRMS, the close date this many days after teaching ends.
TERM_GRACE_DAYS = int(env("TERM_GRACE_DAYS", "2"))
TERM_ARCHIVE_MONTHS = int(env("TERM_ARCHIVE_MONTHS", "12"))
TERMS_FROM_SRMS = env_bool("TERMS_FROM_SRMS", False)
TERM_CLOSE_AFTER_DAYS = int(env("TERM_CLOSE_AFTER_DAYS", "28"))
