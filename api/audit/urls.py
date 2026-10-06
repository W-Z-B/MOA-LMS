from rest_framework.routers import SimpleRouter

from audit import views

router = SimpleRouter()
router.register("audit", views.AuditLogViewSet, basename="audit")

urlpatterns = router.urls
