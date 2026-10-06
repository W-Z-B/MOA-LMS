from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from certificates.api import check_page
from config.views import health
from iam.permissions import DocsPermission
from integration.api import integration_urls, reference_urls, run_urls

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[DocsPermission]), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[DocsPermission]),
        name="docs",
    ),
    path("api/v1/auth/", include("iam.urls")),
    path("api/v1/notifications/", include("notifications.api")),
    path("api/v1/", include("assessments.api")),
    path("api/v1/", include("quizzes.api")),
    path("api/v1/", include("practicals.api")),
    path("api/v1/", include("courses.group_api")),
    path("api/v1/", include("rubrics.api")),
    path("api/v1/", include("similarity.api")),
    path("api/v1/", include("peerreview.api")),
    path("api/v1/", include("paperquizzes.api")),
    path("api/v1/", include("opencourses.api")),
    path("api/v1/", include("courses.api")),
    path("api/v1/", include("video.urls")),
    path("api/v1/", include("forums.api")),
    path("api/v1/", include("messaging.api")),
    path("api/v1/", include("attendance.api")),
    path("api/v1/", include("calendars.api")),
    path("api/v1/", include("helpdesk.api")),
    path("api/v1/", include("insights.api")),
    path("api/v1/", include("audit.urls")),
    path("api/v1/", include("core.urls")),
    path("api/v1/privacy/", include("privacy.urls")),
    path("api/v1/", include(run_urls)),
    path("api/v1/approvals/", include("approvals.urls")),
    path("api/v1/staff-development/", include("staffdev.api")),
    path("api/v1/", include("certificates.api")),
    # Outside tools (item 6.07): registering and placing them, and the LTI 1.3 addresses tools use.
    path("api/v1/", include("lti.api")),
    path("api/lti/", include("lti.views")),
    # AI assistance within decision D5 (items 6.11, 6.12): off unless GSA switches it on.
    path("api/v1/", include("assist.api")),
    # The public certificate check as a page of its own, without sign-in or script (item 5.09).
    path("api/check-certificate/", check_page, name="certificate-check-page"),
    path("api/v1/reference/", include((reference_urls, "reference"))),
    # Service-to-service API for the GSA ecosystem. Api-Key authentication, scoped.
    path("api/v1/integration/", include((integration_urls, "integration"))),
]

# Course files and submissions are never served from MEDIA_URL; downloads go through authenticated endpoints.
